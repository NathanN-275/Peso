import {
  GestureResponderEvent,
  StyleProp,
  StyleSheet,
  Text,
  TouchableOpacity,
  ViewStyle,
} from 'react-native';
import tokens from '../theme/tokens';

type ButtonProps = {
  label: string;
  onPress?: (event?: GestureResponderEvent) => void;
  style?: StyleProp<ViewStyle>;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
};

export default function Button({
  label,
  onPress,
  style,
  variant = 'primary',
  disabled = false,
}: ButtonProps) {
  const buttonStyles = [
    styles.button,
    variant === 'primary' ? styles.primaryButton : styles.primaryButton,
    disabled ? styles.disabledButton : null,
    style,
  ];

  return (
    <TouchableOpacity
      onPress={(event) => {
        event.stopPropagation?.();
        onPress?.(event);
      }}
      disabled={disabled}
      accessibilityRole="button"
      activeOpacity={0.85}
      style={buttonStyles}
    >
      <Text style={styles.label}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    width: tokens.sizes.buttonWidth,
    minHeight: 20,
    paddingHorizontal: 24,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
    borderRadius: tokens.radii.button,
    overflow: 'hidden',
  },
  primaryButton: {
    backgroundColor: tokens.colors.brand,
  },
  disabledButton: {
    opacity: 0.6,
  },
  label: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
    letterSpacing: tokens.typography.buttonLetterSpacing,
    textAlign: 'center',
  },
});
