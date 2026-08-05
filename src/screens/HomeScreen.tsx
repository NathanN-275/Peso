import { Ionicons } from '@expo/vector-icons';
import { useEffect, useMemo, useState } from 'react';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { describeBackendRequestFailure, getSavedVideoOverview } from '../../lib/backendApi';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import { SkeletonBlock } from '../components/Skeleton';
import tokens from '../theme/tokens';
import type { SavedVideo, SavedVideoOverview } from '../types/videoAnalysis';
import {
  formatExerciseLabel,
  getSavedWorkoutFacts,
} from '../utils/savedVideos';

type HomeScreenProps = {
  email?: string | null;
  refreshKey?: number;
  onNavigateToAddVideo?: () => void;
  onNavigateToProfile?: () => void;
  onOpenSavedLiftFolder?: (exerciseType: string) => void;
  cachedSavedOverview?: SavedVideoOverview | null;
  savedOverviewLoaded?: boolean;
  onSavedOverviewLoaded?: (overview: SavedVideoOverview) => void;
};

type SavedVideoGroup = {
  exerciseType: string;
  label: string;
  count: number;
  videos: SavedVideo[];
};

const MAX_PREVIEW_TILES = 4;
const FOLDER_HEIGHT = 208;
const PREVIEW_TILE_HEIGHT = FOLDER_HEIGHT / 2;
const PREVIEW_TILE_WIDTH = 96;
const EMPTY_SAVED_OVERVIEW: SavedVideoOverview = {
  stats: {
    total_saved: 0,
    exercise_count: 0,
    total_reps: 0,
    latest_exercise_type: null,
    latest_saved_at: null,
    most_trained_exercise_type: null,
    most_trained_count: 0,
  },
  groups: [],
};

function groupSavedOverview(overview: SavedVideoOverview | null): SavedVideoGroup[] {
  return (overview?.groups ?? []).map((group) => ({
    exerciseType: group.exercise_type,
    label: formatExerciseLabel(group.exercise_type),
    count: group.count,
    videos: group.preview_items,
  }));
}

function PreviewTile({ video }: { video: SavedVideo }) {
  const [thumbnailLoadFailed, setThumbnailLoadFailed] = useState(false);

  useEffect(() => {
    setThumbnailLoadFailed(false);
  }, [video.thumbnail_url]);

  if (video.thumbnail_url && !thumbnailLoadFailed) {
    return (
      <Image
        source={{ uri: video.thumbnail_url }}
        style={styles.previewImage}
        resizeMode="cover"
        onError={() => setThumbnailLoadFailed(true)}
      />
    );
  }

  return <View style={styles.previewPlaceholder} />;
}

function LiftFolderCard({
  group,
  onPress,
}: {
  group: SavedVideoGroup;
  onPress?: () => void;
}) {
  const previewVideos = group.videos.slice(0, MAX_PREVIEW_TILES);
  const extraCount = Math.max(group.count - previewVideos.length, 0);

  return (
    <View style={styles.folderBlock}>
      <Text style={styles.exerciseTitle}>{group.label}</Text>
      <Pressable accessibilityRole="button" onPress={onPress} style={styles.folderCard}>
        <View style={styles.previewStrip}>
          {previewVideos.map((video) => (
            <View key={video.id} style={styles.previewTile}>
              <PreviewTile video={video} />
              {getSavedWorkoutFacts(video) ? (
                <Text style={styles.previewFacts} numberOfLines={1}>
                  {getSavedWorkoutFacts(video)}
                </Text>
              ) : null}
            </View>
          ))}
          {extraCount > 0 ? (
            <View style={[styles.previewTile, styles.extraTile]}>
              <Text style={styles.extraTileText}>+{extraCount}</Text>
            </View>
          ) : null}
        </View>
      </Pressable>
    </View>
  );
}

function SavedFoldersSkeleton() {
  return (
    <View style={styles.skeletonList}>
      {[0, 1, 2].map((index) => (
        <View key={index} style={styles.skeletonFolder}>
          <SkeletonBlock width="54%" height={32} radius={6} style={styles.skeletonTitle} />
          <View style={styles.skeletonPreviewStrip}>
            {[0, 1, 2, 3].map((tileIndex) => (
              <SkeletonBlock
                key={tileIndex}
                width={PREVIEW_TILE_WIDTH}
                height={PREVIEW_TILE_HEIGHT}
                radius={0}
              />
            ))}
          </View>
        </View>
      ))}
    </View>
  );
}

export default function HomeScreen({
  refreshKey = 0,
  onNavigateToAddVideo,
  onNavigateToProfile,
  onOpenSavedLiftFolder,
  cachedSavedOverview = null,
  savedOverviewLoaded = false,
  onSavedOverviewLoaded,
}: HomeScreenProps) {
  const { session } = useAuth();
  const [loading, setLoading] = useState(!savedOverviewLoaded);
  const [savedOverview, setSavedOverview] = useState<SavedVideoOverview | null>(cachedSavedOverview);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!savedOverviewLoaded) {
      return;
    }

    setSavedOverview(cachedSavedOverview);
    setLoadError(null);
    setLoading(false);
  }, [cachedSavedOverview, savedOverviewLoaded]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const loadSavedVideos = async () => {
      if (!session?.access_token) {
        setLoading(false);
        setSavedOverview(EMPTY_SAVED_OVERVIEW);
        onSavedOverviewLoaded?.(EMPTY_SAVED_OVERVIEW);
        return;
      }

      if (savedOverviewLoaded) {
        setLoading(false);
        setLoadError(null);
        return;
      }

      setLoading(true);
      setLoadError(null);

      try {
        const overview = await getSavedVideoOverview(session.access_token, controller.signal);

        if (cancelled) {
          return;
        }

        if (__DEV__) {
          const previewVideos = overview.groups.flatMap((group) => group.preview_items);
          const missingThumbnailCount = previewVideos.filter((video) => !video.thumbnail_url).length;

          if (missingThumbnailCount > 0) {
            console.warn('Saved overview previews missing thumbnail URLs.', {
              count: missingThumbnailCount,
              videoIds: previewVideos
                .filter((video) => !video.thumbnail_url)
                .map((video) => video.id),
            });
          }
        }

        setSavedOverview(overview);
        onSavedOverviewLoaded?.(overview);
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          return;
        }

        const message = await describeBackendRequestFailure(
          error,
          'Unable to load saved videos.'
        );

        if (!cancelled) {
          setLoadError(message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadSavedVideos();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [session?.access_token, refreshKey, reloadKey, savedOverviewLoaded]);

  const groups = useMemo(() => groupSavedOverview(savedOverview), [savedOverview]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.pageTitle}>Saved Lifts</Text>

          {loading ? (
            <SavedFoldersSkeleton />
          ) : null}

          {!loading && loadError ? (
            <View style={styles.stateBlock}>
              <Text style={styles.errorText}>{loadError}</Text>
              <Pressable accessibilityRole="button" onPress={() => setReloadKey((key) => key + 1)}>
                <Text style={styles.retryText}>Try Again</Text>
              </Pressable>
            </View>
          ) : null}

          {!loading && !loadError && groups.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>No saved videos yet</Text>
              <Text style={styles.emptyCopy}>Analyze and save a lift to see it here.</Text>
              <Pressable
                accessibilityRole="button"
                onPress={onNavigateToAddVideo}
                style={styles.emptyAddButton}
              >
                <Ionicons name="add-circle-outline" size={28} color={tokens.colors.textPrimary} />
                <Text style={styles.emptyAddText}>Add Video</Text>
              </Pressable>
            </View>
          ) : null}

          {!loading && !loadError ? (
            <View style={styles.folderList}>
              {groups.map((group) => (
                <LiftFolderCard
                  key={group.exerciseType}
                  group={group}
                  onPress={() => onOpenSavedLiftFolder?.(group.exerciseType)}
                />
              ))}
            </View>
          ) : null}

        </ScrollView>

        <BottomNav
          activeTab="home"
          onHomePress={() => {}}
          onAddPress={onNavigateToAddVideo}
          onProfilePress={onNavigateToProfile}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
  },
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 0,
    paddingTop: 40,
    paddingBottom: NAV_HEIGHT + 34,
  },
  pageTitle: {
    color: tokens.colors.brand,
    fontSize: 42,
    lineHeight: 48,
    fontWeight: '800',
    marginTop: 4,
    marginBottom: 22,
    paddingHorizontal: 14,
  },
  folderList: {
    gap: 24,
  },
  skeletonList: {
    gap: 24,
  },
  skeletonFolder: {
    gap: 8,
  },
  skeletonTitle: {
    marginHorizontal: 14,
  },
  skeletonPreviewStrip: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 2,
    overflow: 'hidden',
  },
  folderBlock: {
    gap: 6,
  },
  exerciseTitle: {
    color: tokens.colors.brand,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '800',
    paddingHorizontal: 14,
  },
  folderCard: {
    width: '100%',
    height: FOLDER_HEIGHT,
    borderRadius: 0,
    backgroundColor: '#252525',
    paddingHorizontal: 0,
    paddingTop: 0,
    paddingBottom: 0,
  },
  previewStrip: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 2,
  },
  previewTile: {
    width: PREVIEW_TILE_WIDTH,
    height: PREVIEW_TILE_HEIGHT,
    overflow: 'hidden',
    backgroundColor: '#D8D8D8',
  },
  previewImage: {
    width: '100%',
    height: '100%',
  },
  previewPlaceholder: {
    flex: 1,
    backgroundColor: '#D8D8D8',
  },
  previewFacts: {
    position: 'absolute',
    right: 4,
    bottom: 4,
    left: 4,
    borderRadius: 5,
    backgroundColor: 'rgba(0, 0, 0, 0.72)',
    color: tokens.colors.textPrimary,
    paddingHorizontal: 4,
    paddingVertical: 3,
    fontSize: 9,
    lineHeight: 11,
    fontWeight: '800',
    textAlign: 'center',
  },
  extraTile: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#4B4B4B',
  },
  extraTileText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '800',
  },
  stateBlock: {
    minHeight: 180,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    paddingHorizontal: 18,
  },
  errorText: {
    color: '#FF8A8A',
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  retryText: {
    color: tokens.colors.brand,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
  emptyState: {
    minHeight: 330,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    paddingHorizontal: 18,
  },
  emptyTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '800',
    textAlign: 'center',
  },
  emptyCopy: {
    color: tokens.colors.textMuted,
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'center',
  },
  emptyAddButton: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 999,
    backgroundColor: tokens.colors.brand,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  emptyAddText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '800',
  },
});
