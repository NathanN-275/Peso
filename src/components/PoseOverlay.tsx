import { StyleSheet, Text, View } from 'react-native';
import { layoutTrackingLabels } from '../../lib/trackingOverlayPolicy';
import { VideoPoseFrame } from '../types/videoAnalysis';
import {
  ContentFit,
  Size,
  getSquatOverlayKeypoints,
  getSquatPoseConnections,
  mapNormalizedKeypoint,
} from '../utils/videoReview';

const POINT_SIZE = 12;
const LABEL_WIDTH = 104;
const LABEL_HEIGHT = 22;

type PoseOverlayProps = {
  frame: VideoPoseFrame | null;
  containerSize: Size;
  videoSize: Size;
  contentFit?: ContentFit;
  cameraView?: string;
  selectedSide?: string | null;
  confidenceThreshold?: number;
  preferUpperBackKeypoint?: boolean;
};

function Line({
  from,
  to,
  estimated = false,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
  estimated?: boolean;
}) {
  // Draw each skeleton segment as a rotated line.
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  const angle = `${Math.atan2(dy, dx)}rad`;

  return (
    <View
      style={[
        styles.line,
        estimated && styles.estimatedLine,
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
  preferUpperBackKeypoint = false,
}: PoseOverlayProps) {
  // The overlay is pure rendering; it never handles touch input.
  if (!frame || containerSize.width <= 0 || containerSize.height <= 0) {
    return null;
  }

  const squatKeypoints = getSquatOverlayKeypoints(
    frame,
    cameraView,
    confidenceThreshold,
    selectedSide,
    preferUpperBackKeypoint
  );
  // Map the normalized pose points into the rendered video rectangle.
  const connections = getSquatPoseConnections(
    squatKeypoints,
    cameraView,
    selectedSide,
    preferUpperBackKeypoint
  );
  const mappedKeypoints = new Map(
    squatKeypoints.map((keypoint) => {
      const mapped = mapNormalizedKeypoint(keypoint, containerSize, videoSize, contentFit);
      return [
        mapped.name,
        {
          ...mapped,
          label: keypoint.label,
          chainValid: keypoint.chainValid,
          visualOnly: keypoint.visualOnly,
          manualSource: keypoint.manualSource,
          acceptedSource: keypoint.acceptedSource,
        },
      ];
    })
  );
  const labelLayout = layoutTrackingLabels(
    [...mappedKeypoints.values()]
      .filter((point) => point.visualOnly !== true && point.chainValid !== false)
      .map((point) => ({
        id: point.name,
        x: point.x,
        y: point.y,
        labelWidth: LABEL_WIDTH,
        labelHeight: LABEL_HEIGHT,
      })),
    containerSize,
    { gap: 8 }
  );
  const labelsByName = new Map(labelLayout.map((point) => [point.id, point]));
  const visiblePoints = [...mappedKeypoints.values()];

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {connections.map(([fromName, toName]) => {
        const from = mappedKeypoints.get(fromName);
        const to = mappedKeypoints.get(toName);

        if (!from || !to) {
          return null;
        }

        if (
          from.visualOnly === true
          || to.visualOnly === true
          || from.chainValid === false
          || to.chainValid === false
        ) {
          return null;
        }

        const isEstimated = [from.trackingState, to.trackingState].some(
          (state) => state === 'automatic' || state === 'estimated'
        );
        return <Line key={`${fromName}-${toName}`} from={from} to={to} estimated={isEstimated} />;
      })}

      {visiblePoints.map((point) => {
        const isVisualOnly = point.visualOnly === true || point.chainValid === false;
        const isEstimated = point.confidence < 0.5
          || point.trackingState === 'automatic'
          || point.trackingState === 'estimated'
          || isVisualOnly;
        const pointOpacity = isVisualOnly ? 0.42 : isEstimated ? 0.58 : 1;
        if (isVisualOnly) {
          return (
            <View
              key={point.name}
              style={[
                styles.point,
                styles.estimatedPoint,
                styles.visualOnlyPoint,
                {
                  left: point.x - (POINT_SIZE / 2),
                  top: point.y - (POINT_SIZE / 2),
                  opacity: pointOpacity,
                },
              ]}
            />
          );
        }
        const label = labelsByName.get(point.name);
        if (!label) {
          return null;
        }
        const labelCenter = {
          x: label.labelX + (label.labelWidth / 2),
          y: label.labelY + (label.labelHeight / 2),
        };

        return (
          <View key={point.name}>
            {label.displaced ? (
              <Line from={point} to={labelCenter} estimated={isEstimated} />
            ) : null}
            <View
              style={[
                styles.point,
                isEstimated && styles.estimatedPoint,
                isVisualOnly && styles.visualOnlyPoint,
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
                isVisualOnly && styles.visualOnlyLabel,
                {
                  left: label.labelX,
                  top: label.labelY,
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
  estimatedLine: {
    height: 0,
    backgroundColor: 'transparent',
    borderTopWidth: 2,
    borderStyle: 'dashed',
    borderColor: 'rgba(255, 176, 32, 0.82)',
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
  visualOnlyPoint: {
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
    borderColor: 'rgba(255, 176, 32, 0.72)',
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
  visualOnlyLabel: {
    color: 'rgba(255, 228, 163, 0.72)',
  },
});
