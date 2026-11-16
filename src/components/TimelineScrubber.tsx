import { useCallback, useState } from 'react';
import { LayoutChangeEvent, Platform, StyleSheet, Text, View } from 'react-native';
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

  if (Platform.OS === 'web') return (
    <View style={styles.container}>
      <Text style={styles.timeText}>{formatSeconds(currentTime)}</Text>
      <input type="range" aria-label="Video position" min={0} max={Math.max(0, duration)} step={0.05}
        value={Math.min(Math.max(currentTime, 0), Math.max(0, duration))}
        aria-valuetext={`${formatSeconds(currentTime)} of ${formatSeconds(duration)}`}
        disabled={duration <= 0} style={{ flex: 1, minWidth: 0, height: 44, accentColor: tokens.colors.brand, cursor: 'pointer' }}
        onPointerDown={() => { setIsDragging(true); onScrubStart?.(); }}
        onChange={event => onSeek(Number(event.currentTarget.value))}
        onPointerUp={event => { setIsDragging(false); onScrubEnd?.(Number(event.currentTarget.value)); }}
        onPointerCancel={event => { setIsDragging(false); onScrubEnd?.(Number(event.currentTarget.value)); }}
        onBlur={event => { if (isDragging) { setIsDragging(false); onScrubEnd?.(Number(event.currentTarget.value)); } }}
        onKeyDown={event => {
          const offset = { ArrowLeft: -5, ArrowDown: -5, ArrowRight: 5, ArrowUp: 5 }[event.key];
          if (offset === undefined && event.key !== 'Home' && event.key !== 'End') return;
          event.preventDefault();
          onSeek(event.key === 'Home' ? 0 : event.key === 'End' ? duration : Math.max(0, Math.min(duration, currentTime + offset!)));
        }} />
      <Text style={styles.timeText}>{formatSeconds(duration)}</Text>
    </View>
  );

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
