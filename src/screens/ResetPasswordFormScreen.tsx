import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useAuth } from '../../context/AuthContext';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

const titleImage = require('../../ResetPassword.png');

type ResetPasswordFormScreenProps = {
  onBack: () => void;
  onReset: () => void;
};

export default function ResetPasswordFormScreen({
  onBack,
  onReset,
}: ResetPasswordFormScreenProps) {
  const { passwordRecoveryMode, updatePassword } = useAuth();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const handleReset = async () => {
    const trimmedPassword = password.trim();
    const trimmedConfirmPassword = confirmPassword.trim();

    if (!passwordRecoveryMode) {
      setInfoMessage('Open the reset link from your email to choose a new password.');
      setErrorMessage(null);
      return;
    }

    if (!trimmedPassword || !trimmedConfirmPassword) {
      setInfoMessage(null);
      setErrorMessage('Enter and confirm your new password.');
      return;
    }

    if (trimmedPassword.length < 6) {
      setInfoMessage(null);
      setErrorMessage('Use a password with at least 6 characters.');
      return;
    }

    if (trimmedPassword !== trimmedConfirmPassword) {
      setInfoMessage(null);
      setErrorMessage('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);
    setInfoMessage(null);

    try {
      await updatePassword(trimmedPassword);
      setInfoMessage('Password updated. Log in with your new password.');
      onReset();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to reset password.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-black">
      <StatusBar style="light" />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        className="flex-1"
        style={{ backgroundColor: '#000' }}
      >
        <ScrollView
          className="flex-1"
          style={{ backgroundColor: '#000' }}
          contentContainerStyle={{
            paddingHorizontal: tokens.spacing.screenX,
            paddingBottom: 32,
          }}
          keyboardShouldPersistTaps="handled"
        >
          <View
            className="bg-black"
            style={{
              minHeight: 705,
              marginTop: 0,
              paddingTop: 96,
              paddingHorizontal: 46,
              paddingBottom: 40,
            }}
          >
            <Image
              source={titleImage}
              resizeMode="cover"
              style={styles.titleImage}
              accessible
              accessibilityLabel="Reset Password"
            />

            <View style={{ gap: 10 }}>
              <Input
                label="Enter Password"
                placeholder="Value"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                textContentType="newPassword"
                editable={!submitting && passwordRecoveryMode}
              />
              <Input
                label="Confirm Password"
                placeholder="Value"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry
                textContentType="newPassword"
                editable={!submitting && passwordRecoveryMode}
              />
            </View>

            {!passwordRecoveryMode ? (
              <Text
                className="text-text-primary"
                style={{ marginTop: 16, fontSize: 14, lineHeight: 20 }}
              >
                Open the recovery link from your email to activate this form.
              </Text>
            ) : null}

            {errorMessage ? (
              <Text
                className="text-text-primary"
                style={{ marginTop: 16, fontSize: 14, lineHeight: 20, color: '#FF8A8A' }}
              >
                {errorMessage}
              </Text>
            ) : null}

            {infoMessage ? (
              <Text
                className="text-text-primary"
                style={{ marginTop: 16, fontSize: 14, lineHeight: 20 }}
              >
                {infoMessage}
              </Text>
            ) : null}

            <View style={{ marginTop: 10, gap: 10 }}>
              <Button
                label={submitting ? 'Resetting...' : 'Reset'}
                onPress={handleReset}
                disabled={submitting}
                style={{ width: '100%' }}
              />
              <Button
                label="Back"
                onPress={onBack}
                disabled={submitting}
                style={{ width: '100%' }}
              />
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  titleImage: {
    alignSelf: 'center',
    width: '180%',
    height: 150,
    marginBottom: 24,
  },
});
