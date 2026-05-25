import { StyleSheet, View } from 'react-native';
import { BarbellPath } from '../types/videoAnalysis';
import { calculateVideoRect, ContentFit, Size } from '../utils/videoReview';

type BarbellPathOverlayProps = {
  path?: BarbellPath;
  currentTime: number;
  containerSize: Size;
  videoSize: Size;
  contentFit?: ContentFit;
  confidenceThreshold?: number;
};

function Line({ from, to }: { from: { x: number; y: number }; to: { x: number; y: number } }) {
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

export default function BarbellPathOverlay({
  path,
  currentTime: _currentTime,
  containerSize,
  videoSize,
  contentFit = 'cover',
  confidenceThreshold = 0.25,
}: BarbellPathOverlayProps) {
  const pathPoints = Array.isArray(path?.points) ? path.points : [];

  if (
    path?.available !== true
    || pathPoints.length < 2
    || containerSize.width <= 0
    || containerSize.height <= 0
  ) {
    return null;
  }

  const rect = calculateVideoRect(containerSize, videoSize, contentFit);
  const mappedPoints = pathPoints
    .filter((point) => point.confidence >= confidenceThreshold)
    .map((point) => ({
      x: rect.x + (point.x * rect.width),
      y: rect.y + (point.y * rect.height),
      time: point.time,
    }));

  if (mappedPoints.length < 2) {
    return null;
  }

  const firstPoint = mappedPoints[0];
  const lastPoint = mappedPoints[mappedPoints.length - 1];

  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.overlay]}>
      {mappedPoints.slice(1).map((point, index) => {
        const previous = mappedPoints[index];
        if (!previous || point.time - previous.time > 0.5) {
          return null;
        }

        return <Line key={`${previous.time}-${point.time}`} from={previous} to={point} />;
      })}
      <View style={[styles.startPoint, { left: firstPoint.x - 3, top: firstPoint.y - 3 }]} />
      <View style={[styles.currentPoint, { left: lastPoint.x - 7, top: lastPoint.y - 7 }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    zIndex: 20,
    elevation: 20,
  },
  line: {
    position: 'absolute',
    height: 3,
    borderRadius: 3,
    backgroundColor: 'rgba(64, 235, 52, 0.86)',
    transformOrigin: '0px 1.5px',
  },
  startPoint: {
    position: 'absolute',
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: 'rgba(64, 235, 52, 0.88)',
    borderWidth: 1,
    borderColor: '#FFFFFF',
  },
  currentPoint: {
    position: 'absolute',
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: 'rgba(64, 235, 52, 0.92)',
    borderWidth: 2,
    borderColor: '#FFFFFF',
  },
});
