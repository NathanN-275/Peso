import {
  GestureResponderEvent,
  StyleProp,
  StyleSheet,
  Text,
  TouchableOpacity,
  ViewStyle,
} from 'react-native';
import tokens from '../theme/tokens';
import { getButtonVariantColors } from '../../lib/buttonStylePolicy';

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
  const variantColors = getButtonVariantColors(variant, tokens.colors);
  const buttonStyles = [
    styles.button,
    {
      backgroundColor: variantColors.backgroundColor,
      borderColor: variantColors.borderColor,
      borderWidth: variantColors.borderWidth,
    },
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
      <Text style={[styles.label, { color: variantColors.textColor }]}>
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
  disabledButton: {
    opacity: 0.6,
  },
  label: {
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
    letterSpacing: tokens.typography.buttonLetterSpacing,
    textAlign: 'center',
  },
});
