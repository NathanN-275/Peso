import { StyleSheet, View } from 'react-native';
import { BarbellPath } from '../types/videoAnalysis';
import {
  calculateVideoRect,
  ContentFit,
  findInterpolatedBarbellPathPoint,
  Size,
} from '../utils/videoReview';

type BarbellPathOverlayProps = {
  path?: BarbellPath;
  currentTime: number;
  containerSize: Size;
  videoSize: Size;
  contentFit?: ContentFit;
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
  currentTime,
  containerSize,
  videoSize,
  contentFit = 'cover',
}: BarbellPathOverlayProps) {
  const pathPoints = Array.isArray(path?.points) ? path.points : [];
  const elapsedPoints = pathPoints.filter((point) => point.time <= currentTime);
  const currentPoint = findInterpolatedBarbellPathPoint(pathPoints, currentTime);
  const visiblePoints = currentPoint
    ? [
      ...elapsedPoints.filter((point) => point.time < currentPoint.time),
      currentPoint,
    ]
    : elapsedPoints;
  const rect = calculateVideoRect(containerSize, videoSize, contentFit);

  if (
    path?.available !== true
    || pathPoints.length < 2
    || containerSize.width <= 0
    || containerSize.height <= 0
    || visiblePoints.length < 1
  ) {
    return null;
  }

  const mappedPoints = visiblePoints
    .map((point) => ({
      x: rect.x + (point.x * rect.width),
      y: rect.y + (point.y * rect.height),
      time: point.time,
      trackingState: point.trackingState,
      coastingFrame: point.coastingFrame,
      stationaryHardwareRejected: point.stationaryHardwareRejected,
    }));

  if (mappedPoints.length < 1) {
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
      {currentPoint ? (
        <View
          style={[
            styles.currentPoint,
            (
              currentPoint.trackingState === 'automatic'
              || currentPoint.trackingState === 'estimated'
              || currentPoint.coastingFrame === true
              || currentPoint.stationaryHardwareRejected === true
            )
              && styles.estimatedCurrentPoint,
            { left: lastPoint.x - 7, top: lastPoint.y - 7 },
          ]}
        />
      ) : null}
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
  estimatedCurrentPoint: {
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
    borderColor: '#FFB020',
    borderStyle: 'dashed',
  },
});
