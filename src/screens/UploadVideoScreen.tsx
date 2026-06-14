import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import Constants, { AppOwnership } from 'expo-constants';
import { useEffect, useRef, useState } from 'react';
import { LayoutChangeEvent } from 'react-native';
import { Alert, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import {
  fetchAnalysisResult,
  fetchVideoStatus,
  testBackendConnection,
  triggerVideoAnalysis,
} from '../../lib/backendApi';
import {
  backendAuthRecoveryMessage,
  getFreshBackendAccessToken,
  isBackendAuthError,
} from '../../lib/backendAuth';
import {
  cleanupUploadedVideoForAnalysis,
  uploadVideoForAnalysis,
} from '../../lib/videoUpload';
import type { UploadVideoForAnalysisResult } from '../../lib/videoUpload';
import Button from '../components/Button';
import ConfirmationDialog from '../components/ConfirmationDialog';
import SelectedVideoPreview from '../components/SelectedVideoPreview';
import TrackingPinSetupModal from '../components/TrackingPinSetupModal';
import VideoSetupModal from '../components/VideoSetupModal';
import { supportsPinAssistedTracking, VideoSetupSelection } from '../constants/videoSetup';
import AnalysisReviewScreen from './AnalysisReviewScreen';
import { VideoAnalysisResult, VideoAnalysisStatus } from '../types/videoAnalysis';
import tokens from '../theme/tokens';
import type { TrackingSetup } from '../types/trackingSetup';
import { createLocalVideoThumbnail, getUriScheme } from '../utils/localVideoThumbnail';

type UploadVideoScreenProps = {
  onBack?: () => void;
  onAnalysisSaved?: () => void;
};

function formatFileSize(fileSize?: number | null) {
  // Present file sizes in the same units users expect from upload dialogs.
  if (typeof fileSize !== 'number') {
    return null;
  }

  return `${(fileSize / (1024 * 1024)).toFixed(1)} MB`;
}

function formatStatusLabel(status: VideoAnalysisStatus) {
  // Map backend status values to readable progress text.
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

function isAnalysisInProgress(status: VideoAnalysisStatus | null) {
  // Queue and processing are the two active analysis states.
  return status === 'queued' || status === 'processing';
}

function formatFlagLabel(value: string) {
  // Convert snake_case result flags into display labels.
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPercent(value?: number | null) {
  // Format quality metrics as percentages for the review summary.
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }

  return `${Math.round(value * 100)}%`;
}

export default function UploadVideoScreen({ onBack, onAnalysisSaved }: UploadVideoScreenProps) {
  // This screen handles selection, upload, queueing, and polling.
  const { user } = useAuth();
  const isWeb = Platform.select<boolean>({ web: true, default: false }) ?? false;
  const [permissionStatus, setPermissionStatus] = useState<ImagePicker.PermissionStatus | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [setupModalVisible, setSetupModalVisible] = useState(true);
  const [videoSetup, setVideoSetup] = useState<VideoSetupSelection | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [trackingSetup, setTrackingSetup] = useState<TrackingSetup | null>(null);
  const [trackingDetailsExpanded, setTrackingDetailsExpanded] = useState(false);
  const [trackingPinModalVisible, setTrackingPinModalVisible] = useState(false);
  const [removePinsDialogVisible, setRemovePinsDialogVisible] = useState(false);
  const [screenLayout, setScreenLayout] = useState({ width: 0, height: 0 });
  const [uploading, setUploading] = useState(false);
  const [analysisVideoId, setAnalysisVideoId] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<VideoAnalysisStatus | null>(null);
  const [analysisResult, setAnalysisResult] = useState<VideoAnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [quotaWarningMessage, setQuotaWarningMessage] = useState<string | null>(null);
  const [thumbnailUri, setThumbnailUri] = useState<string | null>(null);
  const [displayedVideoSizeBytes, setDisplayedVideoSizeBytes] = useState<number | null>(null);
  const analysisStartInFlightRef = useRef(false);
  const analysisQueuedForVideoRef = useRef<string | null>(null);

  const handleSelectedVideo = (asset: ImagePicker.ImagePickerAsset) => {
    // Selecting a new asset clears any old analysis state.
    analysisStartInFlightRef.current = false;
    analysisQueuedForVideoRef.current = null;
    setSelectedVideo(asset);
    setTrackingSetup(null);
    setTrackingDetailsExpanded(false);
    setTrackingPinModalVisible(false);
    setRemovePinsDialogVisible(false);
    setAnalysisVideoId(null);
    setAnalysisStatus(null);
    setAnalysisResult(null);
    setErrorMessage(null);
    setStatusMessage(null);
    setQuotaWarningMessage(null);
    setDisplayedVideoSizeBytes(
      typeof asset.fileSize === 'number' && !Number.isNaN(asset.fileSize) ? asset.fileSize : null
    );
  };

  const handleStartAnalysis = async () => {
    // Upload first, then ask the backend to begin analysis.
    if (analysisStartInFlightRef.current || uploading || isAnalysisInProgress(analysisStatus)) {
      return;
    }

    if (analysisResult) {
      setStatusMessage(null);
      setErrorMessage(null);
      return;
    }

    if (analysisVideoId && analysisQueuedForVideoRef.current === analysisVideoId) {
      return;
    }

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

    if (!user) {
      setStatusMessage(null);
      setErrorMessage('You must be logged in to upload and analyze a video.');
      return;
    }

    setErrorMessage(null);
    setStatusMessage(null);
    setQuotaWarningMessage(null);
    setUploading(true);
    analysisStartInFlightRef.current = true;
    let uploadedVideo: UploadVideoForAnalysisResult | null = null;

    try {
      // Start with a backend health check so failures are clearer.
      setStatusMessage('Checking backend connection...');
      await testBackendConnection();

      const uploadResult = await uploadVideoForAnalysis({
        asset: selectedVideo,
        exercise: videoSetup.exercise,
        angle: videoSetup.angle,
        trackingSetup,
        onStatusChange: setStatusMessage,
        onQuotaWarning: setQuotaWarningMessage,
      });
      uploadedVideo = uploadResult;

      setDisplayedVideoSizeBytes(uploadResult.uploadedFileSizeBytes);

      setStatusMessage('Starting analysis...');
      console.log('[analysis] starting backend analysis', uploadResult.videoId);
      const accessToken = await getFreshBackendAccessToken();
      const queuedResponse = await triggerVideoAnalysis(uploadResult.videoId, accessToken);
      analysisQueuedForVideoRef.current = uploadResult.videoId;
      setAnalysisVideoId(uploadResult.videoId);
      setAnalysisStatus(queuedResponse.status);
      setStatusMessage(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to upload and analyze this video.';
      const triggerFailedAfterUpload = Boolean(uploadedVideo);

      if (__DEV__) {
        console.warn('[analysis] upload or queue failed', {
          phase: uploadedVideo ? 'queue_analysis' : 'upload',
          videoId: uploadedVideo?.videoId ?? null,
          error,
        });
      }

      if (uploadedVideo) {
        // Clean up storage if analysis could not be queued.
        setStatusMessage('Cleaning up upload...');
        await cleanupUploadedVideoForAnalysis({
          videoId: uploadedVideo.videoId,
          storagePath: uploadedVideo.storagePath,
        });
        setAnalysisVideoId(null);
        setAnalysisStatus(null);
      }

      setStatusMessage(null);
      setErrorMessage(
        triggerFailedAfterUpload
          ? isBackendAuthError(error)
            ? backendAuthRecoveryMessage()
            : 'Upload succeeded, but analysis could not start. The upload was cleaned up; please try again.'
          : message.includes('row-level security policy')
          ? `${message}. Apply the latest videos RLS migration to your Supabase project.`
          : message
      );
      analysisStartInFlightRef.current = false;
    } finally {
      setUploading(false);
    }
  };

  const launchPicker = async () => {
    // The picker is guarded so it cannot open twice.
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
    // Fall back to settings when the app cannot prompt again.
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
    // Keep the cached gallery permission in sync with the OS.
    const currentPermission = await ImagePicker.getMediaLibraryPermissionsAsync();
    setPermissionStatus(currentPermission.status);
    return currentPermission;
  };

  const requestPermission = async (forcePrompt = false) => {
    // Web bypasses permissions because the browser owns file access.
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
    // Emit a warning if native compression is being tested in Expo Go.
    if (__DEV__ && Platform.OS === 'ios' && Constants.appOwnership === AppOwnership.Expo) {
      console.warn(
        '[UploadVideoScreen] Video compression requires a native iOS build. Expo Go will not support react-native-compressor. Rebuild with `npx expo run:ios`.'
      );
    }
  }, []);

  useEffect(() => {
    // Read the current permission once when the screen mounts.
    void syncPermissionStatus();
  }, []);

  useEffect(() => {
    // Generate a thumbnail for the selected clip when possible.
    if (!selectedVideo?.uri) {
      setThumbnailUri(null);
      return;
    }

    let active = true;
    setThumbnailUri(null);

    const generateThumbnail = async () => {
      try {
        const time = typeof selectedVideo.duration === 'number'
          ? Math.max(0, Math.min(selectedVideo.duration / 3, 1500))
          : 1000;
        const thumbnail = await createLocalVideoThumbnail(selectedVideo.uri, {
          timeMs: time,
          quality: 0.7,
        });

        if (!active) {
          return;
        }

        setThumbnailUri(thumbnail);
      } catch (error) {
        if (__DEV__) {
          console.warn('Unable to generate selected video thumbnail.', {
            platform: Platform.OS,
            uriScheme: getUriScheme(selectedVideo.uri),
            error,
          });
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
  }, [selectedVideo]);

  useEffect(() => {
    // Poll until the backend reports a final analysis state.
    if (!analysisVideoId || !user) {
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
        const accessToken = await getFreshBackendAccessToken();
        const statusResponse = await fetchVideoStatus(analysisVideoId, accessToken);

        if (!active) {
          return;
        }

        setAnalysisStatus(statusResponse.status);

        if (statusResponse.status === 'failed') {
          analysisStartInFlightRef.current = false;
          analysisQueuedForVideoRef.current = null;
          setStatusMessage(null);
          setErrorMessage('Analysis failed. Check the backend logs and try another upload.');
          return;
        }

        if (statusResponse.status === 'completed') {
          try {
            const analysisAccessToken = await getFreshBackendAccessToken();
            const analysisResponse = await fetchAnalysisResult(analysisVideoId, analysisAccessToken);

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

        if (active && isBackendAuthError(error)) {
          analysisStartInFlightRef.current = false;
          setStatusMessage(null);
          setErrorMessage('Your sign-in session expired while checking analysis status. Sign in again and reopen the upload.');
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
  }, [analysisResult, analysisStatus, analysisVideoId, user]);

  const handleModalContinue = async (selection: VideoSetupSelection) => {
    // Persist the exercise and view selection before upload starts.
    const setupChanged = videoSetup?.exercise !== selection.exercise || videoSetup?.angle !== selection.angle;
    setVideoSetup(selection);
    if (setupChanged) {
      setTrackingSetup(null);
      setTrackingDetailsExpanded(false);
      setRemovePinsDialogVisible(false);
    }
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
    // Permissions are requested only when the user explicitly taps upload.
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
    // Only a fully configured, idle upload can be sent to analysis.
    Boolean(selectedVideo && videoSetup) &&
    !uploading &&
    !isAnalysisInProgress(analysisStatus) &&
    analysisStatus !== 'completed';

  const handleScreenLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    // Track the viewport so the setup modal can fit correctly.
    const { width, height } = nativeEvent.layout;

    if (width === screenLayout.width && height === screenLayout.height) {
      return;
    }

    setScreenLayout({ width, height });
  };

  const handleReviewDiscarded = () => {
    // Clearing the review screen resets the upload flow.
    analysisStartInFlightRef.current = false;
    analysisQueuedForVideoRef.current = null;
    setSelectedVideo(null);
    setTrackingSetup(null);
    setTrackingDetailsExpanded(false);
    setTrackingPinModalVisible(false);
    setRemovePinsDialogVisible(false);
    setAnalysisVideoId(null);
    setAnalysisStatus(null);
    setAnalysisResult(null);
    setErrorMessage(null);
    setStatusMessage(null);
    setQuotaWarningMessage(null);
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
      <ConfirmationDialog
        visible={removePinsDialogVisible}
        title="Remove saved pins?"
        message="This video will use automatic tracking unless you place the pins again."
        confirmLabel="Remove Pins"
        destructive
        onConfirm={() => {
          setTrackingSetup(null);
          setRemovePinsDialogVisible(false);
          setErrorMessage(null);
          setStatusMessage(null);
        }}
        onCancel={() => setRemovePinsDialogVisible(false)}
      />
      {selectedVideo ? (
        <TrackingPinSetupModal
          visible={trackingPinModalVisible}
          videoUri={selectedVideo.uri}
          videoSize={{
            width: selectedVideo.width || 1080,
            height: selectedVideo.height || 1920,
          }}
          videoDurationMs={selectedVideo.duration ?? undefined}
          initialSetup={trackingSetup}
          onSave={(setup) => {
            setTrackingSetup(setup);
            setTrackingPinModalVisible(false);
          }}
          onCancel={() => setTrackingPinModalVisible(false)}
        />
      ) : null}

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

          {selectedVideo && supportsPinAssistedTracking(videoSetup) ? (
            <View style={styles.trackingSetupSection}>
              <View style={[styles.trackingSplitButton, uploading && styles.trackingSplitButtonDisabled]}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={trackingSetup ? 'Edit Pins' : 'Place Pins, optional'}
                  onPress={() => setTrackingPinModalVisible(true)}
                  disabled={uploading}
                  style={styles.trackingSplitMain}
                >
                  {trackingSetup ? (
                    <Ionicons name="checkmark-circle" size={20} color={tokens.colors.textPrimary} />
                  ) : null}
                  <Text style={styles.trackingSplitLabel}>
                    {trackingSetup ? 'Edit Pins' : 'Place Pins (Optional)'}
                  </Text>
                </Pressable>
                <View style={styles.trackingSplitDivider} />
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={trackingDetailsExpanded ? 'Hide pin details' : 'Show pin details'}
                  accessibilityState={{ expanded: trackingDetailsExpanded }}
                  onPress={() => setTrackingDetailsExpanded((value) => !value)}
                  disabled={uploading}
                  style={styles.trackingSplitToggle}
                >
                  <Ionicons
                    name={trackingDetailsExpanded ? 'chevron-up' : 'chevron-down'}
                    size={22}
                    color={tokens.colors.textPrimary}
                  />
                </Pressable>
              </View>
              {trackingDetailsExpanded ? (
                <View style={styles.trackingDetails}>
                  <Text style={styles.trackingSetupDescription}>
                    Place five pins on one clear frame to help the pose and barbell trackers stay locked on you.
                  </Text>
                  <Text style={styles.accuracyDisclaimer}>
                    Automatic tracking may be less accurate when joints or the barbell are obscured.
                  </Text>
                  {trackingSetup ? (
                    <Pressable
                      accessibilityRole="button"
                      onPress={() => setRemovePinsDialogVisible(true)}
                      disabled={uploading}
                      style={styles.removePinsButton}
                    >
                      <Text style={styles.removePinsText}>Remove saved pins</Text>
                    </Pressable>
                  ) : null}
                </View>
              ) : null}
            </View>
          ) : null}

          {selectedVideo ? (
            <View style={styles.actions}>
              <Button
                label="Choose Another Video"
                onPress={handlePickVideoPress}
                disabled={uploading}
                style={styles.primaryAction}
              />
              <Button
                label="Edit Video Setup"
                onPress={() => setSetupModalVisible(true)}
                disabled={uploading}
                style={styles.primaryAction}
              />
              {canStartAnalysis ? (
                <Button
                  label="Start Analysis"
                  onPress={() => {
                    void handleStartAnalysis();
                  }}
                  style={styles.primaryAction}
                />
              ) : null}
            </View>
          ) : null}

          {quotaWarningMessage ? (
            <Text style={styles.quotaWarningText}>{quotaWarningMessage}</Text>
          ) : null}

          {inlineMessage ? (
            <Text style={errorMessage ? styles.errorText : styles.inlineStatusText}>{inlineMessage}</Text>
          ) : null}

          {analysisResult ? (
            // The result card summarizes the completed backend response.
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
                      {formatFlagLabel(flag)}
                    </Text>
                  ))}
                </View>
              ) : null}

              {analysisResult.coach_feedback.length > 0 ? (
                <View style={styles.resultSection}>
                  <Text style={styles.resultLabel}>Coach feedback</Text>
                  {analysisResult.coach_feedback.map((feedback) => (
                    <Text key={feedback} style={styles.resultText}>
                      {feedback}
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

          {!selectedVideo ? (
            <View style={styles.actions}>
              <Button
                label="Choose Video"
                onPress={handlePickVideoPress}
                disabled={uploading}
                style={styles.primaryAction}
              />
              <Button
                label={videoSetup ? 'Edit Video Setup' : 'Open Video Setup'}
                onPress={() => setSetupModalVisible(true)}
                disabled={uploading}
                style={styles.primaryAction}
              />
            </View>
          ) : null}
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
  trackingSetupSection: {
    width: '100%',
    marginTop: 16,
    gap: 10,
  },
  trackingSplitButton: {
    width: '100%',
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'stretch',
    borderRadius: tokens.radii.button,
    backgroundColor: tokens.colors.brand,
    overflow: 'hidden',
  },
  trackingSplitButtonDisabled: { opacity: 0.6 },
  trackingSplitMain: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  trackingSplitLabel: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
    textAlign: 'center',
  },
  trackingSplitDivider: {
    width: StyleSheet.hairlineWidth,
    backgroundColor: 'rgba(255, 255, 255, 0.42)',
    marginVertical: 9,
  },
  trackingSplitToggle: {
    width: 52,
    alignItems: 'center',
    justifyContent: 'center',
  },
  trackingDetails: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#12161D',
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 10,
  },
  trackingSetupDescription: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  accuracyDisclaimer: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  removePinsButton: {
    alignSelf: 'flex-start',
    paddingVertical: 4,
  },
  removePinsText: {
    color: '#FF9A9A',
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
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
  quotaWarningText: {
    width: '100%',
    marginTop: 16,
    color: '#F4C66A',
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
  },
});
