import { Text, TextInput, TextInputProps, View } from 'react-native';
import tokens from '../theme/tokens';

type InputProps = {
  label?: string;
  placeholder?: string;
  value?: string;
  onChangeText?: (text: string) => void;
  secureTextEntry?: boolean;
  keyboardType?: TextInputProps['keyboardType'];
  autoCapitalize?: TextInputProps['autoCapitalize'];
  autoCorrect?: boolean;
  textContentType?: TextInputProps['textContentType'];
  editable?: boolean;
};

export default function Input({
  label,
  placeholder,
  value,
  onChangeText,
  secureTextEntry,
  keyboardType,
  autoCapitalize = 'none',
  autoCorrect = false,
  textContentType,
  editable = true,
}: InputProps) {
  return (
    <View>
      {label ? (
        <Text className="mb-2 text-label text-text-muted" numberOfLines={1}>
          {label}
        </Text>
      ) : null}
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={tokens.colors.textMuted}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={autoCorrect}
        textContentType={textContentType}
        editable={editable}
        className="rounded-input border border-input-border bg-input-bg px-4 text-text-primary"
        style={{ height: tokens.sizes.inputHeight }}
      />
    </View>
  );
}
