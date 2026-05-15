import { Ionicons } from '@expo/vector-icons';
import { VideoView, useVideoPlayer } from 'expo-video';
import * as VideoThumbnails from 'expo-video-thumbnails';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { getSavedVideos } from '../../lib/backendApi';
import type { SavedVideo } from '../../lib/backendApi';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import tokens from '../theme/tokens';
import {
  formatExerciseLabel,
} from '../utils/savedVideos';

type HomeScreenProps = {
  email?: string | null;
  refreshKey?: number;
  onNavigateToAddVideo?: () => void;
  onOpenSavedLiftFolder?: (exerciseType: string) => void;
  onSavedVideosLoaded?: (videos: SavedVideo[]) => void;
};

type SavedVideoGroup = {
  exerciseType: string;
  label: string;
  videos: SavedVideo[];
};

const MAX_PREVIEW_TILES = 4;
const FOLDER_HEIGHT = 208;
const PREVIEW_TILE_HEIGHT = FOLDER_HEIGHT / 2;
const PREVIEW_TILE_WIDTH = 96;

function groupSavedVideos(videos: SavedVideo[]): SavedVideoGroup[] {
  const groups = new Map<string, SavedVideo[]>();

  for (const video of videos) {
    const currentVideos = groups.get(video.exercise_type) ?? [];
    currentVideos.push(video);
    groups.set(video.exercise_type, currentVideos);
  }

  return Array.from(groups.entries()).map(([exerciseType, groupVideos]) => ({
    exerciseType,
    label: formatExerciseLabel(exerciseType),
    videos: groupVideos,
  }));
}

function VideoFramePreview({ videoUrl }: { videoUrl: string }) {
  const player = useVideoPlayer(videoUrl, (videoPlayer) => {
    videoPlayer.muted = true;
    videoPlayer.loop = false;
    videoPlayer.currentTime = 0;
    videoPlayer.pause();
  });

  useEffect(() => {
    player.pause();
    player.currentTime = 0;
  }, [player, videoUrl]);

  return (
    <VideoView
      style={styles.previewImage}
      player={player}
      nativeControls={false}
      allowsPictureInPicture={false}
      contentFit="cover"
    />
  );
}

function PreviewTile({ video }: { video: SavedVideo }) {
  const [generatedThumbnailUri, setGeneratedThumbnailUri] = useState<string | null>(null);
  const [thumbnailLoadFailed, setThumbnailLoadFailed] = useState(false);

  useEffect(() => {
    setThumbnailLoadFailed(false);
  }, [video.thumbnail_url]);

  useEffect(() => {
    if (video.thumbnail_url || !video.video_url || Platform.OS === 'web') {
      setGeneratedThumbnailUri(null);
      return;
    }

    let active = true;

    const generateVideoPreview = async () => {
      try {
        const thumbnail = await VideoThumbnails.getThumbnailAsync(video.video_url, {
          time: 1000,
          quality: 0.65,
        });

        if (active) {
          setGeneratedThumbnailUri(thumbnail.uri);
        }
      } catch (error) {
        if (__DEV__) {
          console.warn('Unable to generate saved video preview thumbnail.', error);
        }

        if (active) {
          setGeneratedThumbnailUri(null);
        }
      }
    };

    void generateVideoPreview();

    return () => {
      active = false;
    };
  }, [video.thumbnail_url, video.video_url]);

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

  if (generatedThumbnailUri) {
    return (
      <Image
        source={{ uri: generatedThumbnailUri }}
        style={styles.previewImage}
        resizeMode="cover"
      />
    );
  }

  if (video.video_url) {
    return <VideoFramePreview videoUrl={video.video_url} />;
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
  const extraCount = Math.max(group.videos.length - previewVideos.length, 0);

  return (
    <View style={styles.folderBlock}>
      <Text style={styles.exerciseTitle}>{group.label}</Text>
      <Pressable accessibilityRole="button" onPress={onPress} style={styles.folderCard}>
        <View style={styles.previewStrip}>
          {previewVideos.map((video) => (
            <View key={video.id} style={styles.previewTile}>
              <PreviewTile video={video} />
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

export default function HomeScreen({
  refreshKey = 0,
  onNavigateToAddVideo,
  onOpenSavedLiftFolder,
  onSavedVideosLoaded,
}: HomeScreenProps) {
  const { session, signOut } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [savedVideos, setSavedVideos] = useState<SavedVideo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadSavedVideos = async () => {
      if (!session?.access_token) {
        setLoading(false);
        setSavedVideos([]);
        onSavedVideosLoaded?.([]);
        return;
      }

      setLoading(true);
      setLoadError(null);

      try {
        const videos = await getSavedVideos(session.access_token);

        if (cancelled) {
          return;
        }

        setSavedVideos(videos);
        onSavedVideosLoaded?.(videos);
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : 'Unable to load saved videos.');
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
    };
  }, [session?.access_token, refreshKey, reloadKey]);

  const groups = useMemo(() => groupSavedVideos(savedVideos), [savedVideos]);

  const handleLogout = async () => {
    setSubmitting(true);
    setLogoutError(null);

    try {
      await signOut();
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : 'Unable to log out.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Pressable
            onPress={handleLogout}
            disabled={submitting}
            accessibilityRole="button"
            style={[styles.logoutButton, submitting && styles.disabledButton]}
          >
            <Text style={styles.logoutText}>{submitting ? 'Logging Out...' : 'Log Out'}</Text>
          </Pressable>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.pageTitle}>Saved Lifts</Text>

          {loading ? (
            <View style={styles.stateBlock}>
              <ActivityIndicator color={tokens.colors.brand} />
              <Text style={styles.stateText}>Loading saved videos...</Text>
            </View>
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

          {logoutError ? <Text style={styles.errorText}>{logoutError}</Text> : null}
        </ScrollView>

        <BottomNav activeTab="home" onHomePress={() => {}} onAddPress={onNavigateToAddVideo} />
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
  header: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start',
    paddingHorizontal: 18,
    paddingTop: 6,
  },
  logoutButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: tokens.colors.brand,
    borderRadius: 999,
  },
  logoutText: {
    color: tokens.colors.brand,
    fontSize: 12,
    fontWeight: '700',
  },
  disabledButton: {
    opacity: 0.6,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 0,
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
  },
  stateText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
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
