import { StyleSheet, View } from 'react-native';
import { VideoPoseFrame } from '../types/videoAnalysis';
import {
  ContentFit,
  Size,
  filterSquatKeypoints,
  getSquatPoseConnections,
  mapNormalizedKeypoint,
} from '../utils/videoReview';

type PoseOverlayProps = {
  frame: VideoPoseFrame | null;
  containerSize: Size;
  videoSize: Size;
  contentFit?: ContentFit;
  cameraView?: string;
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
  confidenceThreshold = 0.35,
}: PoseOverlayProps) {
  // The overlay is pure rendering; it never handles touch input.
  if (!frame || containerSize.width <= 0 || containerSize.height <= 0) {
    return null;
  }

  const squatKeypoints = filterSquatKeypoints(frame, confidenceThreshold);
  // Map the normalized pose points into the rendered video rectangle.
  const connections = getSquatPoseConnections(squatKeypoints, cameraView);
  const mappedKeypoints = new Map(
    squatKeypoints.map((keypoint) => {
      const mapped = mapNormalizedKeypoint(keypoint, containerSize, videoSize, contentFit);
      return [mapped.name, mapped];
    })
  );

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

      {[...mappedKeypoints.values()].map((point) => (
        <View
          key={point.name}
          style={[
            styles.point,
            {
              left: point.x - 3,
              top: point.y - 3,
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    position: 'absolute',
    height: 2,
    borderRadius: 2,
    backgroundColor: 'rgba(31, 107, 255, 0.88)',
    transformOrigin: '0px 1px',
  },
  point: {
    position: 'absolute',
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#F5F8FF',
    borderWidth: 1,
    borderColor: '#1F6BFF',
  },
});
