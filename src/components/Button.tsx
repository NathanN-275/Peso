import { GestureResponderEvent, Pressable, Text, ViewStyle } from 'react-native';
import tokens from '../theme/tokens';

type ButtonProps = {
  label: string;
  onPress?: (event?: GestureResponderEvent) => void;
  className?: string;
  style?: ViewStyle;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
};

export default function Button({
  label,
  onPress,
  className,
  style,
  variant = 'primary',
  disabled = false,
}: ButtonProps) {
  const baseClass = 'items-center justify-center rounded-button';
  const variantClass =
    variant === 'primary'
      ? 'bg-brand pressed:bg-brand-press'
      : 'bg-brand pressed:bg-brand-press';

  return (
    <Pressable
      onPress={(event) => {
        event.stopPropagation();
        onPress?.(event);
      }}
      disabled={disabled}
      accessibilityRole="button"
      className={`${baseClass} ${variantClass} ${className ?? ''}`}
      style={[
        {
          width: tokens.sizes.buttonWidth,
          height: tokens.sizes.buttonHeight,
          opacity: disabled ? 0.6 : 1,
        },
        style,
      ]}
    >
      <Text className="text-button text-text-primary font-semibold tracking-button">
        {label}
      </Text>
    </Pressable>
  );
}
