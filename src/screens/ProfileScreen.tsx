import { Ionicons } from '@expo/vector-icons';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { describeBackendRequestFailure, getSavedVideos } from '../../lib/backendApi';
import { deriveUsernameFromUser, getProfileDisplayName, loadOwnProfile } from '../../lib/profile';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import tokens from '../theme/tokens';
import type { UserProfile } from '../../lib/profile';
import type { SavedVideo, VideoAnalysisRep } from '../types/videoAnalysis';
import { formatExerciseLabel, formatSavedDate } from '../utils/savedVideos';

type ProfileScreenProps = {
  onHomePress?: () => void;
  onAddPress?: () => void;
  onSettingsPress?: () => void;
  cachedSavedVideos?: SavedVideo[];
  savedVideosLoaded?: boolean;
  onSavedVideosLoaded?: (videos: SavedVideo[]) => void;
};

type DashboardMetric = {
  label: string;
  value: string;
  detail: string;
};

type Achievement = {
  label: string;
  detail: string;
  unlocked: boolean;
};

const ACHIEVEMENT_MILESTONES = {
  workouts: 5,
  reps: 25,
  liftTypes: 3,
};

function getVideoTimestamp(video: SavedVideo) {
  const timestamp = Date.parse(video.saved_at ?? video.created_at);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function getVideoReps(video: SavedVideo): VideoAnalysisRep[] {
  return video.analysis?.rep_data ?? video.analysis?.result_json?.reps ?? [];
}

function getVideoRepCount(video: SavedVideo) {
  const resultRepCount = video.analysis?.result_json?.rep_count;

  if (typeof resultRepCount === 'number') {
    return resultRepCount;
  }

  return getVideoReps(video).length;
}

function buildProfileStats(videos: SavedVideo[]) {
  const workouts = videos.length;
  const totalReps = videos.reduce((total, video) => total + getVideoRepCount(video), 0);
  const exerciseCounts = new Map<string, number>();

  for (const video of videos) {
    exerciseCounts.set(video.exercise_type, (exerciseCounts.get(video.exercise_type) ?? 0) + 1);
  }

  const latestVideo = [...videos].sort((left, right) => getVideoTimestamp(right) - getVideoTimestamp(left))[0];
  const mostTrainedLift = [...exerciseCounts.entries()].sort((left, right) => right[1] - left[1])[0];
  const liftTypeCount = exerciseCounts.size;
  const metrics: DashboardMetric[] = [
    {
      label: 'Recorded Workouts',
      value: `${workouts}`,
      detail: workouts === 1 ? 'saved lift' : 'saved lifts',
    },
    {
      label: 'Total Reps',
      value: `${totalReps}`,
      detail: 'from saved analyses',
    },
    {
      label: 'Latest Workout',
      value: latestVideo ? formatExerciseLabel(latestVideo.exercise_type) : 'N/A',
      detail: latestVideo ? formatSavedDate(latestVideo.saved_at ?? latestVideo.created_at) : 'save a lift',
    },
    {
      label: 'Most Trained Lift',
      value: mostTrainedLift ? formatExerciseLabel(mostTrainedLift[0]) : 'N/A',
      detail: mostTrainedLift ? `${mostTrainedLift[1]} recorded` : 'no workouts yet',
    },
  ];
  const achievements: Achievement[] = [
    {
      label: 'First Workout',
      detail: 'Save 1 workout',
      unlocked: workouts >= 1,
    },
    {
      label: 'Workout Stack',
      detail: `Save ${ACHIEVEMENT_MILESTONES.workouts} workouts`,
      unlocked: workouts >= ACHIEVEMENT_MILESTONES.workouts,
    },
    {
      label: 'Rep Builder',
      detail: `Record ${ACHIEVEMENT_MILESTONES.reps} total reps`,
      unlocked: totalReps >= ACHIEVEMENT_MILESTONES.reps,
    },
    {
      label: 'Lift Variety',
      detail: `Record ${ACHIEVEMENT_MILESTONES.liftTypes} lift types`,
      unlocked: liftTypeCount >= ACHIEVEMENT_MILESTONES.liftTypes,
    },
  ];

  return {
    workouts,
    totalReps,
    metrics,
    achievements,
  };
}

function DashboardCard({ metric }: { metric: DashboardMetric }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricValue} numberOfLines={1}>{metric.value}</Text>
      <Text style={styles.metricLabel} numberOfLines={2}>{metric.label}</Text>
      <Text style={styles.metricDetail} numberOfLines={2}>{metric.detail}</Text>
    </View>
  );
}

function AchievementRow({ achievement }: { achievement: Achievement }) {
  return (
    <View style={styles.achievementRow}>
      <View style={[styles.achievementIcon, achievement.unlocked && styles.achievementIconUnlocked]}>
        <Ionicons
          name={achievement.unlocked ? 'checkmark' : 'lock-closed-outline'}
          size={18}
          color={achievement.unlocked ? '#071018' : tokens.colors.textMuted}
        />
      </View>
      <View style={styles.achievementCopy}>
        <Text style={styles.achievementLabel}>{achievement.label}</Text>
        <Text style={styles.achievementDetail}>{achievement.detail}</Text>
      </View>
    </View>
  );
}

export default function ProfileScreen({
  onHomePress,
  onAddPress,
  onSettingsPress,
  cachedSavedVideos = [],
  savedVideosLoaded = false,
  onSavedVideosLoaded,
}: ProfileScreenProps) {
  const { session, user } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [videos, setVideos] = useState<SavedVideo[]>(cachedSavedVideos);
  const [profileLoading, setProfileLoading] = useState(true);
  const [videosLoading, setVideosLoading] = useState(!savedVideosLoaded);
  const [profileErrorMessage, setProfileErrorMessage] = useState<string | null>(null);
  const [videosErrorMessage, setVideosErrorMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadProfile = async () => {
      if (!session?.access_token || !user) {
        setProfileLoading(false);
        return;
      }

      setProfileLoading(true);
      setProfileErrorMessage(null);

      try {
        const nextProfile = await loadOwnProfile(user);

        if (cancelled) {
          return;
        }

        setProfile(nextProfile);
      } catch (error) {
        if (!cancelled) {
          setProfileErrorMessage(error instanceof Error ? error.message : 'Unable to load profile.');
        }
      } finally {
        if (!cancelled) {
          setProfileLoading(false);
        }
      }
    };

    void loadProfile();

    return () => {
      cancelled = true;
    };
  }, [session?.access_token, user, reloadKey]);

  useEffect(() => {
    if (!savedVideosLoaded) {
      return;
    }

    setVideos(cachedSavedVideos);
    setVideosErrorMessage(null);
    setVideosLoading(false);
  }, [cachedSavedVideos, savedVideosLoaded]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    const loadSavedVideoStats = async () => {
      if (!session?.access_token) {
        setVideos([]);
        setVideosLoading(false);
        onSavedVideosLoaded?.([]);
        return;
      }

      if (savedVideosLoaded && reloadKey === 0) {
        setVideosLoading(false);
        setVideosErrorMessage(null);
        return;
      }

      setVideosLoading(true);
      setVideosErrorMessage(null);

      try {
        const savedVideos = await getSavedVideos(session.access_token, controller.signal);

        if (cancelled) {
          return;
        }

        setVideos(savedVideos);
        onSavedVideosLoaded?.(savedVideos);
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          return;
        }

        const message = await describeBackendRequestFailure(
          error,
          'Unable to load saved video stats.'
        );

        if (!cancelled) {
          setVideosErrorMessage(message);
        }
      } finally {
        if (!cancelled) {
          setVideosLoading(false);
        }
      }
    };

    void loadSavedVideoStats();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [session?.access_token, reloadKey, savedVideosLoaded]);

  const stats = useMemo(() => buildProfileStats(videos), [videos]);
  const displayName = getProfileDisplayName(profile, user);
  const username = profile?.username || deriveUsernameFromUser(user) || 'username';
  const shouldAppendUsername = Boolean(
    username &&
      displayName.trim().split(/\s+/).length === 1 &&
      displayName.toLowerCase() !== username.toLowerCase(),
  );
  const profileName = shouldAppendUsername ? `${displayName} ${username}` : displayName;
  const showInitialStatsLoading = videosLoading && videos.length === 0;
  const showStats = !showInitialStatsLoading && (!videosErrorMessage || videos.length > 0);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.profileTop}>
            <View style={styles.identityRow}>
              <View style={styles.avatar}>
                {profile?.avatar_url ? (
                  <Image source={{ uri: profile.avatar_url }} style={styles.avatarImage} resizeMode="cover" />
                ) : (
                  <Ionicons name="person" size={44} color="#AEB7C6" />
                )}
              </View>
              <View style={styles.identityCopy}>
                <Text style={styles.displayName} numberOfLines={1}>{profileName}</Text>
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Open settings"
                onPress={onSettingsPress}
                hitSlop={8}
                style={styles.iconButton}
              >
                <Ionicons name="settings-outline" size={26} color={tokens.colors.textPrimary} />
              </Pressable>
            </View>
          </View>

          {profileLoading ? (
            <View style={styles.stateBlock}>
              <ActivityIndicator color={tokens.colors.brand} />
              <Text style={styles.stateText}>Loading profile...</Text>
            </View>
          ) : null}

          {!profileLoading && profileErrorMessage ? (
            <View style={styles.stateBlock}>
              <Text style={styles.errorText}>{profileErrorMessage}</Text>
              <Pressable accessibilityRole="button" onPress={() => setReloadKey((key) => key + 1)}>
                <Text style={styles.retryText}>Try Again</Text>
              </Pressable>
            </View>
          ) : null}

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Training Dashboard</Text>

            {showInitialStatsLoading ? (
              <View style={styles.inlineStateBlock}>
                <ActivityIndicator color={tokens.colors.brand} />
                <Text style={styles.stateText}>Loading saved video stats...</Text>
              </View>
            ) : null}

            {videosErrorMessage ? (
              <View style={styles.inlineStateBlock}>
                <Text style={styles.errorText}>{videosErrorMessage}</Text>
                <Pressable accessibilityRole="button" onPress={() => setReloadKey((key) => key + 1)}>
                  <Text style={styles.retryText}>Try Again</Text>
                </Pressable>
              </View>
            ) : null}

            {showStats ? (
              <View style={styles.metricsGrid}>
                {stats.metrics.map((metric) => (
                  <DashboardCard key={metric.label} metric={metric} />
                ))}
              </View>
            ) : null}
          </View>

          {showStats ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Achievements</Text>
              <View style={styles.achievementList}>
                {stats.achievements.map((achievement) => (
                  <AchievementRow key={achievement.label} achievement={achievement} />
                ))}
              </View>
            </View>
          ) : null}
        </ScrollView>

        <BottomNav
          activeTab="profile"
          onHomePress={onHomePress}
          onAddPress={onAddPress}
          onProfilePress={() => setReloadKey((key) => key + 1)}
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
    overflow: 'hidden',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 42,
    paddingBottom: NAV_HEIGHT + 36,
    gap: 22,
  },
  profileTop: {
    gap: 18,
  },
  iconButton: {
    width: 38,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
  },
  identityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  avatar: {
    width: 96,
    height: 96,
    borderRadius: 48,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#D8D8D8',
  },
  avatarImage: {
    width: '100%',
    height: '100%',
  },
  identityCopy: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  displayName: {
    color: tokens.colors.textPrimary,
    fontSize: 25,
    lineHeight: 31,
    fontWeight: '800',
  },
  section: {
    gap: 9,
  },
  sectionTitle: {
    color: tokens.colors.brand,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '800',
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  metricCard: {
    width: '48.5%',
    minHeight: 96,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2B3342',
    backgroundColor: '#15171B',
    padding: 11,
    justifyContent: 'space-between',
  },
  metricValue: {
    color: tokens.colors.textPrimary,
    fontSize: 23,
    lineHeight: 28,
    fontWeight: '800',
  },
  metricLabel: {
    color: tokens.colors.textPrimary,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  metricDetail: {
    color: tokens.colors.textMuted,
    fontSize: 11,
    lineHeight: 15,
  },
  achievementList: {
    gap: 9,
  },
  achievementRow: {
    minHeight: 64,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2B3342',
    backgroundColor: '#15171B',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 12,
  },
  achievementIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: '#384254',
    alignItems: 'center',
    justifyContent: 'center',
  },
  achievementIconUnlocked: {
    borderColor: tokens.colors.brand,
    backgroundColor: tokens.colors.brand,
  },
  achievementCopy: {
    flex: 1,
  },
  achievementLabel: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '700',
  },
  achievementDetail: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  stateBlock: {
    minHeight: 118,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 4,
  },
  inlineStateBlock: {
    minHeight: 76,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingVertical: 10,
  },
  stateText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
  },
  errorText: {
    color: '#FF8A8A',
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  retryText: {
    color: tokens.colors.brand,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '700',
  },
});
