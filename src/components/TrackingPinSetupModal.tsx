import { Ionicons } from '@expo/vector-icons';
import { useEvent } from 'expo';
import { VideoView, useVideoPlayer } from 'expo-video';
import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  LayoutChangeEvent,
  Modal,
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
import Button from './Button';
import TimelineScrubber from './TimelineScrubber';

type TrackingPinSetupModalProps = {
  visible: boolean;
  videoUri: string;
  videoSize: { width: number; height: number };
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

export default function TrackingPinSetupModal({
  visible,
  videoUri,
  videoSize,
  initialSetup,
  onSave,
  onCancel,
}: TrackingPinSetupModalProps) {
  const [currentTime, setCurrentTime] = useState((initialSetup?.reference_time_ms ?? 0) / 1000);
  const [duration, setDuration] = useState(0);
  const [videoLayout, setVideoLayout] = useState({ width: 0, height: 0 });
  const [pins, setPins] = useState<Partial<Record<TrackingPinName, NormalizedTrackingPoint>>>(
    initialSetup?.anchors ?? {}
  );
  const [draggingPin, setDraggingPin] = useState<TrackingPinName | null>(null);
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

  useEffect(() => {
    if (!visible) {
      return;
    }
    const referenceTime = (initialSetup?.reference_time_ms ?? 0) / 1000;
    setPins(initialSetup?.anchors ?? {});
    setCurrentTime(referenceTime);
    player.pause();
    player.currentTime = referenceTime;
  }, [initialSetup, player, visible]);

  useEffect(() => {
    if (sourceLoad.duration > 0) {
      setDuration(sourceLoad.duration);
    }
  }, [sourceLoad.duration]);

  useEffect(() => {
    if (visible) {
      setCurrentTime(timeUpdate.currentTime);
    }
  }, [timeUpdate.currentTime, visible]);

  const videoRect = useMemo(
    () => calculateVideoRect(videoLayout, videoSize, 'contain'),
    [videoLayout, videoSize]
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
    if (pinCount > 0) {
      return;
    }
    const boundedTime = Math.min(Math.max(time, 0), duration || time);
    player.pause();
    player.currentTime = boundedTime;
    setCurrentTime(boundedTime);
  };

  const resetForAnotherFrame = () => {
    Alert.alert(
      'Choose another frame?',
      'Changing the reference frame will clear all placed pins.',
      [
        { text: 'Keep Pins', style: 'cancel' },
        { text: 'Clear Pins', style: 'destructive', onPress: () => setPins({}) },
      ]
    );
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

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onCancel} presentationStyle="fullScreen">
      <SafeAreaView style={styles.safeArea}>
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
            player={player}
            style={styles.video}
            nativeControls={false}
            contentFit="contain"
            allowsPictureInPicture={false}
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
            onScrubEnd={handleSeek}
          />
          {pinCount > 0 ? (
            <Pressable onPress={resetForAnotherFrame} style={styles.linkButton}>
              <Text style={styles.linkText}>Choose another frame</Text>
            </Pressable>
          ) : (
            <Text style={styles.helperText}>Scrub to a frame where all landmarks and the collar are visible.</Text>
          )}
          <View style={styles.actions}>
            <Pressable onPress={() => setPins({})} disabled={pinCount === 0} style={styles.resetButton}>
              <Text style={[styles.resetText, pinCount === 0 && styles.disabledText]}>Reset pins</Text>
            </Pressable>
            <Button label="Use These Pins" onPress={savePins} disabled={!allPinsPlaced} style={styles.saveButton} />
          </View>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#05070A' },
  header: {
    minHeight: 54,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
  },
  headerButton: { width: 72, paddingVertical: 10 },
  headerButtonText: { color: tokens.colors.brand, fontSize: 15, fontWeight: '600' },
  headerSpacer: { width: 72 },
  title: { color: tokens.colors.textPrimary, fontSize: 18, fontWeight: '700' },
  instructions: { paddingHorizontal: 20, paddingVertical: 14, gap: 5 },
  instructionTitle: { color: tokens.colors.textPrimary, fontSize: 20, fontWeight: '700' },
  instructionText: { color: tokens.colors.textMuted, fontSize: 14, lineHeight: 20 },
  progressText: { color: tokens.colors.brand, fontSize: 13, fontWeight: '700' },
  videoArea: { flex: 1, position: 'relative', backgroundColor: '#000', overflow: 'hidden' },
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
  controls: { paddingHorizontal: 18, paddingTop: 16, paddingBottom: 12, gap: 12 },
  helperText: { color: tokens.colors.textMuted, fontSize: 12, lineHeight: 17, textAlign: 'center' },
  linkButton: { alignSelf: 'center', paddingVertical: 4 },
  linkText: { color: tokens.colors.brand, fontSize: 13, fontWeight: '600' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  resetButton: { paddingHorizontal: 10, paddingVertical: 12 },
  resetText: { color: tokens.colors.textPrimary, fontSize: 14, fontWeight: '600' },
  disabledText: { color: tokens.colors.textMuted },
  saveButton: { flex: 1 },
});
