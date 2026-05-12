import { useCallback, useState } from 'react';
import { LayoutChangeEvent, StyleSheet, Text, View } from 'react-native';
import tokens from '../theme/tokens';
import { formatSeconds, getTimeFromTrackX } from '../utils/videoReview';

type TimelineScrubberProps = {
  currentTime: number;
  duration: number;
  onSeek: (time: number) => void;
  onScrubStart?: () => void;
  onScrubEnd?: (time: number) => void;
};

export default function TimelineScrubber({
  currentTime,
  duration,
  onSeek,
  onScrubStart,
  onScrubEnd,
}: TimelineScrubberProps) {
  const [trackWidth, setTrackWidth] = useState(0);
  const [dragTime, setDragTime] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const displayedTime = dragTime ?? currentTime;
  const progress = duration > 0 ? Math.min(Math.max(displayedTime / duration, 0), 1) : 0;

  const updateTimeFromLocalX = useCallback((x: number) => {
    const nextTime = getTimeFromTrackX(x, trackWidth, duration);
    setDragTime(nextTime);
    onSeek(nextTime);
  }, [duration, onSeek, trackWidth]);

  const updateTimeFromResponderX = useCallback((locationX: number) => {
    updateTimeFromLocalX(locationX);
  }, [updateTimeFromLocalX]);

  const finishScrub = useCallback(
    (locationX?: number) => {
      const nextTime = typeof locationX === 'number'
        ? getTimeFromTrackX(locationX, trackWidth, duration)
        : dragTime ?? currentTime;

      setIsDragging(false);
      setDragTime(null);
      onScrubEnd?.(nextTime);
    },
    [currentTime, dragTime, duration, onScrubEnd, trackWidth]
  );

  const handleStart = useCallback(
    (locationX: number) => {
      setIsDragging(true);
      onScrubStart?.();
      updateTimeFromResponderX(locationX);
    },
    [onScrubStart, updateTimeFromResponderX]
  );

  const handleMove = useCallback(
    (locationX: number) => {
      if (!isDragging) {
        return;
      }

      updateTimeFromResponderX(locationX);
    },
    [isDragging, updateTimeFromResponderX]
  );

  const handleTrackLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    setTrackWidth(nativeEvent.layout.width);
  };

  return (
    <View style={styles.container}>
      <Text style={styles.timeText}>{formatSeconds(displayedTime)}</Text>
      <View
        accessibilityRole="adjustable"
        style={styles.track}
        onLayout={handleTrackLayout}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={(event) => {
          handleStart(event.nativeEvent.locationX);
        }}
        onResponderMove={(event) => {
          handleMove(event.nativeEvent.locationX);
        }}
        onResponderRelease={(event) => {
          finishScrub(event.nativeEvent.locationX);
        }}
        onResponderTerminate={(event) => {
          finishScrub(event.nativeEvent.locationX);
        }}
        onResponderTerminationRequest={() => false}
      >
        <View pointerEvents="none" style={styles.trackRail} />
        <View pointerEvents="none" style={[styles.trackFill, { width: `${progress * 100}%` }]} />
        <View pointerEvents="none" style={[styles.thumb, { left: `${progress * 100}%` }]} />
      </View>
      <Text style={styles.timeText}>{formatSeconds(duration)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  timeText: {
    width: 42,
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '600',
    textAlign: 'center',
  },
  track: {
    flex: 1,
    height: 28,
    justifyContent: 'center',
    position: 'relative',
  },
  trackRail: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 4,
    borderRadius: 4,
    backgroundColor: '#3A3A3A',
  },
  trackFill: {
    position: 'absolute',
    left: 0,
    height: 4,
    borderRadius: 4,
    backgroundColor: tokens.colors.brand,
  },
  thumb: {
    position: 'absolute',
    width: 16,
    height: 16,
    marginLeft: -8,
    borderRadius: 8,
    backgroundColor: tokens.colors.textPrimary,
    borderWidth: 3,
    borderColor: tokens.colors.brand,
  },
});
