import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEvent } from 'expo';
import { VideoView, useVideoPlayer } from 'expo-video';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  LayoutChangeEvent,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import tokens from '../theme/tokens';
import {
  NormalizedTrackingPoint,
  TRACKING_PIN_NAMES,
  TrackingPinName,
  TrackingSetup,
} from '../types/trackingSetup';
import { calculateVideoRect } from '../utils/videoReview';
import { getPinnedFrameChangeAction } from '../../lib/trackingPinFramePolicy';
import Button from './Button';
import ConfirmationDialog from './ConfirmationDialog';
import TimelineScrubber from './TimelineScrubber';

const FRAME_CHANGE_WARNING_PREFERENCE_KEY = 'trackingPins.skipFrameChangeWarning.v1';

type TrackingPinSetupModalProps = {
  visible: boolean;
  videoUri: string;
  videoSize: { width: number; height: number };
  videoDurationMs?: number | null;
  initialSetup?: TrackingSetup | null;
  onSave: (setup: TrackingSetup) => void;
  onCancel: () => void;
};

const PIN_LABELS: Record<TrackingPinName, string> = {
  shoulder: 'Shoulder',
  hip: 'Hip',
  knee: 'Knee',
  ankle: 'Ankle',
  barbell: 'Barbell collar',
};

const PIN_COLORS: Record<TrackingPinName, string> = {
  shoulder: '#5DA9FF',
  hip: '#A77BFF',
  knee: '#FFB454',
  ankle: '#5DDBA6',
  barbell: '#FF6577',
};

function orientationCorrectedVideoSize(
  size: { width: number; height: number },
  expected: { width: number; height: number }
) {
  const sizeIsPortrait = size.height > size.width;
  const expectedIsPortrait = expected.height > expected.width;
  return sizeIsPortrait === expectedIsPortrait
    ? size
    : { width: size.height, height: size.width };
}

export default function TrackingPinSetupModal({
  visible,
  videoUri,
  videoSize,
  videoDurationMs,
  initialSetup,
  onSave,
  onCancel,
}: TrackingPinSetupModalProps) {
  const [currentTime, setCurrentTime] = useState((initialSetup?.reference_time_ms ?? 0) / 1000);
  const [duration, setDuration] = useState(
    typeof videoDurationMs === 'number' && Number.isFinite(videoDurationMs)
      ? videoDurationMs / 1000
      : 0
  );
  const [videoLayout, setVideoLayout] = useState({ width: 0, height: 0 });
  const [displayVideoSize, setDisplayVideoSize] = useState(videoSize);
  const [pins, setPins] = useState<Partial<Record<TrackingPinName, NormalizedTrackingPoint>>>(
    initialSetup?.anchors ?? {}
  );
  const [placementOrder, setPlacementOrder] = useState<TrackingPinName[]>(
    initialSetup ? [...TRACKING_PIN_NAMES] : []
  );
  const [draggingPin, setDraggingPin] = useState<TrackingPinName | null>(null);
  const [pinnedFrameTime, setPinnedFrameTime] = useState<number | null>(
    initialSetup ? initialSetup.reference_time_ms / 1000 : null
  );
  const [pendingFrameTime, setPendingFrameTime] = useState<number | null>(null);
  const [frameChangeDialogVisible, setFrameChangeDialogVisible] = useState(false);
  const [suppressFrameChangeWarning, setSuppressFrameChangeWarning] = useState(false);
  const [dontShowFrameChangeWarningAgain, setDontShowFrameChangeWarningAgain] = useState(false);
  const videoViewRef = useRef<VideoView | null>(null);
  const player = useVideoPlayer(videoUri, (videoPlayer) => {
    videoPlayer.loop = false;
    videoPlayer.muted = true;
    videoPlayer.timeUpdateEventInterval = 0.05;
  });
  const sourceLoad = useEvent(player, 'sourceLoad', {
    videoSource: null,
    duration: 0,
    availableVideoTracks: [],
    availableSubtitleTracks: [],
    availableAudioTracks: [],
  });
  const timeUpdate = useEvent(player, 'timeUpdate', {
    currentTime: 0,
    currentLiveTimestamp: null,
    currentOffsetFromLive: null,
    bufferedPosition: 0,
  });
  const statusChange = useEvent(player, 'statusChange', {
    status: player.status,
    oldStatus: undefined,
    error: undefined,
  });

  useEffect(() => {
    if (!visible) {
      return;
    }
    const referenceTime = (initialSetup?.reference_time_ms ?? 0) / 1000;
    setPins(initialSetup?.anchors ?? {});
    setPlacementOrder(initialSetup ? [...TRACKING_PIN_NAMES] : []);
    setCurrentTime(referenceTime);
    setPinnedFrameTime(initialSetup ? referenceTime : null);
    setPendingFrameTime(null);
    setFrameChangeDialogVisible(false);
    setDontShowFrameChangeWarningAgain(false);
    setDisplayVideoSize({ width: videoSize.width, height: videoSize.height });
    if (typeof videoDurationMs === 'number' && Number.isFinite(videoDurationMs)) {
      setDuration(videoDurationMs / 1000);
    }
    player.pause();
    player.currentTime = referenceTime;
  }, [initialSetup, player, videoDurationMs, videoSize.height, videoSize.width, visible]);

  useEffect(() => {
    if (!visible) {
      return;
    }

    void AsyncStorage.getItem(FRAME_CHANGE_WARNING_PREFERENCE_KEY)
      .then((value) => {
        setSuppressFrameChangeWarning(value === 'true');
      })
      .catch(() => {
        setSuppressFrameChangeWarning(false);
      });
  }, [visible]);

  useEffect(() => {
    const loadedTrack = sourceLoad.availableVideoTracks[0];
    if (loadedTrack?.size?.width > 0 && loadedTrack.size.height > 0) {
      setDisplayVideoSize(orientationCorrectedVideoSize(loadedTrack.size, videoSize));
    }
    const nextDuration = sourceLoad.duration || player.duration || 0;
    if (nextDuration > 0) {
      setDuration(nextDuration);
    }
  }, [
    player.duration,
    sourceLoad.availableVideoTracks,
    sourceLoad.duration,
    videoSize.height,
    videoSize.width,
  ]);

  useEffect(() => {
    if (statusChange.status !== 'readyToPlay') {
      return;
    }
    const nextDuration = player.duration || 0;
    if (nextDuration > 0) {
      setDuration(nextDuration);
    }
  }, [player.duration, statusChange.status]);

  useEffect(() => {
    if (visible) {
      setCurrentTime(timeUpdate.currentTime);
    }
  }, [timeUpdate.currentTime, visible]);

  const videoRect = useMemo(
    () => calculateVideoRect(videoLayout, displayVideoSize, 'contain'),
    [displayVideoSize, videoLayout]
  );
  const nextPin = TRACKING_PIN_NAMES.find((name) => !pins[name]) ?? null;
  const pinCount = TRACKING_PIN_NAMES.filter((name) => pins[name]).length;
  const allPinsPlaced = pinCount === TRACKING_PIN_NAMES.length;

  const pointFromTouch = (x: number, y: number): NormalizedTrackingPoint | null => {
    if (
      videoRect.width <= 0 ||
      videoRect.height <= 0 ||
      x < videoRect.x ||
      x > videoRect.x + videoRect.width ||
      y < videoRect.y ||
      y > videoRect.y + videoRect.height
    ) {
      return null;
    }
    return {
      x: Math.min(Math.max((x - videoRect.x) / videoRect.width, 0), 1),
      y: Math.min(Math.max((y - videoRect.y) / videoRect.height, 0), 1),
    };
  };

  const closestPin = (x: number, y: number) => {
    let closest: TrackingPinName | null = null;
    let closestDistance = 30;
    TRACKING_PIN_NAMES.forEach((name) => {
      const point = pins[name];
      if (!point) {
        return;
      }
      const markerX = videoRect.x + (point.x * videoRect.width);
      const markerY = videoRect.y + (point.y * videoRect.height);
      const distance = Math.hypot(markerX - x, markerY - y);
      if (distance < closestDistance) {
        closest = name;
        closestDistance = distance;
      }
    });
    return closest;
  };

  const updatePin = (name: TrackingPinName, x: number, y: number) => {
    const point = pointFromTouch(x, y);
    if (!point) {
      return;
    }
    setPins((current) => ({ ...current, [name]: point }));
  };

  const handleSeek = (time: number) => {
    const boundedTime = Math.min(Math.max(time, 0), duration || time);
    player.pause();
    player.currentTime = boundedTime;
    setCurrentTime(boundedTime);
  };

  const clearPins = () => {
    setPins({});
    setPlacementOrder([]);
    setPinnedFrameTime(null);
  };

  const restorePinnedFrame = () => {
    if (pinnedFrameTime === null) {
      return;
    }
    player.pause();
    player.currentTime = pinnedFrameTime;
    setCurrentTime(pinnedFrameTime);
  };

  const handleScrubEnd = (time: number) => {
    const boundedTime = Math.min(Math.max(time, 0), duration || time);
    const action = getPinnedFrameChangeAction({
      pinCount,
      pinnedFrameTime,
      targetTime: boundedTime,
      suppressWarning: suppressFrameChangeWarning,
    });

    if (action === 'accept') {
      handleSeek(boundedTime);
    } else if (action === 'restore_pinned_frame') {
      restorePinnedFrame();
    } else if (action === 'reset_and_accept') {
      clearPins();
      handleSeek(boundedTime);
    } else {
      setPendingFrameTime(boundedTime);
      setFrameChangeDialogVisible(true);
    }
  };

  const cancelFrameChange = () => {
    setFrameChangeDialogVisible(false);
    setPendingFrameTime(null);
    setDontShowFrameChangeWarningAgain(false);
    restorePinnedFrame();
  };

  const confirmFrameChange = () => {
    const nextTime = pendingFrameTime ?? currentTime;
    clearPins();
    handleSeek(nextTime);
    setFrameChangeDialogVisible(false);
    setPendingFrameTime(null);
    if (dontShowFrameChangeWarningAgain) {
      setSuppressFrameChangeWarning(true);
      void AsyncStorage.setItem(FRAME_CHANGE_WARNING_PREFERENCE_KEY, 'true').catch(() => undefined);
    }
    setDontShowFrameChangeWarningAgain(false);
  };

  const undoLatestPin = () => {
    const latestPin = placementOrder[placementOrder.length - 1];
    if (!latestPin) {
      return;
    }
    setPins((current) => {
      const nextPins = { ...current };
      delete nextPins[latestPin];
      return nextPins;
    });
    setPlacementOrder((current) => current.slice(0, -1));
  };

  const syncRenderedVideoMetadata = () => {
    const nativeVideo = videoViewRef.current?.nativeRef?.current as
      | { duration?: number; videoWidth?: number; videoHeight?: number }
      | undefined;
    const nextDuration = nativeVideo?.duration || player.duration || 0;
    if (nextDuration > 0 && Number.isFinite(nextDuration)) {
      setDuration(nextDuration);
    }
    if (
      nativeVideo?.videoWidth
      && nativeVideo.videoHeight
      && nativeVideo.videoWidth > 0
      && nativeVideo.videoHeight > 0
    ) {
      setDisplayVideoSize(orientationCorrectedVideoSize({
        width: nativeVideo.videoWidth,
        height: nativeVideo.videoHeight,
      }, videoSize));
    }
  };

  const savePins = () => {
    if (!allPinsPlaced) {
      return;
    }
    onSave({
      version: 1,
      reference_time_ms: Math.round(currentTime * 1000),
      barbell_target: 'near_side_collar',
      anchors: pins as Record<TrackingPinName, NormalizedTrackingPoint>,
    });
  };

  if (!visible) {
    return null;
  }

  const placementScreen = (
    <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
        <View style={styles.header}>
          <Pressable onPress={onCancel} style={styles.headerButton}>
            <Text style={styles.headerButtonText}>Cancel</Text>
          </Pressable>
          <Text style={styles.title}>Improve Tracking</Text>
          <View style={styles.headerSpacer} />
        </View>

        <View style={styles.instructions}>
          <Text style={styles.instructionTitle}>
            {nextPin ? `Place: ${PIN_LABELS[nextPin]}` : 'All pins placed'}
          </Text>
          <Text style={styles.instructionText}>
            Choose a clear side-view frame, then tap each landmark. Drag any pin to adjust it.
          </Text>
          <Text style={styles.progressText}>{pinCount}/5 pins</Text>
        </View>

        <View
          style={styles.videoArea}
          onLayout={({ nativeEvent }: LayoutChangeEvent) => {
            setVideoLayout({
              width: nativeEvent.layout.width,
              height: nativeEvent.layout.height,
            });
          }}
        >
          <VideoView
            ref={videoViewRef}
            player={player}
            style={videoRect.width > 0 && videoRect.height > 0
              ? {
                  position: 'absolute',
                  left: videoRect.x,
                  top: videoRect.y,
                  width: videoRect.width,
                  height: videoRect.height,
                }
              : styles.video}
            nativeControls={false}
            contentFit={videoRect.width > 0 && videoRect.height > 0 ? 'fill' : 'contain'}
            allowsPictureInPicture={false}
            onFirstFrameRender={syncRenderedVideoMetadata}
          />
          <View
            style={StyleSheet.absoluteFill}
            onStartShouldSetResponder={() => true}
            onMoveShouldSetResponder={() => true}
            onResponderGrant={(event) => {
              const { locationX, locationY } = event.nativeEvent;
              const existingPin = closestPin(locationX, locationY);
              const selectedPin = existingPin ?? nextPin;
              if (selectedPin) {
                if (!pins[selectedPin]) {
                  if (pinCount === 0) {
                    setPinnedFrameTime(currentTime);
                  }
                  setPlacementOrder((current) => (
                    current.includes(selectedPin) ? current : [...current, selectedPin]
                  ));
                }
                setDraggingPin(selectedPin);
                updatePin(selectedPin, locationX, locationY);
              }
            }}
            onResponderMove={(event) => {
              if (draggingPin) {
                updatePin(draggingPin, event.nativeEvent.locationX, event.nativeEvent.locationY);
              }
            }}
            onResponderRelease={() => setDraggingPin(null)}
            onResponderTerminate={() => setDraggingPin(null)}
          >
            {TRACKING_PIN_NAMES.map((name) => {
              const point = pins[name];
              if (!point) {
                return null;
              }
              const x = videoRect.x + (point.x * videoRect.width);
              const y = videoRect.y + (point.y * videoRect.height);
              return (
                <View
                  key={name}
                  pointerEvents="none"
                  style={[styles.pinContainer, { left: x - 13, top: y - 13 }]}
                >
                  <View style={[styles.pin, { backgroundColor: PIN_COLORS[name] }]}>
                    <Ionicons name="add" size={18} color="#05070A" />
                  </View>
                  <Text style={[styles.pinLabel, { color: PIN_COLORS[name] }]}>{PIN_LABELS[name]}</Text>
                </View>
              );
            })}
          </View>
        </View>

        <View style={styles.controls}>
          <TimelineScrubber
            currentTime={currentTime}
            duration={duration}
            onSeek={handleSeek}
            onScrubStart={() => player.pause()}
            onScrubEnd={handleScrubEnd}
          />
          <Text style={styles.helperText}>
            {pinCount > 0
              ? 'Scrubbing to another frame will clear the placed pins after confirmation.'
              : 'Scrub to a frame where all landmarks and the collar are visible.'}
          </Text>
          <View style={styles.actions}>
            <Pressable onPress={undoLatestPin} disabled={pinCount === 0} style={styles.resetButton}>
              <Text style={[styles.resetText, pinCount === 0 && styles.disabledText]}>Undo</Text>
            </Pressable>
            <Button label="Use These Pins" onPress={savePins} disabled={!allPinsPlaced} style={styles.saveButton} />
          </View>
        </View>
        <ConfirmationDialog
          visible={frameChangeDialogVisible}
          title="Change frame?"
          message="Changing the frame will reset all placed pins."
          confirmLabel="OK"
          checkboxLabel="Don't show this again"
          checkboxValue={dontShowFrameChangeWarningAgain}
          onCheckboxChange={setDontShowFrameChangeWarningAgain}
          onConfirm={confirmFrameChange}
          onCancel={cancelFrameChange}
        />
    </SafeAreaView>
  );

  if (Platform.OS === 'web') {
    return <View style={styles.webOverlay}>{placementScreen}</View>;
  }

  return (
    <Modal visible animationType="slide" onRequestClose={onCancel} presentationStyle="fullScreen">
      {placementScreen}
    </Modal>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    width: '100%',
    height: '100%',
    backgroundColor: '#05070A',
    overflow: 'hidden',
  },
  webOverlay: {
    ...StyleSheet.absoluteFillObject,
    width: '100%',
    height: '100%',
    backgroundColor: '#05070A',
    overflow: 'hidden',
    zIndex: 40,
  },
  header: {
    minHeight: 50,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
  },
  headerButton: { width: 72, paddingVertical: 10 },
  headerButtonText: { color: tokens.colors.brand, fontSize: 15, fontWeight: '600' },
  headerSpacer: { width: 72 },
  title: { color: tokens.colors.textPrimary, fontSize: 18, fontWeight: '700' },
  instructions: { paddingHorizontal: 20, paddingTop: 3, paddingBottom: 12, gap: 5 },
  instructionTitle: { color: tokens.colors.textPrimary, fontSize: 20, fontWeight: '700' },
  instructionText: { color: tokens.colors.textMuted, fontSize: 14, lineHeight: 20 },
  progressText: { color: tokens.colors.brand, fontSize: 13, fontWeight: '700' },
  videoArea: {
    flex: 1,
    minHeight: 0,
    position: 'relative',
    backgroundColor: '#000',
    overflow: 'hidden',
  },
  video: { ...StyleSheet.absoluteFillObject },
  pinContainer: { position: 'absolute', alignItems: 'center' },
  pin: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: '#FFFFFF',
  },
  pinLabel: {
    marginTop: 2,
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 4,
    backgroundColor: 'rgba(0,0,0,0.76)',
    fontSize: 11,
    fontWeight: '700',
  },
  controls: {
    flexShrink: 0,
    paddingHorizontal: 18,
    paddingTop: 16,
    paddingBottom: 12,
    gap: 12,
  },
  helperText: { color: tokens.colors.textMuted, fontSize: 12, lineHeight: 17, textAlign: 'center' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  resetButton: { paddingHorizontal: 10, paddingVertical: 12 },
  resetText: { color: tokens.colors.textPrimary, fontSize: 14, fontWeight: '600' },
  disabledText: { color: tokens.colors.textMuted },
  saveButton: { flex: 1 },
});
