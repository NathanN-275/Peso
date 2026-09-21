import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, TextInputProps, View } from 'react-native';
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
  showPasswordToggle?: boolean;
  testID?: string;
  accessibilityLabel?: string;
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
  showPasswordToggle = false,
  testID,
  accessibilityLabel,
}: InputProps) {
  const [passwordVisible, setPasswordVisible] = useState(false);
  const hasPasswordToggle = secureTextEntry === true && showPasswordToggle;

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
      <View style={styles.inputWrap}>
        <TextInput
          testID={testID}
          accessibilityLabel={accessibilityLabel ?? label}
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={tokens.colors.textMuted}
          secureTextEntry={secureTextEntry && !passwordVisible}
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
          style={[styles.textInput, hasPasswordToggle && styles.textInputWithIcon]}
        />
        {hasPasswordToggle ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={passwordVisible ? 'Hide password' : 'Show password'}
            onPress={() => setPasswordVisible((visible) => !visible)}
            disabled={!editable}
            hitSlop={8}
            style={styles.passwordToggle}
          >
            <Ionicons
              name={passwordVisible ? 'eye-off-outline' : 'eye-outline'}
              size={22}
              color={editable ? tokens.colors.textMuted : '#667085'}
            />
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  labelText: {
    fontSize: 16,
    lineHeight: 20,
    marginBottom: 10,
  },
  inputWrap: {
    position: 'relative',
  },
  textInput: {
    height: tokens.sizes.inputHeight - 4,
    marginTop: 0,
  },
  textInputWithIcon: {
    paddingRight: 52,
  },
  passwordToggle: {
    position: 'absolute',
    top: 0,
    right: 8,
    bottom: 0,
    width: 38,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
