import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import tokens from '../theme/tokens';
import ReviewBottomSheet from './ReviewBottomSheet';

type TrackingDisplaySheetProps = {
  visible: boolean;
  poseAvailable: boolean;
  poseEnabled: boolean;
  barbellAvailable: boolean;
  barbellEnabled: boolean;
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
  onPoseEnabledChange,
  onBarbellEnabledChange,
  onClose,
}: TrackingDisplaySheetProps) {
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
