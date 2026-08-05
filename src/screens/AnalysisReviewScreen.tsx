import { Ionicons } from '@expo/vector-icons';
import { useEvent } from 'expo';
import { VideoView, useVideoPlayer } from 'expo-video';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { discardAnalyzedVideo, saveAnalyzedVideo } from '../../lib/backendApi';
import BarbellPathOverlay from '../components/BarbellPathOverlay';
import JointMotionTrailOverlay from '../components/JointMotionTrailOverlay';
import PoseOverlay from '../components/PoseOverlay';
import TrackingReferenceOverlay from '../components/TrackingReferenceOverlay';
import ReviewBottomSheet from '../components/ReviewBottomSheet';
import TimelineScrubber from '../components/TimelineScrubber';
import TrackingDisplaySheet from '../components/TrackingDisplaySheet';
import WorkoutDetailsSheet from '../components/WorkoutDetailsSheet';
import tokens from '../theme/tokens';
import { BarbellPath, VideoAnalysisResult } from '../types/videoAnalysis';
import type { WorkoutSaveDetails } from '../../lib/workoutSavePolicy';
import {
  isReferenceTrackingTime,
  resolveSelectedTrackingSide,
} from '../../lib/trackingOverlayPolicy';
import {
  calculateVideoRect,
  findInterpolatedPoseFrame,
  formatPercent,
  getRepDuration,
  getRepSpeed,
  getRepVelocity,
  normalizeCoachingFeedback,
  normalizeResultFlags,
  normalizeVideoQuality,
} from '../utils/videoReview';

type AnalysisReviewScreenProps = {
  videoUri: string | null;
  result: VideoAnalysisResult;
  mode?: 'pending' | 'saved';
  onBack?: () => void;
  onDiscarded?: () => void;
  onSaved?: (videoId: string) => void | Promise<void>;
  onDeleteSavedVideo?: (videoId: string) => Promise<void>;
  workoutDetails?: WorkoutSaveDetails | null;
};

type BarbellPathCarrier = VideoAnalysisResult & {
  analysis?: {
    barbellPath?: BarbellPath;
  };
  result?: {
    barbellPath?: BarbellPath;
  };
};

function formatFlagLabel(value: string) {
  // Turn backend enum strings into readable labels.
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value?: number | null, suffix = '') {
  // Keep numeric debug values compact on screen.
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return `0${suffix}`;
  }

  return `${value.toFixed(2)}${suffix}`;
}

function SheetSection({
  title,
  children,
  collapsible = false,
  defaultExpanded = true,
}: {
  title: string;
  children: React.ReactNode;
  collapsible?: boolean;
  defaultExpanded?: boolean;
}) {
  // Shared block for the review sheet sections.
  const [expanded, setExpanded] = useState(!collapsible || defaultExpanded);

  return (
    <View style={styles.sheetSection}>
      {collapsible ? (
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded }}
          onPress={() => setExpanded((value) => !value)}
          style={styles.sheetSectionHeader}
        >
          <Text style={styles.sheetLabel}>{title}</Text>
          <Ionicons
            name={expanded ? 'chevron-up-outline' : 'chevron-down-outline'}
            size={18}
            color={tokens.colors.textMuted}
          />
        </Pressable>
      ) : (
        <Text style={styles.sheetLabel}>{title}</Text>
      )}
      {expanded ? children : null}
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
  onDeleteSavedVideo,
  workoutDetails,
}: AnalysisReviewScreenProps) {
  // This screen plays the analyzed clip and overlays pose feedback.
  const { session } = useAuth();
  const isSavedMode = mode === 'saved';
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(result.duration ?? 0);
  const [videoLayout, setVideoLayout] = useState({ width: 0, height: 0 });
  const [activeSheet, setActiveSheet] = useState<'summary' | 'coaching' | 'tracking' | null>(null);
  const [poseOverlayEnabled, setPoseOverlayEnabled] = useState(true);
  const [barbellPathEnabled, setBarbellPathEnabled] = useState(true);
  const [saving, setSaving] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [deletingSavedVideo, setDeletingSavedVideo] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showDiscardSheet, setShowDiscardSheet] = useState(false);
  const [showSavedDeleteSheet, setShowSavedDeleteSheet] = useState(false);
  const [showWorkoutDetailsSheet, setShowWorkoutDetailsSheet] = useState(false);
  const [wasPlayingBeforeScrub, setWasPlayingBeforeScrub] = useState(false);
  const mediaAvailable = Boolean(videoUri);

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
    () => findInterpolatedPoseFrame(result.poseFrames, currentTime),
    [currentTime, result.poseFrames]
  );
  const videoSize = {
    width: result.processedVideoWidth || result.videoWidth || 1080,
    height: result.processedVideoHeight || result.videoHeight || 1920,
  };
  const barbellPath = useMemo(() => {
    const payload = result as BarbellPathCarrier;
    return payload.barbellPath ?? payload.analysis?.barbellPath ?? payload.result?.barbellPath;
  }, [result]);
  const summaryFlags = normalizeResultFlags(result);
  const coachingFeedback = normalizeCoachingFeedback(result);
  const videoQuality = normalizeVideoQuality(result);
  const hasPoseTimeline = Boolean(result.poseFrames?.length);
  const hasBarbellPath = barbellPath?.available === true
    && Array.isArray(barbellPath.points)
    && barbellPath.points.length >= 2;
  const trackingAssistance = result.trackingAssistance ?? result.diagnostics?.tracking_assistance;
  const trackingReference = trackingAssistance?.reference ?? null;
  const showReferencePins = Boolean(
    trackingReference
    && isReferenceTrackingTime(currentTime, trackingReference.timeMs)
  );
  const showPoseOverlay = hasPoseTimeline && poseOverlayEnabled && !showReferencePins;
  const showBarbellPath = hasBarbellPath && barbellPathEnabled && !showReferencePins;
  const cameraView = result.cameraView ?? result.view;
  const isFrontSquatTracking = result.analysisMode === 'front_squat_tracking_v1';
  const depthAssessmentAvailable = result.analysisCapabilities?.depthAssessment
    ?? !isFrontSquatTracking;
  const selectedPoseSide = resolveSelectedTrackingSide(trackingAssistance, result.diagnostics);
  const analysisStale = result.analysis_stale ?? result.diagnostics?.analysis_stale ?? false;
  const analysisIncomplete = result.analysis_incomplete ?? result.diagnostics?.analysis_incomplete ?? false;
  const depthSummaryDebug = result.diagnostics?.depth_summary_debug;
  const finalInsufficientDepthReps =
    depthSummaryDebug?.insufficient_depth_reps
    ?? result.reps
      .filter((rep) => (rep.depthStatus ?? rep.depth_status) === 'insufficient_depth')
      .map((rep) => rep.repIndex ?? rep.rep_index);
  const finalHitDepthReps =
    depthSummaryDebug?.hit_depth_reps
    ?? result.reps
      .filter((rep) => (rep.depthStatus ?? rep.depth_status) === 'hit_depth')
      .map((rep) => rep.repIndex ?? rep.rep_index);
  const finalUncertainDepthReps =
    depthSummaryDebug?.uncertain_depth_reps
    ?? result.reps
      .filter((rep) => (rep.depthStatus ?? rep.depth_status) === 'uncertain_depth')
      .map((rep) => rep.repIndex ?? rep.rep_index);
  const summaryDepthMismatch =
    summaryFlags.includes('Insufficient depth') && finalInsufficientDepthReps.length === 0;
  const sanitizedSummaryFlags = summaryDepthMismatch
    ? summaryFlags.filter((flag) => flag !== 'Insufficient depth')
    : summaryFlags;
  const displaySummaryFlags = analysisIncomplete ? ['Analysis needs re-run'] : sanitizedSummaryFlags;
  const depthHitCount = finalHitDepthReps.length;
  const repCount = result.rep_count || result.reps.length;
  const depthHitLabel =
    repCount > 0
      ? `Depth hit: ${depthHitCount > 0 ? 'yes' : 'no'} (${depthHitCount}/${repCount} reps)`
      : 'Depth hit: n/a (0 reps)';
  const trackingAssistanceLabel = trackingAssistance?.actualMode === 'pin_assisted'
    ? 'Pin-assisted'
    : trackingAssistance?.requestedMode === 'pins'
      && trackingAssistance.actualMode === 'automatic_fallback'
      ? 'Automatic fallback'
      : null;

  useEffect(() => {
    setPoseOverlayEnabled(true);
    setBarbellPathEnabled(true);
  }, [result.video_id]);

  useEffect(() => {
    if (!mediaAvailable && activeSheet === 'tracking') {
      setActiveSheet(null);
    }
  }, [activeSheet, mediaAvailable]);

  useEffect(() => {
    const points = Array.isArray(barbellPath?.points) ? barbellPath.points : [];
    const firstPoint = points[0] ?? null;
    const lastPoint = points[points.length - 1] ?? null;
    const rect = calculateVideoRect(videoLayout, videoSize, 'cover');
    const firstMappedPoint = firstPoint
      ? {
        x: rect.x + (firstPoint.x * rect.width),
        y: rect.y + (firstPoint.y * rect.height),
      }
      : null;

    console.log('[BARBELL_PATH_DIAG]', {
      exists: Boolean(barbellPath),
      available: barbellPath?.available,
      pointCount: points.length,
      firstPoint,
      lastPoint,
      overlayWidth: videoLayout.width,
      overlayHeight: videoLayout.height,
      firstMappedPoint,
    });
  }, [barbellPath, videoLayout.width, videoLayout.height, videoSize.width, videoSize.height]);

  const handleVideoLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    // The overlay needs the rendered video size to map pose points correctly.
    setVideoLayout({
      width: nativeEvent.layout.width,
      height: nativeEvent.layout.height,
    });
  };

  const handleSeek = (time: number) => {
    if (!mediaAvailable) {
      return;
    }

    // Clamp seeks so the scrubber cannot leave the clip bounds.
    const boundedTime = Math.min(Math.max(time, 0), duration || time);
    player.currentTime = boundedTime;
    setCurrentTime(boundedTime);
  };

  const handleScrubStart = () => {
    if (!mediaAvailable) {
      return;
    }

    setWasPlayingBeforeScrub(isPlaying);
    player.pause();
  };

  const handleScrubEnd = (time: number) => {
    handleSeek(time);

    if (mediaAvailable && wasPlayingBeforeScrub) {
      player.play();
    }
  };

  const handleTogglePlayback = () => {
    if (!mediaAvailable) {
      return;
    }

    if (isPlaying) {
      player.pause();
      return;
    }

    player.play();
  };

  const handleSave = async (details: WorkoutSaveDetails) => {
    // Save is gated by a valid session token.
    if (isSavedMode || !session?.access_token || saving) {
      return;
    }

    setSaving(true);
    setErrorMessage(null);

    try {
      await saveAnalyzedVideo(result.video_id, details, session.access_token);
      setSaved(true);
      setShowWorkoutDetailsSheet(false);
      if (mediaAvailable) {
        player.pause();
      }
      await onSaved?.(result.video_id);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to save this video.');
      throw error;
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
      if (mediaAvailable) {
        player.pause();
      }
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

  const deleteSavedVideo = async () => {
    if (!isSavedMode || !onDeleteSavedVideo || deletingSavedVideo) {
      return;
    }

    setDeletingSavedVideo(true);
    setErrorMessage(null);

    try {
      await onDeleteSavedVideo(result.video_id);
      setShowSavedDeleteSheet(false);
      if (mediaAvailable) {
        player.pause();
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to delete this video.');
    } finally {
      setDeletingSavedVideo(false);
    }
  };

  const closeSavedDeleteSheet = () => {
    if (deletingSavedVideo) {
      return;
    }

    setShowSavedDeleteSheet(false);
  };

  const handleBack = () => {
    if (isSavedMode) {
      if (mediaAvailable) {
        player.pause();
      }
      onBack?.();
      return;
    }

    // Going back warns if the analyzed clip has not been saved yet.
    if (saved) {
      void onSaved?.(result.video_id);
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
            disabled={saving || discarding || deletingSavedVideo}
            style={[styles.topButton, (saving || discarding || deletingSavedVideo) && styles.disabledButton]}
          >
            <Text style={styles.topButtonText}>Back</Text>
          </Pressable>
          <Text style={styles.title}>{formatFlagLabel(result.exercise)}</Text>
          {isSavedMode ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => setShowSavedDeleteSheet(true)}
              disabled={deletingSavedVideo}
              style={[styles.savedTrashButton, deletingSavedVideo && styles.disabledButton]}
            >
              {deletingSavedVideo ? (
                <ActivityIndicator color={tokens.colors.brand} />
              ) : (
                <Ionicons name="trash-outline" size={24} color={tokens.colors.brand} />
              )}
            </Pressable>
          ) : (
            <Pressable
              accessibilityRole="button"
              onPress={() => setShowWorkoutDetailsSheet(true)}
              disabled={saving || discarding}
              style={[styles.topButton, (saving || discarding) && styles.disabledButton]}
            >
              <Text style={styles.topButtonText}>{saving ? 'Saving' : 'Save'}</Text>
            </Pressable>
          )}
        </View>

        <View style={styles.videoArea} onLayout={handleVideoLayout}>
          <Pressable style={styles.videoPressable} onPress={handleTogglePlayback}>
            {mediaAvailable ? (
              <>
                <VideoView
                  player={player}
                  style={styles.video}
                  nativeControls={false}
                  contentFit="cover"
                  allowsPictureInPicture={false}
                  onFirstFrameRender={() => setErrorMessage(null)}
                />
                {showPoseOverlay ? (
                  <JointMotionTrailOverlay
                    frames={result.poseFrames}
                    currentTime={currentTime}
                    containerSize={videoLayout}
                    videoSize={videoSize}
                    contentFit="cover"
                    exercise={result.exercise}
                    cameraView={cameraView}
                  />
                ) : null}
                {showPoseOverlay ? (
                  <PoseOverlay
                    frame={poseFrame}
                    containerSize={videoLayout}
                    videoSize={videoSize}
                    contentFit="cover"
                    exercise={result.exercise}
                    cameraView={cameraView}
                    selectedSide={selectedPoseSide}
                    preferUpperBackKeypoint={trackingAssistance?.actualMode === 'pin_assisted'}
                  />
                ) : null}
                {showBarbellPath ? (
                  <BarbellPathOverlay
                    path={barbellPath}
                    currentTime={currentTime}
                    containerSize={videoLayout}
                    videoSize={videoSize}
                    contentFit="cover"
                  />
                ) : null}
                {showReferencePins && trackingReference ? (
                  <TrackingReferenceOverlay
                    reference={trackingReference}
                    containerSize={videoLayout}
                    videoSize={videoSize}
                    contentFit="cover"
                  />
                ) : null}
                {trackingAssistanceLabel ? (
                  <View style={styles.trackingAssistanceBadge} pointerEvents="none">
                    <Ionicons
                      name={trackingAssistance?.used ? 'locate' : 'warning-outline'}
                      size={14}
                      color={trackingAssistance?.used ? '#8CC0FF' : '#FFD080'}
                    />
                    <Text
                      style={[
                        styles.trackingAssistanceText,
                        !trackingAssistance?.used && styles.trackingFallbackText,
                      ]}
                    >
                      {trackingAssistanceLabel}
                    </Text>
                  </View>
                ) : null}
              </>
            ) : (
              <View style={styles.mediaUnavailable}>
                <Ionicons name="analytics-outline" size={46} color={tokens.colors.brand} />
                <Text style={styles.mediaUnavailableTitle}>Analysis saved</Text>
                <Text style={styles.mediaUnavailableText}>
                  The source video has expired to reduce storage usage.
                </Text>
              </View>
            )}

            {mediaAvailable && status === 'loading' ? (
              <View style={styles.centerOverlay}>
                <ActivityIndicator color={tokens.colors.textPrimary} />
              </View>
            ) : null}

            {mediaAvailable && !isPlaying ? (
              <View style={styles.playButton}>
                <Ionicons name="play" size={26} color={tokens.colors.textPrimary} />
              </View>
            ) : null}
          </Pressable>
        </View>

        <View style={styles.bottomPanel}>
          {mediaAvailable ? (
            <TimelineScrubber
              currentTime={currentTime}
              duration={duration}
              onSeek={handleSeek}
              onScrubStart={handleScrubStart}
              onScrubEnd={handleScrubEnd}
            />
          ) : null}

          {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}

          <View style={styles.bottomActions}>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: !mediaAvailable }}
              onPress={() => setActiveSheet('tracking')}
              disabled={!mediaAvailable}
              style={[styles.toolButton, !mediaAvailable && styles.disabledButton]}
            >
              <Ionicons name="eye-outline" size={24} color={tokens.colors.brand} />
              <Text style={styles.toolButtonText}>Tracking</Text>
            </Pressable>
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
        <TrackingDisplaySheet
          visible={activeSheet === 'tracking'}
          poseAvailable={hasPoseTimeline}
          poseEnabled={poseOverlayEnabled}
          barbellAvailable={hasBarbellPath}
          barbellEnabled={barbellPathEnabled}
          onPoseEnabledChange={setPoseOverlayEnabled}
          onBarbellEnabledChange={setBarbellPathEnabled}
          onClose={() => setActiveSheet(null)}
        />
        <ReviewBottomSheet
          visible={activeSheet === 'summary'}
          title="Summary"
          onClose={() => setActiveSheet(null)}
          scrollable
          scrollContentStyle={styles.sheetContent}
        >
          {workoutDetails ? (
            <SheetSection title="Workout facts">
              {workoutDetails.performed_reps !== null ? (
                <Text style={styles.sheetText}>
                  Performed reps: {workoutDetails.performed_reps}
                </Text>
              ) : null}
              {workoutDetails.load_value !== null && workoutDetails.load_unit !== null ? (
                <Text style={styles.sheetText}>
                  Load: {workoutDetails.load_value} {workoutDetails.load_unit}
                </Text>
              ) : null}
              <Text style={styles.sheetMutedText}>Detected reps: {repCount}</Text>
              {workoutDetails.user_notes ? (
                <Text style={styles.sheetMutedText}>Notes: {workoutDetails.user_notes}</Text>
              ) : null}
            </SheetSection>
          ) : null}
          <SheetSection title="Summary flags">
              {depthAssessmentAvailable ? (
                <Text style={styles.sheetText}>{depthHitLabel}</Text>
              ) : (
                <Text style={styles.sheetText}>Front tracking: {repCount} reps</Text>
              )}
              {analysisStale ? (
                <Text style={styles.staleText}>
                  This result was created by an older or incomplete model payload. Re-run analysis before trusting depth flags.
                </Text>
              ) : null}
              {summaryDepthMismatch ? (
                <Text style={styles.staleText}>
                  Summary flag inconsistent with rep statuses.
                </Text>
              ) : null}
              {displaySummaryFlags.length ? displaySummaryFlags.map((flag) => (
                <Text key={flag} style={styles.sheetText}>{formatFlagLabel(flag)}</Text>
              )) : <Text style={styles.sheetMutedText}>No summary flags.</Text>}
            </SheetSection>

            <SheetSection title="Video quality">
              <Text style={styles.sheetText}>Overall quality: {formatPercent(videoQuality.overallQuality)}</Text>
              <Text style={styles.sheetText}>Pose coverage: {formatPercent(videoQuality.poseCoverage)}</Text>
              <Text style={styles.sheetText}>Lower body visibility: {formatPercent(videoQuality.lowerBodyVisibility)}</Text>
              {!isFrontSquatTracking ? (
                <Text style={styles.sheetText}>Side-view confidence: {formatPercent(videoQuality.sideViewConfidence)}</Text>
              ) : null}
              <Text style={styles.sheetText}>
                Squat motion signal: {formatNumber(videoQuality.squatMotionSignal ?? 0)}
              </Text>
            </SheetSection>

            <SheetSection title="Per-rep highlights">
              {result.reps.length ? result.reps.map((rep) => {
                const velocity = getRepVelocity(rep);
                return (
                  <View key={rep.rep_index} style={styles.repBlock}>
                    <Text style={styles.sheetText}>Rep {rep.repIndex ?? rep.rep_index}</Text>
                    <Text style={styles.sheetMutedText}>Duration: {formatNumber(getRepDuration(rep), 's')}</Text>
                    <Text style={styles.sheetMutedText}>Rep speed: {formatNumber(getRepSpeed(rep), ' reps/s')}</Text>
                    {isFrontSquatTracking ? (
                      <Text style={styles.sheetMutedText}>
                        Tracking confidence: {formatPercent(rep.confidence)}
                      </Text>
                    ) : (
                      <>
                        <Text style={styles.sheetMutedText}>
                          Estimated hip velocity: avg {formatNumber(velocity.avgVelocity)}, peak {formatNumber(velocity.peakVelocity)}
                        </Text>
                        <Text style={styles.sheetMutedText}>
                          Depth {formatNumber(rep.depthScore ?? rep.depth_score)}, torso change {formatNumber(rep.torsoAngleChangeDeg ?? rep.torso_angle_change, ' deg')}
                        </Text>
                      </>
                    )}
                  </View>
                );
              }) : <Text style={styles.sheetMutedText}>No reps detected.</Text>}
          </SheetSection>
        </ReviewBottomSheet>

        <WorkoutDetailsSheet
          visible={!isSavedMode && showWorkoutDetailsSheet}
          detectedReps={repCount}
          onCancel={() => setShowWorkoutDetailsSheet(false)}
          onSubmit={handleSave}
        />

        <ReviewBottomSheet
          visible={activeSheet === 'coaching'}
          title="Coaching"
          onClose={() => setActiveSheet(null)}
          scrollable
          scrollContentStyle={styles.sheetContent}
        >
          {coachingFeedback.length ? coachingFeedback.map((feedback) => (
            <Text key={feedback} style={styles.sheetText}>{feedback}</Text>
          )) : <Text style={styles.sheetMutedText}>No coaching feedback available.</Text>}
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

        <ReviewBottomSheet
          visible={isSavedMode && showSavedDeleteSheet}
          title="Delete video?"
          onClose={closeSavedDeleteSheet}
          showCloseButton={false}
          sheetStyle={styles.discardSheet}
        >
          <View style={styles.discardContent}>
            <Text style={styles.discardSubtitle}>
              This permanently removes the saved video and its analysis from your library.
            </Text>
            {errorMessage ? <Text style={styles.discardErrorText}>{errorMessage}</Text> : null}
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                void deleteSavedVideo();
              }}
              disabled={deletingSavedVideo}
              style={[styles.savedDeleteButton, deletingSavedVideo && styles.disabledButton]}
            >
              {deletingSavedVideo ? (
                <ActivityIndicator color="#D93025" />
              ) : (
                <Text style={styles.savedDeleteButtonText}>Delete Video</Text>
              )}
            </Pressable>
            <Pressable
              accessibilityRole="button"
              onPress={closeSavedDeleteSheet}
              disabled={deletingSavedVideo}
              style={[styles.cancelDiscardButton, deletingSavedVideo && styles.disabledButton]}
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
    minWidth: 68,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 8,
    backgroundColor: tokens.colors.brand,
    paddingHorizontal: 12,
  },
  savedTrashButton: {
    minWidth: 68,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#173B82',
    backgroundColor: '#07142C',
    paddingHorizontal: 12,
  },
  disabledButton: {
    opacity: 0.6,
  },
  topButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 19,
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
  mediaUnavailable: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 28,
    gap: 10,
    backgroundColor: '#050505',
  },
  mediaUnavailableTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 20,
    lineHeight: 25,
    fontWeight: '800',
    textAlign: 'center',
  },
  mediaUnavailableText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  centerOverlay: {
    ...StyleSheet.absoluteFill,
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
  trackingAssistanceBadge: {
    position: 'absolute',
    top: 12,
    left: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#315A88',
    backgroundColor: 'rgba(8, 20, 35, 0.88)',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  trackingAssistanceText: {
    color: '#8CC0FF',
    fontSize: 12,
    lineHeight: 15,
    fontWeight: '700',
  },
  trackingFallbackText: { color: '#FFD080' },
  bottomPanel: {
    minHeight: 144,
    borderTopWidth: 1,
    borderTopColor: '#343434',
    backgroundColor: '#202020',
    paddingHorizontal: 22,
    paddingTop: 12,
    paddingBottom: 12,
    gap: 10,
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
    gap: 6,
    paddingVertical: 6,
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
  sheetContent: {
    gap: 18,
    paddingBottom: 8,
  },
  sheetSection: {
    gap: 8,
  },
  sheetSectionHeader: {
    minHeight: 34,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
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
  savedDeleteButton: {
    width: '100%',
    minHeight: 54,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#D93025',
    backgroundColor: '#241010',
    paddingHorizontal: 18,
  },
  savedDeleteButtonText: {
    color: '#D93025',
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '800',
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
