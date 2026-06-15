import { StyleSheet, Text, View } from 'react-native';
import { layoutTrackingLabels } from '../../lib/trackingOverlayPolicy';
import {
  TRACKING_PIN_NAMES,
  TrackingPinName,
  TrackingReference,
} from '../types/trackingSetup';
import { calculateVideoRect, ContentFit, Size } from '../utils/videoReview';

const PIN_SIZE = 22;
const LABEL_HEIGHT = 20;

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

type TrackingReferenceOverlayProps = {
  reference: TrackingReference;
  containerSize: Size;
  videoSize: Size;
  contentFit?: ContentFit;
};

function LeaderLine({
  from,
  to,
  color,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
}) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  return (
    <View
      style={[
        styles.leaderLine,
        {
          left: from.x,
          top: from.y,
          width: Math.hypot(dx, dy),
          backgroundColor: color,
          transform: [{ rotateZ: `${Math.atan2(dy, dx)}rad` }],
        },
      ]}
    />
  );
}

export default function TrackingReferenceOverlay({
  reference,
  containerSize,
  videoSize,
  contentFit = 'cover',
}: TrackingReferenceOverlayProps) {
  if (containerSize.width <= 0 || containerSize.height <= 0) {
    return null;
  }
  const rect = calculateVideoRect(containerSize, videoSize, contentFit);
  const points = TRACKING_PIN_NAMES.map((name) => ({
    id: name,
    x: rect.x + (reference.anchors[name].x * rect.width),
    y: rect.y + (reference.anchors[name].y * rect.height),
    labelWidth: name === 'barbell' ? 104 : 76,
    labelHeight: LABEL_HEIGHT,
  }));
  const labels = layoutTrackingLabels(points, containerSize, { gap: 7 });

  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.overlay]}>
      {labels.map((point) => {
        const name = point.id as TrackingPinName;
        const labelCenter = {
          x: point.labelX + (point.labelWidth / 2),
          y: point.labelY + (point.labelHeight / 2),
        };
        return (
          <View key={name}>
            {point.displaced ? (
              <LeaderLine from={point} to={labelCenter} color={PIN_COLORS[name]} />
            ) : null}
            <View
              style={[
                styles.pin,
                {
                  left: point.x - (PIN_SIZE / 2),
                  top: point.y - (PIN_SIZE / 2),
                  backgroundColor: PIN_COLORS[name],
                },
              ]}
            >
              <Text style={styles.plus}>+</Text>
            </View>
            <Text
              numberOfLines={1}
              style={[
                styles.label,
                {
                  left: point.labelX,
                  top: point.labelY,
                  width: point.labelWidth,
                  color: PIN_COLORS[name],
                },
              ]}
            >
              {PIN_LABELS[name]}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { zIndex: 30, elevation: 30 },
  leaderLine: {
    position: 'absolute',
    height: 1,
    opacity: 0.8,
    transformOrigin: '0px 0.5px',
  },
  pin: {
    position: 'absolute',
    width: PIN_SIZE,
    height: PIN_SIZE,
    borderRadius: PIN_SIZE / 2,
    borderWidth: 2,
    borderColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  plus: { color: '#05070A', fontSize: 20, fontWeight: '700', lineHeight: 20 },
  label: {
    position: 'absolute',
    height: LABEL_HEIGHT,
    paddingHorizontal: 4,
    borderRadius: 4,
    backgroundColor: 'rgba(0,0,0,0.78)',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 18,
    textAlign: 'center',
  },
});
