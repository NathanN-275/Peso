import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as VideoThumbnails from 'expo-video-thumbnails';
import Constants, { AppOwnership } from 'expo-constants';
import { useEffect, useState } from 'react';
import { LayoutChangeEvent } from 'react-native';
import { Alert, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import {
  fetchAnalysisResult,
  fetchVideoStatus,
  triggerVideoAnalysis,
} from '../../lib/backendApi';
import { uploadVideoForAnalysis } from '../../lib/videoUpload';
import Button from '../components/Button';
import SelectedVideoPreview from '../components/SelectedVideoPreview';
import VideoSetupModal from '../components/VideoSetupModal';
import { VideoSetupSelection } from '../constants/videoSetup';
import AnalysisReviewScreen from './AnalysisReviewScreen';
import { VideoAnalysisResult, VideoAnalysisStatus } from '../types/videoAnalysis';
import tokens from '../theme/tokens';

type UploadVideoScreenProps = {
  onBack?: () => void;
  onAnalysisSaved?: () => void;
};

function formatFileSize(fileSize?: number | null) {
  if (typeof fileSize !== 'number') {
    return null;
  }

  return `${(fileSize / (1024 * 1024)).toFixed(1)} MB`;
}

function formatStatusLabel(status: VideoAnalysisStatus) {
  switch (status) {
    case 'uploaded':
      return 'Uploaded';
    case 'queued':
      return 'Queued for analysis';
    case 'processing':
      return 'Analyzing video';
    case 'completed':
      return 'Analysis complete';
    case 'failed':
      return 'Analysis failed';
    default:
      return status;
  }
}

function formatFlagLabel(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPercent(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }

  return `${Math.round(value * 100)}%`;
}

export default function UploadVideoScreen({ onBack, onAnalysisSaved }: UploadVideoScreenProps) {
  const { user, session } = useAuth();
  const isWeb = Platform.select<boolean>({ web: true, default: false }) ?? false;
  const [permissionStatus, setPermissionStatus] = useState<ImagePicker.PermissionStatus | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [setupModalVisible, setSetupModalVisible] = useState(true);
  const [videoSetup, setVideoSetup] = useState<VideoSetupSelection | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [screenLayout, setScreenLayout] = useState({ width: 0, height: 0 });
  const [uploading, setUploading] = useState(false);
  const [analysisVideoId, setAnalysisVideoId] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<VideoAnalysisStatus | null>(null);
  const [analysisResult, setAnalysisResult] = useState<VideoAnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [thumbnailUri, setThumbnailUri] = useState<string | null>(null);
  const [displayedVideoSizeBytes, setDisplayedVideoSizeBytes] = useState<number | null>(null);

  const handleSelectedVideo = (asset: ImagePicker.ImagePickerAsset) => {
    setSelectedVideo(asset);
    setAnalysisVideoId(null);
    setAnalysisStatus(null);
    setAnalysisResult(null);
    setErrorMessage(null);
    setStatusMessage(null);
    setDisplayedVideoSizeBytes(
      typeof asset.fileSize === 'number' && !Number.isNaN(asset.fileSize) ? asset.fileSize : null
    );
  };

  const handleStartAnalysis = async () => {
    if (!selectedVideo) {
      setStatusMessage(null);
      setErrorMessage('Choose a video before starting analysis.');
      return;
    }

    if (!videoSetup) {
      setSetupModalVisible(true);
      setStatusMessage(null);
      setErrorMessage('Select an exercise and camera angle before starting analysis.');
      return;
    }

    if (!user || !session?.access_token) {
      setStatusMessage(null);
      setErrorMessage('You must be logged in to upload and analyze a video.');
      return;
    }

    setErrorMessage(null);
    setStatusMessage(null);
    setUploading(true);

    try {
      const uploadResult = await uploadVideoForAnalysis({
        asset: selectedVideo,
        exercise: videoSetup.exercise,
        angle: videoSetup.angle,
        onStatusChange: setStatusMessage,
      });

      setDisplayedVideoSizeBytes(uploadResult.uploadedFileSizeBytes);
      setAnalysisVideoId(uploadResult.videoId);
      setAnalysisStatus(uploadResult.status);

      setStatusMessage('Starting analysis...');
      const queuedResponse = await triggerVideoAnalysis(uploadResult.videoId, session.access_token);
      setAnalysisStatus(queuedResponse.status);
      setStatusMessage(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to upload and analyze this video.';
      setStatusMessage(null);
      setErrorMessage(
        message.includes('row-level security policy')
          ? `${message}. Apply the latest videos RLS migration to your Supabase project.`
          : message
      );
    } finally {
      setUploading(false);
    }
  };

  const launchPicker = async () => {
    if (pickerOpen || uploading) {
      return;
    }

    setPickerOpen(true);

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
        allowsEditing: false,
        quality: 1,
        ...(Platform.OS === 'ios'
          ? {
              videoExportPreset: ImagePicker.VideoExportPreset.H264_1280x720,
            }
          : {}),
      });

      if (result.canceled) {
        return;
      }

      const nextAsset = result.assets[0];

      if (nextAsset) {
        handleSelectedVideo(nextAsset);
      }
    } finally {
      setPickerOpen(false);
    }
  };

  const promptForSettings = () => {
    Alert.alert(
      'Camera roll access needed',
      'Peso needs access to your camera roll to upload videos.',
      [
        {
          text: 'Accept',
          onPress: () => {
            void requestPermission(true);
          },
        },
        {
          text: 'Settings',
          onPress: () => {
            void Linking.openSettings();
          },
        },
      ],
      { cancelable: true }
    );
  };

  const syncPermissionStatus = async () => {
    const currentPermission = await ImagePicker.getMediaLibraryPermissionsAsync();
    setPermissionStatus(currentPermission.status);
    return currentPermission;
  };

  const requestPermission = async (forcePrompt = false) => {
    if (isWeb) {
      await launchPicker();
      return;
    }

    const currentPermission = await syncPermissionStatus();

    if (currentPermission.granted) {
      await launchPicker();
      return;
    }

    if (currentPermission.canAskAgain || forcePrompt) {
      const requestedPermission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      setPermissionStatus(requestedPermission.status);

      if (requestedPermission.granted) {
        await launchPicker();
        return;
      }
    }

    if (!isWeb) {
      promptForSettings();
    }
  };

  useEffect(() => {
    if (__DEV__ && Platform.OS === 'ios' && Constants.appOwnership === AppOwnership.Expo) {
      console.warn(
        '[UploadVideoScreen] Video compression requires a native iOS build. Expo Go will not support react-native-compressor. Rebuild with `npx expo run:ios`.'
      );
    }
  }, []);

  useEffect(() => {
    void syncPermissionStatus();
  }, []);

  useEffect(() => {
    if (!selectedVideo?.uri) {
      setThumbnailUri(null);
      return;
    }

    if (isWeb) {
      setThumbnailUri(null);
      return;
    }

    let active = true;

    const generateThumbnail = async () => {
      try {
        const time = typeof selectedVideo.duration === 'number'
          ? Math.max(0, Math.min(selectedVideo.duration / 3, 1500))
          : 1000;
        const thumbnail = await VideoThumbnails.getThumbnailAsync(selectedVideo.uri, {
          time,
          quality: 0.7,
        });

        if (!active) {
          return;
        }

        setThumbnailUri(thumbnail.uri);
      } catch (error) {
        if (__DEV__) {
          console.warn('Unable to generate video thumbnail.', error);
        }

        if (active) {
          setThumbnailUri(null);
        }
      }
    };

    void generateThumbnail();

    return () => {
      active = false;
    };
  }, [isWeb, selectedVideo]);

  useEffect(() => {
    if (!analysisVideoId || !session?.access_token) {
      return;
    }

    if (analysisStatus === 'failed') {
      return;
    }

    if (analysisStatus === 'completed' && analysisResult) {
      return;
    }

    let active = true;

    const poll = async () => {
      try {
        const statusResponse = await fetchVideoStatus(analysisVideoId, session.access_token);

        if (!active) {
          return;
        }

        setAnalysisStatus(statusResponse.status);

        if (statusResponse.status === 'failed') {
          setStatusMessage(null);
          setErrorMessage('Analysis failed. Check the backend logs and try another upload.');
          return;
        }

        if (statusResponse.status === 'completed') {
          try {
            const analysisResponse = await fetchAnalysisResult(analysisVideoId, session.access_token);

            if (!active) {
              return;
            }

            setAnalysisResult(analysisResponse.result_json);
          } catch (error) {
            if (__DEV__) {
              console.warn('Analysis result not ready yet.', error);
            }
          }
        }
      } catch (error) {
        if (__DEV__) {
          console.warn('Polling video analysis status failed.', error);
        }
      }
    };

    void poll();
    const intervalId = setInterval(() => {
      void poll();
    }, 4000);

    return () => {
      active = false;
      clearInterval(intervalId);
    };
  }, [analysisResult, analysisStatus, analysisVideoId, session?.access_token]);

  const handleModalContinue = async (selection: VideoSetupSelection) => {
    setVideoSetup(selection);
    setSetupModalVisible(false);
    setErrorMessage(null);
    setStatusMessage(null);

    if (!selectedVideo) {
      await requestPermission(true);
    }
  };

  const handleModalCancel = () => {
    if (onBack) {
      onBack();
      return;
    }

    setSetupModalVisible(false);
  };

  const handlePickVideoPress = () => {
    if (uploading) {
      return;
    }

    if (permissionStatus === 'granted') {
      void launchPicker();
      return;
    }

    void requestPermission(true);
  };

  const resolvedVideoName =
    selectedVideo?.fileName ?? selectedVideo?.uri.split('/').pop() ?? 'Selected video';
  const resolvedFileSize = formatFileSize(displayedVideoSizeBytes ?? selectedVideo?.fileSize);
  const inlineMessage = errorMessage ?? statusMessage;
  const diagnostics = analysisResult?.diagnostics;
  const videoQualityRows = diagnostics
    ? [
        ['Overall quality', formatPercent(diagnostics.quality_score)],
        ['Pose coverage', formatPercent(diagnostics.pose_coverage)],
        ['Lower body visibility', formatPercent(diagnostics.lower_body_visibility)],
        ['Side-view confidence', formatPercent(diagnostics.side_view_score)],
        [
          'Squat motion signal',
          typeof diagnostics.rep_detection?.motion_amplitude === 'number'
            ? diagnostics.rep_detection.motion_amplitude.toFixed(2)
            : null,
        ],
      ].filter((row): row is [string, string] => Boolean(row[1]))
    : [];
  const canStartAnalysis =
    Boolean(selectedVideo && videoSetup) &&
    !uploading &&
    analysisStatus !== 'queued' &&
    analysisStatus !== 'processing' &&
    analysisStatus !== 'completed';

  const handleScreenLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    const { width, height } = nativeEvent.layout;

    if (width === screenLayout.width && height === screenLayout.height) {
      return;
    }

    setScreenLayout({ width, height });
  };

  const handleReviewDiscarded = () => {
    setSelectedVideo(null);
    setAnalysisVideoId(null);
    setAnalysisStatus(null);
    setAnalysisResult(null);
    setErrorMessage(null);
    setStatusMessage(null);
    setThumbnailUri(null);
    setDisplayedVideoSizeBytes(null);
  };

  if (analysisResult && selectedVideo) {
    return (
      <AnalysisReviewScreen
        videoUri={selectedVideo.uri}
        result={analysisResult}
        onDiscarded={handleReviewDiscarded}
        onSaved={onAnalysisSaved ?? onBack ?? handleReviewDiscarded}
      />
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} onLayout={handleScreenLayout}>
      <VideoSetupModal
        visible={setupModalVisible}
        initialSelection={videoSetup}
        availableWidth={screenLayout.width || undefined}
        availableHeight={screenLayout.height || undefined}
        onContinue={(selection) => {
          void handleModalContinue(selection);
        }}
        onCancel={handleModalCancel}
      />

      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <Button label="Back" onPress={onBack} style={styles.backButton} />

        <View style={styles.content}>
          <Ionicons name="cloud-upload-outline" size={72} color={tokens.colors.textPrimary} />
          <Text style={styles.title}>Upload Video</Text>
          <Text style={styles.copy}>
            Confirm the exercise and camera angle, then select a video from your camera roll.
          </Text>

          {videoSetup ? (
            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>Selected setup</Text>
              <View style={styles.badgesRow}>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{videoSetup.exercise}</Text>
                </View>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{videoSetup.angle}</Text>
                </View>
              </View>
            </View>
          ) : null}

          {selectedVideo ? (
            <View style={styles.videoCard}>
              <View style={styles.videoCardHeader}>
                <View style={styles.videoCardInfo}>
                  <Text style={styles.videoCardLabel}>Selected video</Text>
                  <Text style={styles.videoCardName}>{resolvedVideoName}</Text>
                  {resolvedFileSize ? <Text style={styles.videoCardMeta}>{resolvedFileSize}</Text> : null}
                  {analysisVideoId ? <Text style={styles.videoCardMeta}>Video ID: {analysisVideoId}</Text> : null}
                  {analysisStatus ? (
                    <Text style={styles.statusText}>Status: {formatStatusLabel(analysisStatus)}</Text>
                  ) : null}
                </View>

                <View style={styles.thumbnailFrame}>
                  <SelectedVideoPreview
                    videoUri={selectedVideo.uri}
                    thumbnailUri={thumbnailUri}
                  />
                </View>
              </View>
            </View>
          ) : null}

          {canStartAnalysis ? (
            <Button
              label="Start Analysis"
              onPress={() => {
                void handleStartAnalysis();
              }}
              style={styles.startAnalysisButton}
            />
          ) : null}

          {inlineMessage ? (
            <Text style={errorMessage ? styles.errorText : styles.inlineStatusText}>{inlineMessage}</Text>
          ) : null}

          {analysisResult ? (
            <View style={styles.resultCard}>
              <Text style={styles.summaryTitle}>Analysis result</Text>
              <Text style={styles.resultHeadline}>
                {analysisResult.analysis_limited ? 'Limited analysis' : `${analysisResult.rep_count} reps detected`}
              </Text>

              {analysisResult.summary_flags.length > 0 ? (
                <View style={styles.resultSection}>
                  <Text style={styles.resultLabel}>Summary flags</Text>
                  {analysisResult.summary_flags.map((flag) => (
                    <Text key={flag} style={styles.resultText}>
                      {`\u2022 ${formatFlagLabel(flag)}`}
                    </Text>
                  ))}
                </View>
              ) : null}

              {analysisResult.coach_feedback.length > 0 ? (
                <View style={styles.resultSection}>
                  <Text style={styles.resultLabel}>Coach feedback</Text>
                  {analysisResult.coach_feedback.map((feedback) => (
                    <Text key={feedback} style={styles.resultText}>
                      {`\u2022 ${feedback}`}
                    </Text>
                  ))}
                </View>
              ) : null}

              {videoQualityRows.length > 0 ? (
                <View style={styles.resultSection}>
                  <Text style={styles.resultLabel}>Video quality</Text>
                  {videoQualityRows.map(([label, value]) => (
                    <Text key={label} style={styles.resultText}>
                      {label}: {value}
                    </Text>
                  ))}
                  {diagnostics?.quality_flags?.length ? (
                    <Text style={styles.resultMutedText}>
                      Flags: {diagnostics.quality_flags.map(formatFlagLabel).join(', ')}
                    </Text>
                  ) : null}
                </View>
              ) : null}

              {analysisResult.reps.length > 0 ? (
                <View style={styles.resultSection}>
                  <Text style={styles.resultLabel}>Per-rep highlights</Text>
                  {analysisResult.reps.map((rep) => (
                    <Text key={rep.rep_index} style={styles.resultText}>
                      Rep {rep.rep_index}: depth {rep.depth_score.toFixed(2)}, torso change{' '}
                      {rep.torso_angle_change.toFixed(1)}°
                    </Text>
                  ))}
                </View>
              ) : null}
            </View>
          ) : null}

          <View style={styles.actions}>
            <Button
              label={selectedVideo ? 'Choose Another Video' : 'Choose Video'}
              onPress={handlePickVideoPress}
              disabled={uploading}
              style={styles.primaryAction}
            />
            <Pressable
              accessibilityRole="button"
              onPress={() => setSetupModalVisible(true)}
              style={styles.secondaryAction}
            >
              <Text style={styles.secondaryActionText}>
                {videoSetup ? 'Edit Video Setup' : 'Open Video Setup'}
              </Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
    position: 'relative',
  },
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 16,
    paddingBottom: 56,
  },
  backButton: {
    width: 80,
    minHeight: 36,
    alignSelf: 'flex-start',
    marginTop: 12,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: '#3B6EEA',
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'flex-start',
    paddingHorizontal: 28,
    paddingTop: 44,
    paddingBottom: 32,
  },
  title: {
    marginTop: 22,
    color: tokens.colors.textPrimary,
    fontSize: 26,
    lineHeight: 32,
    fontWeight: '700',
    textAlign: 'center',
  },
  copy: {
    marginTop: 18,
    color: '#E6E6E6',
    fontSize: 16,
    lineHeight: 25,
    fontWeight: '500',
    textAlign: 'center',
    maxWidth: 292,
  },
  summaryCard: {
    width: '100%',
    marginTop: 26,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#12161D',
    paddingHorizontal: 18,
    paddingVertical: 18,
    gap: 14,
  },
  summaryTitle: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  badgesRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  badge: {
    borderRadius: 999,
    backgroundColor: '#1A2432',
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  badgeText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '600',
  },
  videoCard: {
    width: '100%',
    marginTop: 16,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0F1218',
    paddingHorizontal: 18,
    paddingVertical: 16,
  },
  videoCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
  },
  videoCardInfo: {
    flex: 1,
    gap: 6,
  },
  videoCardLabel: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  videoCardName: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
  },
  videoCardMeta: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  statusText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    marginTop: 4,
  },
  thumbnailFrame: {
    width: 88,
    height: 88,
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#151A22',
    flexShrink: 0,
  },
  startAnalysisButton: {
    width: '100%',
    maxWidth: 320,
    marginTop: 12,
  },
  errorText: {
    width: '100%',
    marginTop: 16,
    color: '#FF8A8A',
    fontSize: 14,
    lineHeight: 20,
  },
  inlineStatusText: {
    width: '100%',
    marginTop: 16,
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  resultCard: {
    width: '100%',
    marginTop: 18,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#12161D',
    paddingHorizontal: 18,
    paddingVertical: 18,
    gap: 12,
  },
  resultHeadline: {
    color: tokens.colors.textPrimary,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '700',
  },
  resultSection: {
    gap: 6,
  },
  resultLabel: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  resultText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
  },
  resultMutedText: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  actions: {
    width: '100%',
    marginTop: 14,
    gap: 12,
  },
  primaryAction: {
    width: '100%',
    maxWidth: 320,
  },
  secondaryAction: {
    alignSelf: 'center',
    paddingVertical: 8,
  },
  secondaryActionText: {
    color: tokens.colors.textMuted,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '600',
  },
});
