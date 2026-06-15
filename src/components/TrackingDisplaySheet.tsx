import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import tokens from '../theme/tokens';
import type { TrackingAssistance, TrackingPinName } from '../types/trackingSetup';
import ReviewBottomSheet from './ReviewBottomSheet';

type TrackingDisplaySheetProps = {
  visible: boolean;
  poseAvailable: boolean;
  poseEnabled: boolean;
  barbellAvailable: boolean;
  barbellEnabled: boolean;
  trackingAssistance?: TrackingAssistance | null;
  onPoseEnabledChange: (enabled: boolean) => void;
  onBarbellEnabledChange: (enabled: boolean) => void;
  onClose: () => void;
};

type TrackingOptionProps = {
  label: string;
  description: string;
  available: boolean;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
};

function TrackingOption({
  label,
  description,
  available,
  enabled,
  onEnabledChange,
}: TrackingOptionProps) {
  const effectiveEnabled = available && enabled;

  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityHint={available ? description : 'Unavailable for this video'}
      accessibilityState={{ checked: effectiveEnabled, disabled: !available }}
      disabled={!available}
      onPress={() => onEnabledChange(!effectiveEnabled)}
      style={({ pressed }) => [
        styles.option,
        !available && styles.optionDisabled,
        pressed && available && styles.optionPressed,
      ]}
    >
      <View style={styles.optionCopy}>
        <Text style={[styles.optionLabel, !available && styles.disabledText]}>{label}</Text>
        <Text style={[styles.optionDescription, !available && styles.disabledText]}>
          {available ? description : 'Unavailable for this video'}
        </Text>
      </View>
      <View
        accessible={false}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        pointerEvents="none"
      >
        <Switch
          value={effectiveEnabled}
          disabled={!available}
          trackColor={{ false: '#3A4352', true: tokens.colors.brand }}
          thumbColor={tokens.colors.textPrimary}
          ios_backgroundColor="#3A4352"
        />
      </View>
    </Pressable>
  );
}

export default function TrackingDisplaySheet({
  visible,
  poseAvailable,
  poseEnabled,
  barbellAvailable,
  barbellEnabled,
  trackingAssistance,
  onPoseEnabledChange,
  onBarbellEnabledChange,
  onClose,
}: TrackingDisplaySheetProps) {
  const assistanceMode = trackingAssistance?.actualMode === 'pin_assisted'
    ? 'Pin-assisted'
    : trackingAssistance?.requestedMode === 'pins'
      ? 'Automatic fallback'
      : 'Automatic';
  const coverageEntries = Object.entries(trackingAssistance?.coverage ?? {}) as Array<
    [TrackingPinName, number]
  >;

  return (
    <ReviewBottomSheet visible={visible} title="Tracking display" onClose={onClose}>
      <View style={styles.content}>
        <Text style={styles.helperText}>
          Choose what appears over the video. Turn both off for a clean view.
        </Text>
        <View style={styles.options}>
          <TrackingOption
            label="Pose overlay"
            description="Body landmarks and connections"
            available={poseAvailable}
            enabled={poseEnabled}
            onEnabledChange={onPoseEnabledChange}
          />
          <TrackingOption
            label="Barbell path"
            description="Tracked bar path over time"
            available={barbellAvailable}
            enabled={barbellEnabled}
            onEnabledChange={onBarbellEnabledChange}
          />
        </View>
        {trackingAssistance?.requestedMode === 'pins' ? (
          <View style={styles.assistancePanel}>
            <View style={styles.assistanceHeadingRow}>
              <Text style={styles.assistanceHeading}>Tracking assistance</Text>
              <Text
                style={[
                  styles.assistanceMode,
                  trackingAssistance.used ? styles.assistanceModeUsed : styles.assistanceModeFallback,
                ]}
              >
                {assistanceMode}
              </Text>
            </View>
            <Text style={styles.assistanceDetail}>
              Body points guided: {trackingAssistance.fusedLandmarkCount ?? 0}
            </Text>
            <Text style={styles.assistanceDetail}>
              Reference anchors: {trackingAssistance.directlyAnchoredLandmarkCount ?? 0},{' '}
              blended: {trackingAssistance.blendedLandmarkCount ?? 0},{' '}
              automatic fallbacks: {trackingAssistance.fallbackLandmarkCount ?? 0}
            </Text>
            <Text style={styles.assistanceDetail}>
              Barbell points: {trackingAssistance.manualBarbellPointCount ?? 0} pin-assisted,{' '}
              {trackingAssistance.automaticBarbellPointCount ?? 0} automatic
            </Text>
            <Text style={styles.assistanceDetail}>
              Rejected body points: {trackingAssistance.rejectedTrackCount ?? 0}
            </Text>
            {trackingAssistance.selectedSide ? (
              <Text style={styles.assistanceDetail}>
                Body side: {trackingAssistance.selectedSide}
              </Text>
            ) : null}
            {coverageEntries.length > 0 ? (
              <Text style={styles.assistanceDetail}>
                Coverage: {coverageEntries.map(([name, coverage]) => (
                  `${name} ${Math.round(coverage * 100)}%`
                )).join(', ')}
              </Text>
            ) : null}
            {trackingAssistance.fallbackReason ? (
              <Text style={styles.assistanceFallbackReason}>
                Fallback reason: {trackingAssistance.fallbackReason.split('_').join(' ')}
              </Text>
            ) : null}
          </View>
        ) : null}
      </View>
    </ReviewBottomSheet>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: 16,
  },
  helperText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  options: {
    gap: 10,
  },
  assistancePanel: {
    gap: 6,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0C1016',
    padding: 14,
  },
  assistanceHeadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  assistanceHeading: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    fontWeight: '700',
  },
  assistanceMode: {
    fontSize: 12,
    fontWeight: '700',
  },
  assistanceModeUsed: {
    color: '#8CC0FF',
  },
  assistanceModeFallback: {
    color: '#FFD080',
  },
  assistanceDetail: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textTransform: 'capitalize',
  },
  assistanceFallbackReason: {
    color: '#FFD080',
    fontSize: 13,
    lineHeight: 18,
  },
  option: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0C1016',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  optionPressed: {
    backgroundColor: '#151C27',
  },
  optionDisabled: {
    opacity: 0.58,
  },
  optionCopy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  optionLabel: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '700',
  },
  optionDescription: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  disabledText: {
    color: '#7D8797',
  },
});
