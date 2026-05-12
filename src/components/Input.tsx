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
  onFocus?: TextInputProps['onFocus'];
  onBlur?: TextInputProps['onBlur'];
  autoFocus?: boolean;
  returnKeyType?: TextInputProps['returnKeyType'];
  onSubmitEditing?: TextInputProps['onSubmitEditing'];
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
  onFocus,
  onBlur,
  autoFocus = false,
  returnKeyType,
  onSubmitEditing,
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
        onFocus={onFocus}
        onBlur={onBlur}
        autoFocus={autoFocus}
        returnKeyType={returnKeyType}
        onSubmitEditing={onSubmitEditing}
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
    marginBottom: 10,
  },
  textInput: {
    height: tokens.sizes.inputHeight - 4,
    marginTop: 0,
  },
});
