import { StyleSheet, Text, TextInput, TextInputProps, View } from 'react-native';
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
        <Text
          className="text-text-muted"
          style={styles.labelText}
          numberOfLines={1}
        >
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
        style={styles.textInput}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  labelText: {
    fontSize: 16,
    lineHeight: 20,
    marginBottom: 6,
  },
  textInput: {
    height: tokens.sizes.inputHeight - 4,
    marginTop: 0,
  },
});
