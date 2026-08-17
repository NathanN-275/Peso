import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';
import { getSideSquatRecordingGuidance } from '../../lib/sideSquatRecordingGuidancePolicy';
import type { VideoSetupSelection } from '../constants/videoSetup';
import tokens from '../theme/tokens';

type SideSquatRecordingGuideProps = {
  variant?: 'full' | 'compact' | 'essential';
  setup: VideoSetupSelection | null;
};

export default function SideSquatRecordingGuide({
  variant = 'full',
  setup,
}: SideSquatRecordingGuideProps) {
  const guidance = getSideSquatRecordingGuidance(setup);

  if (!guidance) {
    return null;
  }

  if (variant === 'compact') {
    return (
      <View
        accessibilityLabel={`Side-view recording guidance. ${guidance.compactSummary}`}
        style={styles.compactCard}
      >
        <Ionicons name="scan-outline" size={18} color={tokens.colors.brand} />
        <Text style={styles.compactText}>{guidance.compactSummary}</Text>
      </View>
    );
  }

  if (variant === 'essential') {
    return (
      <View
        accessibilityLabel="Three essential side-view recording tips"
        style={styles.essentialCard}
      >
        <View style={styles.essentialHeading}>
          <Ionicons name="scan-outline" size={18} color={tokens.colors.brand} />
          <Text style={styles.essentialTitle}>3 setup tips</Text>
        </View>
        <View style={styles.essentialList}>
          {guidance.essentialItems.map((item) => (
            <View key={item.id} style={styles.essentialRow}>
              <Ionicons name="checkmark-circle-outline" size={16} color="#77D8A2" />
              <Text style={styles.essentialText}>{item.text}</Text>
            </View>
          ))}
        </View>
      </View>
    );
  }

  return (
    <View
      accessibilityLabel="Side-view squat recording guidance"
      style={styles.card}
    >
      <View style={styles.headingRow}>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>Before you record or choose a video</Text>
          <Text style={styles.title}>{guidance.title}</Text>
          <Text style={styles.summary}>{guidance.summary}</Text>
        </View>
        <View
          accessibilityLabel="Framing guide showing a full lifter with the phone at hip height"
          style={styles.framingGuide}
        >
          <View style={styles.guideFrame}>
            <Ionicons name="body-outline" size={62} color={tokens.colors.textPrimary} />
            {guidance.barbellSquat ? <View style={styles.barbellLine} /> : null}
            {guidance.barbellSquat ? <View style={styles.collarMarker} /> : null}
          </View>
          <View style={styles.hipHeightLine} />
          <View style={styles.phoneMarker}>
            <Ionicons name="phone-portrait-outline" size={20} color={tokens.colors.brand} />
          </View>
        </View>
      </View>

      <View style={styles.itemList}>
        {guidance.items.map((item) => (
          <View key={item.id} style={styles.itemRow}>
            <Ionicons name="checkmark-circle-outline" size={18} color="#77D8A2" />
            <Text style={styles.itemText}>{item.text}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    width: '100%',
    marginTop: 16,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: tokens.colors.secondaryBorder,
    backgroundColor: '#0F151D',
    paddingHorizontal: 16,
    paddingVertical: 16,
    gap: 16,
  },
  headingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  headingCopy: {
    flex: 1,
    minWidth: 0,
  },
  eyebrow: {
    color: tokens.colors.brand,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  title: {
    marginTop: 5,
    color: tokens.colors.textPrimary,
    fontSize: 18,
    lineHeight: 23,
    fontWeight: '800',
  },
  summary: {
    marginTop: 5,
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  framingGuide: {
    width: 86,
    height: 116,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: '#3B4A60',
    backgroundColor: '#080B10',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    overflow: 'hidden',
  },
  guideFrame: {
    width: 54,
    height: 94,
    borderWidth: 1,
    borderColor: '#53647D',
    borderRadius: 5,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  hipHeightLine: {
    position: 'absolute',
    left: 2,
    right: 2,
    top: 58,
    height: StyleSheet.hairlineWidth,
    backgroundColor: tokens.colors.brand,
  },
  phoneMarker: {
    position: 'absolute',
    right: 1,
    top: 47,
    backgroundColor: '#080B10',
  },
  barbellLine: {
    position: 'absolute',
    top: 34,
    left: 6,
    right: 6,
    height: 2,
    backgroundColor: '#A7B4C8',
  },
  collarMarker: {
    position: 'absolute',
    top: 31,
    right: 8,
    width: 7,
    height: 8,
    borderRadius: 2,
    backgroundColor: '#B8F06A',
  },
  itemList: {
    gap: 9,
  },
  itemRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 9,
  },
  itemText: {
    flex: 1,
    color: '#D8DEE8',
    fontSize: 13,
    lineHeight: 19,
  },
  compactCard: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(85, 139, 255, 0.55)',
    backgroundColor: 'rgba(5, 10, 18, 0.86)',
    paddingHorizontal: 11,
    paddingVertical: 9,
  },
  compactText: {
    flex: 1,
    color: tokens.colors.textPrimary,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  essentialCard: {
    width: '100%',
    marginTop: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: tokens.colors.secondaryBorder,
    backgroundColor: '#0F151D',
    paddingHorizontal: 12,
    paddingVertical: 11,
    gap: 8,
  },
  essentialHeading: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  essentialTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.45,
  },
  essentialList: {
    gap: 6,
  },
  essentialRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
  },
  essentialText: {
    flex: 1,
    color: '#D8DEE8',
    fontSize: 12,
    lineHeight: 17,
  },
});
