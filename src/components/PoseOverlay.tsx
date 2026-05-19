import { StyleSheet, Text, View } from 'react-native';
import { VideoPoseFrame } from '../types/videoAnalysis';
import {
  ContentFit,
  Size,
  getSquatOverlayKeypoints,
  getSquatPoseConnections,
  mapNormalizedKeypoint,
} from '../utils/videoReview';

const POINT_SIZE = 12;
const LABEL_WIDTH = 76;
const LABEL_HEIGHT = 22;

type PoseOverlayProps = {
  frame: VideoPoseFrame | null;
  containerSize: Size;
  videoSize: Size;
  contentFit?: ContentFit;
  cameraView?: string;
  selectedSide?: string | null;
  confidenceThreshold?: number;
};

function Line({ from, to }: { from: { x: number; y: number }; to: { x: number; y: number } }) {
  // Draw each skeleton segment as a rotated line.
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  const angle = `${Math.atan2(dy, dx)}rad`;

  return (
    <View
      style={[
        styles.line,
        {
          left: from.x,
          top: from.y,
          width: length,
          transform: [{ rotateZ: angle }],
        },
      ]}
    />
  );
}

export default function PoseOverlay({
  frame,
  containerSize,
  videoSize,
  contentFit = 'cover',
  cameraView,
  selectedSide,
  confidenceThreshold = 0.35,
}: PoseOverlayProps) {
  // The overlay is pure rendering; it never handles touch input.
  if (!frame || containerSize.width <= 0 || containerSize.height <= 0) {
    return null;
  }

  const squatKeypoints = getSquatOverlayKeypoints(
    frame,
    cameraView,
    confidenceThreshold,
    selectedSide
  );
  // Map the normalized pose points into the rendered video rectangle.
  const connections = getSquatPoseConnections(squatKeypoints, cameraView, selectedSide);
  const mappedKeypoints = new Map(
    squatKeypoints.map((keypoint) => {
      const mapped = mapNormalizedKeypoint(keypoint, containerSize, videoSize, contentFit);
      return [mapped.name, { ...mapped, label: keypoint.label }];
    })
  );
  const visiblePoints = [...mappedKeypoints.values()];

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {connections.map(([fromName, toName]) => {
        const from = mappedKeypoints.get(fromName);
        const to = mappedKeypoints.get(toName);

        if (!from || !to) {
          return null;
        }

        return <Line key={`${fromName}-${toName}`} from={from} to={to} />;
      })}

      {visiblePoints.map((point) => {
        const labelLeft = Math.min(
          Math.max(point.x + 10, 0),
          Math.max(containerSize.width - LABEL_WIDTH, 0)
        );
        const labelTop = Math.min(
          Math.max(point.y - LABEL_HEIGHT - 4, 0),
          Math.max(containerSize.height - LABEL_HEIGHT, 0)
        );
        const isEstimated = point.confidence < 0.5;
        const pointOpacity = isEstimated ? 0.58 : 1;

        return (
          <View key={point.name}>
            <View
              style={[
                styles.point,
                isEstimated && styles.estimatedPoint,
                {
                  left: point.x - (POINT_SIZE / 2),
                  top: point.y - (POINT_SIZE / 2),
                  opacity: pointOpacity,
                },
              ]}
            />
            <Text
              numberOfLines={1}
              style={[
                styles.label,
                isEstimated && styles.estimatedLabel,
                {
                  left: labelLeft,
                  top: labelTop,
                  opacity: pointOpacity,
                },
              ]}
            >
              {point.label}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    position: 'absolute',
    height: 3,
    borderRadius: 3,
    backgroundColor: 'rgba(31, 107, 255, 0.92)',
    transformOrigin: '0px 1.5px',
  },
  point: {
    position: 'absolute',
    width: POINT_SIZE,
    height: POINT_SIZE,
    borderRadius: POINT_SIZE / 2,
    backgroundColor: '#FFF500',
    borderWidth: 2,
    borderColor: '#1F6BFF',
  },
  estimatedPoint: {
    backgroundColor: '#FFFFFF',
    borderColor: '#FFB020',
    borderStyle: 'dashed',
  },
  label: {
    position: 'absolute',
    width: LABEL_WIDTH,
    height: LABEL_HEIGHT,
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '800',
    lineHeight: 20,
    textShadowColor: 'rgba(0, 0, 0, 0.75)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  estimatedLabel: {
    color: '#FFE4A3',
  },
});
