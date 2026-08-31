import { Ionicons } from '@expo/vector-icons';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  AppState,
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
import { shouldPollAnalysisActivity } from '../../lib/analysisActivityPolicy';
import {
  discardAnalyzedVideo,
  describeBackendRequestFailure,
  getAnalysisActivity,
  getSavedVideoOverview,
  triggerVideoAnalysis,
} from '../../lib/backendApi';
import { canRetryAnalysis, failureCopy } from '../../lib/analysisRecoveryPolicy';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import { SkeletonBlock } from '../components/Skeleton';
import tokens from '../theme/tokens';
import type {
  AnalysisActivityItem,
  SavedVideo,
  SavedVideoOverview,
} from '../types/videoAnalysis';
import {
  formatExerciseLabel,
  getSavedWorkoutFacts,
} from '../utils/savedVideos';

type HomeScreenProps = {
  email?: string | null;
  refreshKey?: number;
  queuedAnalysisConfirmation?: string | null;
  onQueuedAnalysisConfirmationDismiss?: () => void;
  onNavigateToAddVideo?: () => void;
  onNavigateToProfile?: () => void;
  onOpenAnalysisActivity?: (videoId: string) => void | Promise<void>;
  onOpenSavedLiftFolder?: (exerciseType: string) => void;
  cachedSavedOverview?: SavedVideoOverview | null;
  savedOverviewLoaded?: boolean;
  onSavedOverviewLoaded?: (overview: SavedVideoOverview) => void;
};

function activityStatusCopy(activity: AnalysisActivityItem) {
  switch (activity.stage) {
    case 'queued':
      return { label: 'Queued', detail: 'Waiting for analysis to start', icon: 'time-outline' as const };
    case 'downloading':
      return { label: 'Downloading', detail: 'Downloading video', icon: 'cloud-download-outline' as const };
    case 'pose':
      return { label: 'Pose', detail: 'Estimating pose', icon: 'body-outline' as const };
    case 'barbell_tracking':
      return { label: 'Barbell tracking', detail: 'Tracking barbell', icon: 'analytics-outline' as const };
    case 'saving':
      return { label: 'Saving', detail: 'Saving analysis', icon: 'save-outline' as const };
    case 'ready':
      return { label: 'Ready', detail: 'Ready to review', icon: 'checkmark-circle-outline' as const };
    case 'failed':
      return { label: 'Failed', detail: failureCopy(activity), icon: 'alert-circle-outline' as const };
  }
}

function AnalysisActivityCard({
  activity,
  onOpen,
  onRetry,
  onDelete,
  actionBusy,
}: {
  activity: AnalysisActivityItem;
  onOpen?: () => void;
  onRetry?: (videoId: string) => void;
  onDelete?: (videoId: string) => void;
  actionBusy?: boolean;
}) {
  const copy = activityStatusCopy(activity);
  const ready = activity.status === 'ready';
  const [thumbnailFailed, setThumbnailFailed] = useState(false);
  const [opening, setOpening] = useState(false);
  const [openFailed, setOpenFailed] = useState(false);

  useEffect(() => setThumbnailFailed(false), [activity.thumbnail_url]);

  const content = (
    <>
      {activity.thumbnail_url && !thumbnailFailed ? (
        <Image
          source={{ uri: activity.thumbnail_url }}
          style={styles.activityThumbnail}
          onError={() => setThumbnailFailed(true)}
        />
      ) : (
        <View style={styles.activityThumbnailPlaceholder}>
          <Ionicons name="barbell-outline" size={26} color={tokens.colors.textMuted} />
        </View>
      )}
      <View style={styles.activityCopy}>
        <Text style={styles.activityExercise}>{formatExerciseLabel(activity.exercise_type)}</Text>
        <Text style={styles.activityMeta}>{formatExerciseLabel(activity.view_type)} view</Text>
        <View style={styles.activityStatusRow}>
          <Ionicons
            name={copy.icon}
            size={17}
            color={ready ? tokens.colors.brand : tokens.colors.textMuted}
          />
          <Text style={[styles.activityStatus, ready && styles.activityStatusReady]}>
            {opening ? 'Loading review…' : openFailed ? 'Download failed — Retry' : copy.detail}
          </Text>
        </View>
      </View>
      {ready ? <Ionicons name="chevron-forward" size={22} color={tokens.colors.brand} /> : null}
      {activity.stage === 'failed' ? (
        <View style={styles.activityActions}>
          {canRetryAnalysis(activity) ? (
            <Pressable
              accessibilityRole="button"
              disabled={actionBusy}
              onPress={() => onRetry?.(activity.video_id)}
              style={[styles.activityAction, actionBusy && styles.activityActionDisabled]}
            >
              <Text style={styles.activityActionText}>{actionBusy ? 'Retrying…' : 'Try analysis again'}</Text>
            </Pressable>
          ) : null}
          <Pressable
            accessibilityRole="button"
            disabled={actionBusy}
            onPress={() => onDelete?.(activity.video_id)}
            style={[styles.activityAction, styles.activityDeleteAction, actionBusy && styles.activityActionDisabled]}
          >
            <Text style={styles.activityDeleteActionText}>{actionBusy ? 'Deleting…' : 'Delete video'}</Text>
          </Pressable>
        </View>
      ) : null}
    </>
  );

  if (!ready) {
    return <View style={styles.activityCard}>{content}</View>;
  }

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${formatExerciseLabel(activity.exercise_type)} analysis ${copy.label}`}
      disabled={opening}
      onPress={() => {
        if (!onOpen || opening) return;
        setOpening(true);
        setOpenFailed(false);
        Promise.resolve(onOpen())
          .catch(() => setOpenFailed(true))
          .finally(() => setOpening(false));
      }}
      style={[styles.activityCard, styles.activityCardReady]}
    >
      {content}
    </Pressable>
  );
}

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
  queuedAnalysisConfirmation = null,
  onQueuedAnalysisConfirmationDismiss,
  onNavigateToAddVideo,
  onNavigateToProfile,
  onOpenAnalysisActivity,
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
  const [analysisActivity, setAnalysisActivity] = useState<AnalysisActivityItem[]>([]);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [activityActionVideoId, setActivityActionVideoId] = useState<string | null>(null);
  const [activityReloadKey, setActivityReloadKey] = useState(0);
  const observedReadyJobsRef = useRef(new Set<string>());
  const [surfaceActive, setSurfaceActive] = useState(
    Platform.OS === 'web' ? typeof document === 'undefined' || document.visibilityState === 'visible' : true
  );

  useEffect(() => {
    if (Platform.OS === 'web') {
      const handleVisibility = () => setSurfaceActive(document.visibilityState === 'visible');
      document.addEventListener('visibilitychange', handleVisibility);
      return () => document.removeEventListener('visibilitychange', handleVisibility);
    }

    const subscription = AppState.addEventListener('change', (state) => {
      setSurfaceActive(state === 'active');
    });
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (!session?.access_token) {
      setAnalysisActivity([]);
      setActivityError(null);
      return;
    }
    if (!surfaceActive) {
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const poll = async () => {
      try {
        const response = await getAnalysisActivity(session.access_token, controller.signal);
        if (cancelled) {
          return;
        }
        setAnalysisActivity(response.items);
        setActivityError(null);
        response.items.forEach((item) => {
          if (item.stage !== 'ready' || observedReadyJobsRef.current.has(item.job_id)) {
            return;
          }
          const readyAt = item.stage_timestamps.ready
            ? Date.parse(item.stage_timestamps.ready)
            : Number.NaN;
          if (Number.isFinite(readyAt)) {
            console.info('[analysis-metric] ui_ready_delay_ms', {
              jobId: item.job_id,
              videoId: item.video_id,
              durationMs: Math.max(Date.now() - readyAt, 0),
            });
          }
          observedReadyJobsRef.current.add(item.job_id);
        });
        if (shouldPollAnalysisActivity(response.items, surfaceActive)) {
          timer = setTimeout(() => void poll(), 4000);
        }
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) {
          return;
        }
        setActivityError('Unable to refresh analysis activity.');
        timer = setTimeout(() => void poll(), 8000);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [activityReloadKey, session?.access_token, surfaceActive, refreshKey]);

  useEffect(() => {
    if (!queuedAnalysisConfirmation) {
      return;
    }

    const timer = setTimeout(() => onQueuedAnalysisConfirmationDismiss?.(), 7000);
    return () => clearTimeout(timer);
  }, [onQueuedAnalysisConfirmationDismiss, queuedAnalysisConfirmation]);

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

  const retryFailedAnalysis = async (videoId: string) => {
    if (!session?.access_token) return;

    setActivityActionVideoId(videoId);
    setActivityError(null);
    try {
      const response = await triggerVideoAnalysis(videoId, session.access_token);
      setAnalysisActivity((items) => items.map((item) => (
        item.video_id === videoId
          ? {
              ...item,
              job_id: response.job_id ?? item.job_id,
              status: response.status === 'processing' ? 'processing' : 'queued',
              stage: response.stage === 'failed' || response.stage === 'ready'
                ? 'queued'
                : response.stage,
              failure_class: null,
              recovery_action: null,
            }
          : item
      )));
      setActivityReloadKey((key) => key + 1);
    } catch (error) {
      setActivityError(error instanceof Error ? error.message : 'Unable to retry analysis.');
    } finally {
      setActivityActionVideoId(null);
    }
  };

  const deleteFailedAnalysis = (videoId: string) => {
    if (!session?.access_token) return;

    Alert.alert(
      'Delete failed video?',
      'This permanently removes the uploaded video and cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete video',
          style: 'destructive',
          onPress: () => {
            void (async () => {
              setActivityActionVideoId(videoId);
              setActivityError(null);
              try {
                await discardAnalyzedVideo(videoId, session.access_token);
                setAnalysisActivity((items) => items.filter((item) => item.video_id !== videoId));
                setActivityReloadKey((key) => key + 1);
              } catch (error) {
                setActivityError(error instanceof Error ? error.message : 'Unable to delete this video.');
              } finally {
                setActivityActionVideoId(null);
              }
            })();
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.safeArea} testID="home-screen">
      <View style={styles.container}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {queuedAnalysisConfirmation ? (
            <View accessibilityRole="alert" style={styles.queueConfirmation}>
              <Ionicons name="checkmark-circle-outline" size={22} color={tokens.colors.brand} />
              <Text style={styles.queueConfirmationText}>{queuedAnalysisConfirmation}</Text>
            </View>
          ) : null}
          {analysisActivity.length > 0 || activityError ? (
            <View style={styles.activitySection}>
              <Text style={styles.activityTitle}>Analysis Activity</Text>
              {analysisActivity.map((activity) => (
                <AnalysisActivityCard
                  key={activity.job_id}
                  activity={activity}
                  onOpen={activity.status === 'ready'
                    ? () => { void onOpenAnalysisActivity?.(activity.video_id); }
                    : undefined}
                  onRetry={activity.stage === 'failed' ? (videoId) => void retryFailedAnalysis(videoId) : undefined}
                  onDelete={activity.stage === 'failed' ? deleteFailedAnalysis : undefined}
                  actionBusy={activityActionVideoId === activity.video_id}
                />
              ))}
              {activityError ? <Text style={styles.activityError}>{activityError}</Text> : null}
            </View>
          ) : null}

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
                testID="home-add-video"
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
  queueConfirmation: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 20,
    marginHorizontal: 14,
    borderWidth: 1,
    borderColor: tokens.colors.brand,
    borderRadius: 14,
    backgroundColor: '#101722',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  queueConfirmationText: {
    flex: 1,
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  activitySection: {
    gap: 10,
    marginBottom: 28,
    paddingHorizontal: 14,
  },
  activityTitle: {
    color: tokens.colors.brand,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
  },
  activityCard: {
    minHeight: 92,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderColor: '#283345',
    borderRadius: 16,
    backgroundColor: '#101722',
    padding: 10,
  },
  activityCardReady: {
    borderColor: tokens.colors.brand,
  },
  activityThumbnail: {
    width: 68,
    height: 68,
    borderRadius: 10,
    backgroundColor: '#252525',
  },
  activityThumbnailPlaceholder: {
    width: 68,
    height: 68,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    backgroundColor: '#252525',
  },
  activityCopy: {
    flex: 1,
    minWidth: 160,
    gap: 2,
  },
  activityExercise: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '800',
  },
  activityMeta: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
  },
  activityStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginTop: 5,
  },
  activityStatus: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  activityStatusReady: {
    color: tokens.colors.brand,
  },
  activityActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    width: '100%',
    paddingTop: 2,
  },
  activityAction: {
    borderRadius: 8,
    backgroundColor: tokens.colors.brand,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  activityActionDisabled: {
    opacity: 0.6,
  },
  activityActionText: {
    color: tokens.colors.textPrimary,
    fontSize: 12,
    fontWeight: '800',
  },
  activityDeleteAction: {
    backgroundColor: '#5B2530',
  },
  activityDeleteActionText: {
    color: '#FFB7C1',
    fontSize: 12,
    fontWeight: '800',
  },
  activityError: {
    color: '#FFB4B4',
    fontSize: 12,
    lineHeight: 16,
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
