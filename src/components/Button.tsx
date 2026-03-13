import { Pressable, Text, ViewStyle } from 'react-native';
import tokens from '../theme/tokens';

type ButtonProps = {
  label: string;
  onPress?: () => void;
  className?: string;
  style?: ViewStyle;
  variant?: 'primary' | 'secondary';
};

export default function Button({
  label,
  onPress,
  className,
  style,
  variant = 'primary',
}: ButtonProps) {
  const baseClass = 'items-center justify-center rounded-button';
  const variantClass =
    variant === 'primary'
      ? 'bg-brand pressed:bg-brand-press'
      : 'bg-brand pressed:bg-brand-press';

  return (
    <Pressable
      onPress={onPress}
      className={`${baseClass} ${variantClass} ${className ?? ''}`}
      style={[
        { width: tokens.sizes.buttonWidth, height: tokens.sizes.buttonHeight },
        style,
      ]}
    >
      <Text className="text-button text-text-primary font-semibold tracking-button">
        {label}
      </Text>
    </Pressable>
  );
}
