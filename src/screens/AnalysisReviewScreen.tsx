import { Ionicons } from '@expo/vector-icons';
import { useEvent } from 'expo';
import { VideoView, useVideoPlayer } from 'expo-video';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  LayoutChangeEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { discardAnalyzedVideo, saveAnalyzedVideo } from '../../lib/backendApi';
import PoseOverlay from '../components/PoseOverlay';
import ReviewBottomSheet from '../components/ReviewBottomSheet';
import TimelineScrubber from '../components/TimelineScrubber';
import tokens from '../theme/tokens';
import { VideoAnalysisResult } from '../types/videoAnalysis';
import {
  findClosestPoseFrame,
  formatPercent,
  getRepDuration,
  getRepSpeed,
  getRepVelocity,
  normalizeCoachingFeedback,
  normalizeResultFlags,
  normalizeVideoQuality,
} from '../utils/videoReview';

type AnalysisReviewScreenProps = {
  videoUri: string;
  result: VideoAnalysisResult;
  mode?: 'pending' | 'saved';
  onBack?: () => void;
  onDiscarded?: () => void;
  onSaved?: () => void;
};

function formatFlagLabel(value: string) {
  // Turn backend enum strings into readable labels.
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value: number, suffix = '') {
  // Keep numeric debug values compact on screen.
  if (!Number.isFinite(value)) {
    return `0${suffix}`;
  }

  return `${value.toFixed(2)}${suffix}`;
}

function formatOptionalNumber(value: number | undefined, suffix = '') {
  if (typeof value !== 'number') {
    return `n/a${suffix}`;
  }

  return formatNumber(value, suffix);
}

function formatMilliseconds(value: number | undefined) {
  if (typeof value !== 'number') {
    return 'n/a';
  }

  return `${(value / 1000).toFixed(2)}s`;
}

function formatDepthStatus(value: string | undefined) {
  if (!value) {
    return 'Unknown';
  }

  return formatFlagLabel(value);
}

function SheetSection({ title, children }: { title: string; children: React.ReactNode }) {
  // Shared block for the review sheet sections.
  return (
    <View style={styles.sheetSection}>
      <Text style={styles.sheetLabel}>{title}</Text>
      {children}
    </View>
  );
}

export default function AnalysisReviewScreen({
  videoUri,
  result,
  mode = 'pending',
  onBack,
  onDiscarded,
  onSaved,
}: AnalysisReviewScreenProps) {
  // This screen plays the analyzed clip and overlays pose feedback.
  const { session } = useAuth();
  const isSavedMode = mode === 'saved';
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(result.duration ?? 0);
  const [videoLayout, setVideoLayout] = useState({ width: 0, height: 0 });
  const [activeSheet, setActiveSheet] = useState<'summary' | 'coaching' | null>(null);
  const [saving, setSaving] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showDiscardSheet, setShowDiscardSheet] = useState(false);
  const [wasPlayingBeforeScrub, setWasPlayingBeforeScrub] = useState(false);

  const player = useVideoPlayer(videoUri, (videoPlayer) => {
    // Configure playback for review mode instead of normal video controls.
    videoPlayer.loop = false;
    videoPlayer.muted = true;
    videoPlayer.timeUpdateEventInterval = 0.05;
  });
  const { isPlaying } = useEvent(player, 'playingChange', { isPlaying: player.playing });
  const { status, error } = useEvent(player, 'statusChange', {
    status: player.status,
    oldStatus: undefined,
    error: undefined,
  });
  const timeUpdate = useEvent(player, 'timeUpdate', {
    currentTime: 0,
    currentLiveTimestamp: null,
    currentOffsetFromLive: null,
    bufferedPosition: 0,
  });
  const sourceLoad = useEvent(player, 'sourceLoad', {
    videoSource: null,
    duration: result.duration ?? 0,
    availableVideoTracks: [],
    availableSubtitleTracks: [],
    availableAudioTracks: [],
  });

  useEffect(() => {
    // Keep the scrubber state in sync with the native player clock.
    setCurrentTime(timeUpdate.currentTime);
  }, [timeUpdate.currentTime]);

  useEffect(() => {
    const nextDuration = sourceLoad.duration || player.duration || result.duration || 0;

    if (nextDuration > 0) {
      setDuration(nextDuration);
    }
  }, [player.duration, result.duration, sourceLoad.duration]);

  useEffect(() => {
    if (error?.message) {
      setErrorMessage(error.message);
    }
  }, [error?.message]);

  const poseFrame = useMemo(
    () => findClosestPoseFrame(result.poseFrames, currentTime),
    [currentTime, result.poseFrames]
  );
  const videoSize = {
    width: result.videoWidth || 1080,
    height: result.videoHeight || 1920,
  };
  const summaryFlags = normalizeResultFlags(result);
  const coachingFeedback = normalizeCoachingFeedback(result);
  const videoQuality = normalizeVideoQuality(result);
  const hasPoseTimeline = Boolean(result.poseFrames?.length);
  const cameraView = result.cameraView ?? result.view;
  const selectedPoseSide = result.diagnostics?.pose_validation?.selected_side
    ?? result.diagnostics?.selected_side
    ?? null;
  const analysisStale = result.analysis_stale ?? result.diagnostics?.analysis_stale ?? false;
  const poseBackend = result.pose_backend ?? result.diagnostics?.pose_backend;
  const fallbackTriggered = result.fallback_triggered ?? result.diagnostics?.fallback_triggered ?? false;
  const fallbackReason = result.fallback_reason ?? result.diagnostics?.fallback_reason;
  const landmarkModel = result.landmark_model ?? result.diagnostics?.landmark_model;

  const handleVideoLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    // The overlay needs the rendered video size to map pose points correctly.
    setVideoLayout({
      width: nativeEvent.layout.width,
      height: nativeEvent.layout.height,
    });
  };

  const handleSeek = (time: number) => {
    // Clamp seeks so the scrubber cannot leave the clip bounds.
    const boundedTime = Math.min(Math.max(time, 0), duration || time);
    player.currentTime = boundedTime;
    setCurrentTime(boundedTime);
  };

  const handleScrubStart = () => {
    setWasPlayingBeforeScrub(isPlaying);
    player.pause();
  };

  const handleScrubEnd = (time: number) => {
    handleSeek(time);

    if (wasPlayingBeforeScrub) {
      player.play();
    }
  };

  const handleTogglePlayback = () => {
    if (isPlaying) {
      player.pause();
      return;
    }

    player.play();
  };

  const handleSave = async () => {
    // Save is gated by a valid session token.
    if (isSavedMode || !session?.access_token || saving) {
      return;
    }

    setSaving(true);
    setErrorMessage(null);

    try {
      await saveAnalyzedVideo(result.video_id, session.access_token);
      setSaved(true);
      player.pause();
      onSaved?.();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to save this video.');
    } finally {
      setSaving(false);
    }
  };

  const discardVideo = async () => {
    // Discard removes the uploaded file from the backend and storage.
    if (isSavedMode || !session?.access_token || discarding) {
      return;
    }

    setDiscarding(true);
    setErrorMessage(null);

    try {
      await discardAnalyzedVideo(result.video_id, session.access_token);
      setShowDiscardSheet(false);
      player.pause();
      onDiscarded?.();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to discard this video.');
    } finally {
      setDiscarding(false);
    }
  };

  const closeDiscardSheet = () => {
    if (discarding) {
      return;
    }

    setShowDiscardSheet(false);
  };

  const handleBack = () => {
    if (isSavedMode) {
      player.pause();
      onBack?.();
      return;
    }

    // Going back warns if the analyzed clip has not been saved yet.
    if (saved) {
      onSaved?.();
      return;
    }

    setShowDiscardSheet(true);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.topBar}>
          <Pressable
            accessibilityRole="button"
            onPress={handleBack}
            disabled={saving || discarding}
            style={[styles.topButton, (saving || discarding) && styles.disabledButton]}
          >
            <Text style={styles.topButtonText}>Back</Text>
          </Pressable>
          <Text style={styles.title}>{formatFlagLabel(result.exercise)}</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              void handleSave();
            }}
            disabled={isSavedMode || saving || discarding}
            style={[styles.topButton, (isSavedMode || saving || discarding) && styles.disabledButton]}
          >
            <Text style={styles.topButtonText}>{isSavedMode ? 'Saved' : saving ? 'Saving' : 'Save'}</Text>
          </Pressable>
        </View>

        <View style={styles.videoArea} onLayout={handleVideoLayout}>
          <Pressable style={styles.videoPressable} onPress={handleTogglePlayback}>
            <VideoView
              player={player}
              style={styles.video}
              nativeControls={false}
              contentFit="cover"
              allowsPictureInPicture={false}
              onFirstFrameRender={() => setErrorMessage(null)}
            />
            {/* Pose markers are drawn on top of the rendered video. */}
            <PoseOverlay
              frame={poseFrame}
              containerSize={videoLayout}
              videoSize={videoSize}
              contentFit="cover"
              cameraView={cameraView}
              selectedSide={selectedPoseSide}
            />

            {status === 'loading' ? (
              <View style={styles.centerOverlay}>
                <ActivityIndicator color={tokens.colors.textPrimary} />
              </View>
            ) : null}

            {!isPlaying ? (
              <View style={styles.playButton}>
                <Ionicons name="play" size={26} color={tokens.colors.textPrimary} />
              </View>
            ) : null}

            {!hasPoseTimeline ? (
              <View style={styles.poseNotice}>
                <Text style={styles.poseNoticeText}>Pose overlay unavailable for this result.</Text>
              </View>
            ) : null}
          </Pressable>
        </View>

        <View style={styles.bottomPanel}>
          <TimelineScrubber
            currentTime={currentTime}
            duration={duration}
            onSeek={handleSeek}
            onScrubStart={handleScrubStart}
            onScrubEnd={handleScrubEnd}
          />

          {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}

          <View style={styles.bottomActions}>
            <Pressable
              accessibilityRole="button"
              onPress={() => setActiveSheet('summary')}
              style={styles.toolButton}
            >
              <Ionicons name="layers-outline" size={24} color={tokens.colors.brand} />
              <Text style={styles.toolButtonText}>Summary</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={() => setActiveSheet('coaching')}
              style={styles.toolButton}
            >
              <Ionicons name="document-text-outline" size={24} color={tokens.colors.brand} />
              <Text style={styles.toolButtonText}>Coaching</Text>
            </Pressable>
          </View>
        </View>
        <ReviewBottomSheet
          visible={activeSheet === 'summary'}
          title="Summary"
          onClose={() => setActiveSheet(null)}
        >
          <ScrollView style={styles.sheetScroll} contentContainerStyle={styles.sheetContent}>
            <SheetSection title="Summary flags">
              <Text style={styles.debugText}>Stale analysis: {analysisStale ? 'yes' : 'no'}</Text>
              <Text style={styles.debugText}>Pose backend: {poseBackend ?? 'n/a'}</Text>
              <Text style={styles.debugText}>Fallback used: {fallbackTriggered ? 'yes' : 'no'}</Text>
              <Text style={styles.debugText}>Fallback reason: {fallbackReason ?? 'n/a'}</Text>
              <Text style={styles.debugText}>Landmark model: {landmarkModel ?? 'n/a'}</Text>
              {analysisStale ? (
                <Text style={styles.staleText}>
                  This result was created by an older model version. Re-run analysis before trusting depth flags.
                </Text>
              ) : null}
              {summaryFlags.length ? summaryFlags.map((flag) => (
                <Text key={flag} style={styles.sheetText}>- {formatFlagLabel(flag)}</Text>
              )) : <Text style={styles.sheetMutedText}>No summary flags.</Text>}
            </SheetSection>

            <SheetSection title="Video quality">
              <Text style={styles.sheetText}>Overall quality: {formatPercent(videoQuality.overallQuality)}</Text>
              <Text style={styles.sheetText}>Pose coverage: {formatPercent(videoQuality.poseCoverage)}</Text>
              <Text style={styles.sheetText}>Lower body visibility: {formatPercent(videoQuality.lowerBodyVisibility)}</Text>
              <Text style={styles.sheetText}>Side-view confidence: {formatPercent(videoQuality.sideViewConfidence)}</Text>
              <Text style={styles.sheetText}>
                Squat motion signal: {formatNumber(videoQuality.squatMotionSignal ?? 0)}
              </Text>
            </SheetSection>

            <SheetSection title="Per-rep highlights">
              {result.reps.length ? result.reps.map((rep) => {
                const velocity = getRepVelocity(rep);
                const depthStatus = rep.depthStatus ?? rep.depth_status;
                const depthTimestampMs = rep.depthTimestampMs ?? rep.depth_timestamp_ms;
                const bottomTimestampMs = rep.bottomTimestampMs ?? rep.bottom_timestamp_ms;
                const selectedSide = rep.selectedSide ?? rep.selected_side ?? rep.depth_evidence?.selected_side;
                const hipKneeDelta = rep.depth_evidence?.hip_knee_delta ?? rep.depth_components?.hip_knee_delta;
                const parallelScore = rep.depth_evidence?.parallel_score ?? rep.depth_components?.parallel_score;
                const depthConfidence =
                  rep.depth_evidence?.depth_confidence ?? rep.depthConfidence ?? rep.depth_confidence;
                const scoredFrameDiffers = rep.depth_evidence?.scored_frame_differs_from_bottom;
                const plateRackOcclusion = rep.depth_evidence?.plate_rack_occlusion_suspected;
                return (
                  <View key={rep.rep_index} style={styles.repBlock}>
                    <Text style={styles.sheetText}>Rep {rep.repIndex ?? rep.rep_index}</Text>
                    <Text style={styles.sheetMutedText}>Duration: {formatNumber(getRepDuration(rep), 's')}</Text>
                    <Text style={styles.sheetMutedText}>Rep speed: {formatNumber(getRepSpeed(rep), ' reps/s')}</Text>
                    <Text style={styles.sheetMutedText}>
                      Estimated hip velocity: avg {formatNumber(velocity.avgVelocity)}, peak {formatNumber(velocity.peakVelocity)}
                    </Text>
                    <Text style={styles.sheetMutedText}>
                      Depth {formatNumber(rep.depthScore ?? rep.depth_score)}, torso change {formatNumber(rep.torsoAngleChangeDeg ?? rep.torso_angle_change, ' deg')}
                    </Text>
                    <View style={styles.debugBlock}>
                      <Text style={styles.debugText}>Depth status: {formatDepthStatus(depthStatus)}</Text>
                      <Text style={styles.debugText}>Hip-knee delta: {formatOptionalNumber(hipKneeDelta)}</Text>
                      <Text style={styles.debugText}>Parallel score: {formatOptionalNumber(parallelScore)}</Text>
                      <Text style={styles.debugText}>Depth confidence: {formatOptionalNumber(depthConfidence)}</Text>
                      <Text style={styles.debugText}>
                        Scored frame: {formatMilliseconds(depthTimestampMs)} · bottom: {formatMilliseconds(bottomTimestampMs)}
                      </Text>
                      <Text style={styles.debugText}>Selected side: {selectedSide ?? selectedPoseSide ?? 'n/a'}</Text>
                      <Text style={styles.debugText}>Scored frame differs: {scoredFrameDiffers ? 'yes' : 'no'}</Text>
                      <Text style={styles.debugText}>Rack/plate occlusion: {plateRackOcclusion ? 'yes' : 'no'}</Text>
                    </View>
                  </View>
                );
              }) : <Text style={styles.sheetMutedText}>No reps detected.</Text>}
            </SheetSection>
          </ScrollView>
        </ReviewBottomSheet>

        <ReviewBottomSheet
          visible={activeSheet === 'coaching'}
          title="Coaching"
          onClose={() => setActiveSheet(null)}
        >
          <ScrollView style={styles.sheetScroll} contentContainerStyle={styles.sheetContent}>
            {coachingFeedback.length ? coachingFeedback.map((feedback) => (
              <Text key={feedback} style={styles.sheetText}>- {feedback}</Text>
            )) : <Text style={styles.sheetMutedText}>No coaching feedback available.</Text>}
          </ScrollView>
        </ReviewBottomSheet>

        <ReviewBottomSheet
          visible={!isSavedMode && showDiscardSheet}
          title="Discard video?"
          onClose={closeDiscardSheet}
          showCloseButton={false}
          sheetStyle={styles.discardSheet}
        >
          <View style={styles.discardContent}>
            <Text style={styles.discardSubtitle}>
              This analyzed upload has not been saved. Discarding permanently removes the video and analysis.
            </Text>
            {errorMessage ? <Text style={styles.discardErrorText}>{errorMessage}</Text> : null}
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                void discardVideo();
              }}
              disabled={discarding || saving}
              style={[styles.discardButton, (discarding || saving) && styles.disabledButton]}
            >
              {discarding ? (
                <ActivityIndicator color={tokens.colors.textPrimary} />
              ) : (
                <Text style={styles.discardButtonText}>Discard Video</Text>
              )}
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={closeDiscardSheet}
              disabled={discarding}
              style={[styles.cancelDiscardButton, discarding && styles.disabledButton]}
            >
              <Text style={styles.cancelDiscardButtonText}>Cancel</Text>
            </Pressable>
          </View>
        </ReviewBottomSheet>
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
    position: 'relative',
    backgroundColor: '#000',
  },
  topBar: {
    height: 86,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 22,
    backgroundColor: '#000',
  },
  topButton: {
    minWidth: 76,
    minHeight: 46,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 9,
    backgroundColor: tokens.colors.brand,
    paddingHorizontal: 14,
  },
  disabledButton: {
    opacity: 0.6,
  },
  topButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '600',
  },
  title: {
    flex: 1,
    color: tokens.colors.brand,
    fontSize: 32,
    lineHeight: 38,
    fontWeight: '500',
    textAlign: 'center',
    marginHorizontal: 14,
  },
  videoArea: {
    flex: 1,
    width: '100%',
    backgroundColor: '#000',
  },
  videoPressable: {
    flex: 1,
    position: 'relative',
    overflow: 'hidden',
  },
  video: {
    width: '100%',
    height: '100%',
  },
  centerOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
  },
  playButton: {
    position: 'absolute',
    left: '50%',
    top: '50%',
    width: 58,
    height: 58,
    marginLeft: -29,
    marginTop: -29,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 29,
    backgroundColor: 'rgba(0, 0, 0, 0.48)',
  },
  poseNotice: {
    position: 'absolute',
    left: 14,
    right: 14,
    bottom: 14,
    borderRadius: 8,
    backgroundColor: 'rgba(0, 0, 0, 0.58)',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  poseNoticeText: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  bottomPanel: {
    minHeight: 164,
    borderTopWidth: 1,
    borderTopColor: '#343434',
    backgroundColor: '#202020',
    paddingHorizontal: 22,
    paddingTop: 18,
    paddingBottom: 18,
    gap: 14,
  },
  bottomActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  toolButton: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 8,
  },
  toolButtonText: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
  },
  errorText: {
    color: '#FF8A8A',
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  sheetScroll: {
    flexGrow: 0,
  },
  sheetContent: {
    gap: 18,
    paddingBottom: 8,
  },
  sheetSection: {
    gap: 8,
  },
  sheetLabel: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '700',
  },
  sheetText: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 22,
  },
  sheetMutedText: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  staleText: {
    color: '#FFB020',
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  repBlock: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0C1016',
    padding: 12,
    gap: 3,
  },
  debugBlock: {
    marginTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#243044',
    paddingTop: 8,
    gap: 2,
  },
  debugText: {
    color: '#9FB6D9',
    fontSize: 12,
    lineHeight: 17,
  },
  discardSheet: {
    maxHeight: '46%',
    backgroundColor: '#202020',
    borderColor: '#343434',
    paddingHorizontal: 22,
    paddingBottom: 34,
  },
  discardContent: {
    gap: 14,
  },
  discardSubtitle: {
    color: '#D6D6D6',
    fontSize: 15,
    lineHeight: 22,
  },
  discardErrorText: {
    color: '#FF8A8A',
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  discardButton: {
    width: '100%',
    minHeight: 54,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#D93025',
    paddingHorizontal: 18,
  },
  discardButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '700',
  },
  cancelDiscardButton: {
    width: '100%',
    minHeight: 54,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#4A4A4A',
    backgroundColor: '#2A2A2A',
    paddingHorizontal: 18,
  },
  cancelDiscardButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '700',
  },
});
