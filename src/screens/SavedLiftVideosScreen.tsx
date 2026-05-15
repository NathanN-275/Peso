import { Ionicons } from '@expo/vector-icons';
import { VideoView, useVideoPlayer } from 'expo-video';
import * as VideoThumbnails from 'expo-video-thumbnails';
import { useEffect, useState } from 'react';
import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { SavedVideo } from '../../lib/backendApi';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import tokens from '../theme/tokens';
import {
  formatExerciseLabel,
  formatSavedDate,
  formatViewLabel,
  getSavedVideoSummary,
} from '../utils/savedVideos';

type SavedLiftVideosScreenProps = {
  exerciseType: string;
  videos: SavedVideo[];
  onBack: () => void;
  onOpenSavedVideo: (video: SavedVideo) => void;
  onHomePress?: () => void;
  onAddPress?: () => void;
};

function SavedVideoFramePreview({ videoUrl }: { videoUrl: string }) {
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
      style={styles.thumbnailImage}
      player={player}
      nativeControls={false}
      allowsPictureInPicture={false}
      contentFit="cover"
    />
  );
}

function SavedVideoThumb({ video }: { video: SavedVideo }) {
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
          console.warn('Unable to generate saved list video preview thumbnail.', error);
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
        style={styles.thumbnailImage}
        resizeMode="cover"
        onError={() => setThumbnailLoadFailed(true)}
      />
    );
  }

  if (generatedThumbnailUri) {
    return (
      <Image
        source={{ uri: generatedThumbnailUri }}
        style={styles.thumbnailImage}
        resizeMode="cover"
      />
    );
  }

  if (video.video_url) {
    return <SavedVideoFramePreview videoUrl={video.video_url} />;
  }

  return <View style={styles.thumbnailPlaceholder} />;
}

export default function SavedLiftVideosScreen({
  exerciseType,
  videos,
  onBack,
  onOpenSavedVideo,
  onHomePress,
  onAddPress,
}: SavedLiftVideosScreenProps) {
  const title = formatExerciseLabel(exerciseType);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" onPress={onBack} style={styles.backButton}>
            <Text style={styles.backButtonText}>Back</Text>
          </Pressable>
          <Text style={styles.title}>{title}</Text>
          <View style={styles.topSpacer} />
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.countText}>
            {videos.length} saved {videos.length === 1 ? 'video' : 'videos'}
          </Text>

          {videos.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>No saved videos</Text>
              <Text style={styles.emptyCopy}>Saved {title} videos will appear here.</Text>
            </View>
          ) : (
            <View style={styles.videoList}>
              {videos.map((video) => (
                <Pressable
                  key={video.id}
                  accessibilityRole="button"
                  onPress={() => onOpenSavedVideo(video)}
                  style={styles.videoCard}
                >
                  <SavedVideoThumb video={video} />
                  <View style={styles.videoInfo}>
                    <Text style={styles.videoTitle}>{formatExerciseLabel(video.exercise_type)}</Text>
                    <Text style={styles.videoMeta}>{formatViewLabel(video.view_type)} view</Text>
                    <Text style={styles.videoMeta}>{formatSavedDate(video.saved_at)}</Text>
                    <Text style={styles.videoSummary} numberOfLines={2}>
                      {getSavedVideoSummary(video)}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={22} color={tokens.colors.textMuted} />
                </Pressable>
              ))}
            </View>
          )}
        </ScrollView>

        <BottomNav activeTab="home" onHomePress={onHomePress} onAddPress={onAddPress} />
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
  topBar: {
    minHeight: 78,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 6,
  },
  backButton: {
    minWidth: 72,
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    backgroundColor: tokens.colors.brand,
  },
  backButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 19,
    fontWeight: '800',
  },
  title: {
    flex: 1,
    color: tokens.colors.brand,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '800',
    textAlign: 'center',
    marginHorizontal: 12,
  },
  topSpacer: {
    width: 72,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 22,
    paddingBottom: NAV_HEIGHT + 30,
  },
  countText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 16,
  },
  videoList: {
    gap: 14,
  },
  videoCard: {
    minHeight: 118,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#343434',
    backgroundColor: '#202020',
    padding: 12,
  },
  thumbnailImage: {
    width: 82,
    height: 94,
    borderRadius: 12,
    backgroundColor: '#5C5C5C',
  },
  thumbnailPlaceholder: {
    width: 82,
    height: 94,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#5C5C5C',
  },
  videoInfo: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  videoTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 18,
    lineHeight: 23,
    fontWeight: '800',
  },
  videoMeta: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  videoSummary: {
    color: '#DADADA',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 4,
  },
  emptyState: {
    minHeight: 360,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 22,
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
});
