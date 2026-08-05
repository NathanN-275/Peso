import { StyleSheet, View } from 'react-native';
import {
  FRONT_TRAIL_WINDOW_SECONDS,
  frontTrailWindowFrames,
  shouldConnectFrontTrailSamples,
  shouldShowFrontMotionTrails,
} from '../../lib/frontTrackingPolicy';
import { VideoPoseFrame, VideoPoseKeypoint } from '../types/videoAnalysis';
import {
  ContentFit,
  mapNormalizedKeypoint,
  Size,
} from '../utils/videoReview';

const TRAIL_NAMES = [
  'left_knee',
  'right_knee',
  'left_ankle',
  'right_ankle',
] as const;

const TRAIL_COLORS: Record<(typeof TRAIL_NAMES)[number], string> = {
  left_knee: '#FFB454',
  right_knee: '#FFD090',
  left_ankle: '#5DDBA6',
  right_ankle: '#92E8C6',
};

type TrailName = (typeof TRAIL_NAMES)[number];

type JointMotionTrailOverlayProps = {
  frames?: VideoPoseFrame[];
  currentTime: number;
  containerSize: Size;
  videoSize: Size;
  contentFit?: ContentFit;
  exercise?: string | null;
  cameraView?: string;
};

function isUsablePoint(point: VideoPoseKeypoint | undefined) {
  return Boolean(
    point
    && point.confidence >= 0.15
    && point.chainValid !== false
    && point.visualOnly !== true
  );
}

function TrailSegment({
  from,
  to,
  color,
  opacity,
  estimated,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
  opacity: number;
  estimated: boolean;
}) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  return (
    <View
      style={[
        styles.segment,
        estimated && styles.estimatedSegment,
        {
          left: from.x,
          top: from.y,
          width: Math.hypot(dx, dy),
          borderColor: color,
          backgroundColor: estimated ? 'transparent' : color,
          opacity,
          transform: [{ rotateZ: `${Math.atan2(dy, dx)}rad` }],
        },
      ]}
    />
  );
}

export default function JointMotionTrailOverlay({
  frames,
  currentTime,
  containerSize,
  videoSize,
  contentFit = 'cover',
  exercise,
  cameraView,
}: JointMotionTrailOverlayProps) {
  if (
    !shouldShowFrontMotionTrails({ cameraView, exercise })
    || !frames?.length
    || containerSize.width <= 0
    || containerSize.height <= 0
  ) {
    return null;
  }

  const startTime = Math.max(currentTime - FRONT_TRAIL_WINDOW_SECONDS, 0);
  const history = frontTrailWindowFrames(frames, currentTime);

  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.overlay]}>
      {TRAIL_NAMES.flatMap((name: TrailName) => history.slice(1).map((frame, index) => {
        const previousFrame = history[index];
        const previous = previousFrame.keypoints.find((point) => point.name === name);
        const current = frame.keypoints.find((point) => point.name === name);
        if (
          !isUsablePoint(previous)
          || !isUsablePoint(current)
          || !shouldConnectFrontTrailSamples(previousFrame.time, frame.time)
        ) {
          return null;
        }

        const from = mapNormalizedKeypoint(
          previous as VideoPoseKeypoint,
          containerSize,
          videoSize,
          contentFit
        );
        const to = mapNormalizedKeypoint(
          current as VideoPoseKeypoint,
          containerSize,
          videoSize,
          contentFit
        );
        const estimated = previous?.trackingState === 'estimated'
          || current?.trackingState === 'estimated';
        const age = Math.min(
          Math.max((frame.time - startTime) / FRONT_TRAIL_WINDOW_SECONDS, 0),
          1
        );
        return (
          <TrailSegment
            key={`${name}-${previousFrame.time}-${frame.time}`}
            from={from}
            to={to}
            color={estimated ? '#FFB020' : TRAIL_COLORS[name]}
            opacity={0.14 + (age * 0.72)}
            estimated={estimated}
          />
        );
      }))}
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    zIndex: 10,
    elevation: 10,
  },
  segment: {
    position: 'absolute',
    height: 3,
    borderRadius: 3,
    transformOrigin: '0px 1.5px',
  },
  estimatedSegment: {
    height: 0,
    borderTopWidth: 2,
    borderStyle: 'dashed',
  },
});
