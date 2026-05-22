import { StyleSheet, View } from 'react-native';
import { BarbellPath, BarbellPathPoint } from '../types/videoAnalysis';
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

function progressivePoints(points: BarbellPathPoint[], currentTime: number) {
  const visible = points.filter((point) => point.time <= currentTime);
  const next = points.find((point) => point.time > currentTime);
  const previous = visible[visible.length - 1];

  if (!previous || !next) {
    return visible;
  }

  const gap = next.time - previous.time;
  if (gap <= 0 || gap > 0.5) {
    return visible;
  }

  const progress = Math.min(Math.max((currentTime - previous.time) / gap, 0), 1);
  return [
    ...visible,
    {
      time: currentTime,
      x: previous.x + ((next.x - previous.x) * progress),
      y: previous.y + ((next.y - previous.y) * progress),
      confidence: Math.min(previous.confidence, next.confidence),
    },
  ];
}

export default function BarbellPathOverlay({
  path,
  currentTime,
  containerSize,
  videoSize,
  contentFit = 'cover',
  confidenceThreshold = 0.25,
}: BarbellPathOverlayProps) {
  if (!path?.available || path.points.length <= 0 || containerSize.width <= 0 || containerSize.height <= 0) {
    return null;
  }

  const rect = calculateVideoRect(containerSize, videoSize, contentFit);
  const mappedPoints = progressivePoints(
    path.points.filter((point) => point.confidence >= confidenceThreshold),
    currentTime
  ).map((point) => ({
    x: rect.x + (point.x * rect.width),
    y: rect.y + (point.y * rect.height),
    time: point.time,
  }));

  if (mappedPoints.length <= 0) {
    return null;
  }

  const lastPoint = mappedPoints[mappedPoints.length - 1];

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {mappedPoints.slice(1).map((point, index) => {
        const previous = mappedPoints[index];
        if (!previous || point.time - previous.time > 0.5) {
          return null;
        }

        return <Line key={`${previous.time}-${point.time}`} from={previous} to={point} />;
      })}
      <View style={[styles.currentPoint, { left: lastPoint.x - 6, top: lastPoint.y - 6 }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    position: 'absolute',
    height: 4,
    borderRadius: 4,
    backgroundColor: 'rgba(64, 235, 52, 0.72)',
    transformOrigin: '0px 2px',
  },
  currentPoint: {
    position: 'absolute',
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: 'rgba(64, 235, 52, 0.82)',
    borderWidth: 2,
    borderColor: '#FFFFFF',
  },
});
