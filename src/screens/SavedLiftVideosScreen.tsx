import { Ionicons } from '@expo/vector-icons';
import { File, Paths } from 'expo-file-system';
import * as MediaLibrary from 'expo-media-library';
import { VideoView, useVideoPlayer } from 'expo-video';
import * as VideoThumbnails from 'expo-video-thumbnails';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { SavedVideo } from '../../lib/backendApi';
import tokens from '../theme/tokens';
import {
  formatExerciseLabel,
  formatSavedDate,
  formatViewLabel,
  getSavedVideoSummary,
} from '../utils/savedVideos';

type SortOrder = 'newest' | 'oldest';

type SavedLiftVideosScreenProps = {
  exerciseType: string;
  videos: SavedVideo[];
  onBack: () => void;
  onOpenSavedVideo: (video: SavedVideo) => void;
  onDeleteSavedVideos: (videoIds: string[]) => Promise<void>;
};

function getVideoTimestamp(video: SavedVideo) {
  const timestamp = Date.parse(video.saved_at ?? video.created_at);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function getSelectionLabel(count: number) {
  return `${count} ${count === 1 ? 'Video' : 'Videos'} Selected`;
}

function getExportExtension(video: SavedVideo) {
  const path = video.storage_path.split('?')[0] ?? '';
  const match = path.match(/\.(mp4|mov|m4v|webm)$/i);
  return match?.[0] ?? '.mp4';
}

function getExportFileName(video: SavedVideo, index: number) {
  const exercise = formatExerciseLabel(video.exercise_type).replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '');
  return `peso-${exercise || 'video'}-${video.id.slice(0, 8)}-${index + 1}${getExportExtension(video)}`;
}

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
  onDeleteSavedVideos,
}: SavedLiftVideosScreenProps) {
  const title = formatExerciseLabel(exerciseType);
  const [sortOrder, setSortOrder] = useState<SortOrder>('newest');
  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const sortedVideos = useMemo(() => {
    return [...videos].sort((left, right) => {
      const diff = getVideoTimestamp(right) - getVideoTimestamp(left);
      return sortOrder === 'newest' ? diff : -diff;
    });
  }, [sortOrder, videos]);

  const selectedVideos = useMemo(
    () => sortedVideos.filter((video) => selectedIds.has(video.id)),
    [selectedIds, sortedVideos]
  );

  useEffect(() => {
    setSelectedIds((currentIds) => {
      const availableIds = new Set(videos.map((video) => video.id));
      const nextIds = new Set([...currentIds].filter((id) => availableIds.has(id)));
      return nextIds.size === currentIds.size ? currentIds : nextIds;
    });
  }, [videos]);

  const clearSelection = () => {
    setSelecting(false);
    setSelectedIds(new Set());
    setActionMessage(null);
  };

  const toggleSelected = (videoId: string) => {
    setActionMessage(null);
    setSelectedIds((currentIds) => {
      const nextIds = new Set(currentIds);

      if (nextIds.has(videoId)) {
        nextIds.delete(videoId);
      } else {
        nextIds.add(videoId);
      }

      return nextIds;
    });
  };

  const handleVideoPress = (video: SavedVideo) => {
    if (selecting) {
      toggleSelected(video.id);
      return;
    }

    onOpenSavedVideo(video);
  };

  const handleExportSelected = async () => {
    if (exporting || selectedVideos.length === 0) {
      return;
    }

    setExporting(true);
    setActionMessage(null);

    try {
      if (Platform.OS === 'web') {
        const webGlobal = globalThis as typeof globalThis & {
          open?: (url?: string | URL, target?: string) => Window | null;
        };

        selectedVideos.forEach((video) => {
          webGlobal.open?.(video.video_url, '_blank');
        });
        setActionMessage(`Opened ${selectedVideos.length} ${selectedVideos.length === 1 ? 'video' : 'videos'} for download.`);
        return;
      }

      const available = await MediaLibrary.isAvailableAsync();

      if (!available) {
        throw new Error('Saving to the media library is not available on this device.');
      }

      let permission = await MediaLibrary.getPermissionsAsync(true, ['video']);

      if (!permission.granted) {
        permission = await MediaLibrary.requestPermissionsAsync(true, ['video']);
      }

      if (!permission.granted) {
        throw new Error('Peso needs permission to save videos to your photo library.');
      }

      for (const [index, video] of selectedVideos.entries()) {
        const destination = new File(Paths.cache, getExportFileName(video, index));
        const downloadedFile = await File.downloadFileAsync(video.video_url, destination, {
          idempotent: true,
        });

        await MediaLibrary.saveToLibraryAsync(downloadedFile.uri);

        try {
          downloadedFile.delete();
        } catch {
          // Cache cleanup is best-effort after the video is in the media library.
        }
      }

      setActionMessage(`Saved ${selectedVideos.length} ${selectedVideos.length === 1 ? 'video' : 'videos'} to your device.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : 'Unable to export selected videos.');
    } finally {
      setExporting(false);
    }
  };

  const handleDeleteSelected = async () => {
    if (deleting || selectedVideos.length === 0) {
      return;
    }

    setDeleting(true);
    setActionMessage(null);

    const failedIds: string[] = [];

    for (const video of selectedVideos) {
      try {
        await onDeleteSavedVideos([video.id]);
      } catch {
        failedIds.push(video.id);
      }
    }

    setDeleting(false);
    setShowDeleteModal(false);

    if (failedIds.length === 0) {
      clearSelection();
      return;
    }

    setSelectedIds(new Set(failedIds));
    setActionMessage(
      `Deleted ${selectedVideos.length - failedIds.length} ${selectedVideos.length - failedIds.length === 1 ? 'video' : 'videos'}, but ${failedIds.length} failed.`
    );
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" onPress={onBack} style={styles.backButton}>
            <Text style={styles.backButtonText}>Back</Text>
          </Pressable>
          <Text style={styles.title}>{title}</Text>
          <Pressable
            accessibilityRole="button"
            onPress={selecting ? clearSelection : () => setSelecting(true)}
            style={styles.selectButton}
          >
            <Text style={styles.selectButtonText}>{selecting ? 'Cancel' : 'Select'}</Text>
          </Pressable>
        </View>

        <View style={styles.controlRow}>
          <Pressable
            accessibilityRole="button"
            onPress={() => setSortOrder((currentOrder) => (currentOrder === 'newest' ? 'oldest' : 'newest'))}
            style={styles.filterButton}
          >
            <Ionicons name="filter" size={17} color={tokens.colors.brand} />
            <Text style={styles.filterButtonText}>
              {sortOrder === 'newest' ? 'Newest First' : 'Oldest First'}
            </Text>
          </Pressable>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={[
            styles.scrollContent,
            selecting && styles.scrollContentWithSelectionBar,
          ]}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.countText}>
            {videos.length} saved {videos.length === 1 ? 'video' : 'videos'}
          </Text>

          {actionMessage ? <Text style={styles.actionMessage}>{actionMessage}</Text> : null}

          {videos.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>No saved videos</Text>
              <Text style={styles.emptyCopy}>Saved {title} videos will appear here.</Text>
            </View>
          ) : (
            <View style={styles.videoList}>
              {sortedVideos.map((video) => {
                const selected = selectedIds.has(video.id);

                return (
                  <Pressable
                    key={video.id}
                    accessibilityRole="button"
                    onPress={() => handleVideoPress(video)}
                    style={[styles.videoCard, selected && styles.selectedVideoCard]}
                  >
                    <View style={styles.thumbnailWrap}>
                      <SavedVideoThumb video={video} />
                      {selecting ? (
                        <View style={[styles.selectionBadge, selected && styles.selectionBadgeActive]}>
                          {selected ? (
                            <Ionicons name="checkmark" size={15} color={tokens.colors.textPrimary} />
                          ) : null}
                        </View>
                      ) : null}
                    </View>
                    <View style={styles.videoInfo}>
                      <Text style={styles.videoTitle}>{formatExerciseLabel(video.exercise_type)}</Text>
                      <Text style={styles.videoMeta}>{formatViewLabel(video.view_type)} view</Text>
                      <Text style={styles.videoMeta}>{formatSavedDate(video.saved_at)}</Text>
                      <Text style={styles.videoSummary} numberOfLines={2}>
                        {getSavedVideoSummary(video)}
                      </Text>
                    </View>
                    {selecting ? null : (
                      <Ionicons name="chevron-forward" size={22} color={tokens.colors.textMuted} />
                    )}
                  </Pressable>
                );
              })}
            </View>
          )}
        </ScrollView>

        {selecting ? (
          <View style={styles.selectionBar}>
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                void handleExportSelected();
              }}
              disabled={exporting || selectedVideos.length === 0}
              style={[styles.selectionIconButton, (exporting || selectedVideos.length === 0) && styles.disabledButton]}
            >
              {exporting ? (
                <ActivityIndicator color={tokens.colors.textPrimary} />
              ) : (
                <Ionicons name="share-outline" size={34} color={tokens.colors.textPrimary} />
              )}
            </Pressable>

            <Text style={styles.selectionCountText}>{getSelectionLabel(selectedIds.size)}</Text>

            <Pressable
              accessibilityRole="button"
              onPress={() => setShowDeleteModal(true)}
              disabled={deleting || selectedVideos.length === 0}
              style={[styles.selectionIconButton, (deleting || selectedVideos.length === 0) && styles.disabledButton]}
            >
              {deleting ? (
                <ActivityIndicator color={tokens.colors.textPrimary} />
              ) : (
                <Ionicons name="trash-outline" size={34} color={tokens.colors.textPrimary} />
              )}
            </Pressable>
          </View>
        ) : null}

        <Modal
          animationType="fade"
          transparent
          visible={showDeleteModal}
          onRequestClose={() => {
            if (!deleting) {
              setShowDeleteModal(false);
            }
          }}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.confirmModal}>
              <Text style={styles.confirmTitle}>
                Delete {selectedVideos.length === 1 ? 'Video' : 'Videos'}?
              </Text>
              <Text style={styles.confirmCopy}>
                This permanently removes {selectedVideos.length === 1 ? 'this saved video' : 'these saved videos'} from your library.
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  void handleDeleteSelected();
                }}
                disabled={deleting}
                style={[styles.confirmDeleteButton, deleting && styles.disabledButton]}
              >
                {deleting ? (
                  <ActivityIndicator color={tokens.colors.textPrimary} />
                ) : (
                  <Text style={styles.confirmDeleteText}>
                    {selectedVideos.length === 1 ? 'Delete Video' : 'Delete Videos'}
                  </Text>
                )}
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => setShowDeleteModal(false)}
                disabled={deleting}
                style={[styles.confirmCancelButton, deleting && styles.disabledButton]}
              >
                <Text style={styles.confirmCancelText}>Cancel</Text>
              </Pressable>
            </View>
          </View>
        </Modal>
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
  selectButton: {
    minWidth: 72,
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    backgroundColor: '#1B3F8D',
  },
  selectButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 19,
    fontWeight: '800',
  },
  controlRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingHorizontal: 22,
    paddingBottom: 12,
  },
  filterButton: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#293C66',
    backgroundColor: '#101725',
    paddingHorizontal: 12,
  },
  filterButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '700',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 22,
    paddingBottom: 30,
  },
  scrollContentWithSelectionBar: {
    paddingBottom: 126,
  },
  countText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 12,
  },
  actionMessage: {
    color: '#DADADA',
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 12,
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
  selectedVideoCard: {
    borderColor: tokens.colors.brand,
  },
  thumbnailWrap: {
    position: 'relative',
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
  selectionBadge: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: tokens.colors.textPrimary,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
  },
  selectionBadgeActive: {
    borderColor: tokens.colors.brand,
    backgroundColor: tokens.colors.brand,
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
  selectionBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    minHeight: 102,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: '#1E1E1E',
    backgroundColor: '#000',
    paddingHorizontal: 40,
    paddingTop: 12,
    paddingBottom: 18,
  },
  selectionIconButton: {
    width: 70,
    height: 70,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 35,
    borderWidth: 1,
    borderColor: '#2C2C2C',
    backgroundColor: '#151515',
  },
  selectionCountText: {
    flex: 1,
    color: tokens.colors.textPrimary,
    fontSize: 21,
    lineHeight: 27,
    fontWeight: '800',
    textAlign: 'center',
    paddingHorizontal: 12,
  },
  disabledButton: {
    opacity: 0.55,
  },
  modalOverlay: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.72)',
    padding: 24,
  },
  confirmModal: {
    width: '100%',
    maxWidth: 340,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#343434',
    backgroundColor: '#202020',
    padding: 18,
    gap: 12,
  },
  confirmTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 20,
    lineHeight: 26,
    fontWeight: '800',
    textAlign: 'center',
  },
  confirmCopy: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  confirmDeleteButton: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#D93025',
    paddingHorizontal: 16,
  },
  confirmDeleteText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '800',
  },
  confirmCancelButton: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#4A4A4A',
    backgroundColor: '#2A2A2A',
    paddingHorizontal: 16,
  },
  confirmCancelText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '700',
  },
});
