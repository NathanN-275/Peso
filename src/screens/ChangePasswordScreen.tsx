import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
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
import { supabase } from '../../lib/supabase';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

const titleImage = require('../../ResetPassword.png');

type ResetPasswordFormScreenProps = {
  onBack: () => void;
  onReset: () => void;
  initialErrorMessage?: string | null;
};

export default function ResetPasswordFormScreen({
  initialErrorMessage = null,
  onBack,
  onReset,
}: ResetPasswordFormScreenProps) {
  // The form stays locked until a real recovery session is present.
  const { passwordRecoveryMode, updatePassword } = useAuth();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(initialErrorMessage);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  useEffect(() => {
    // Keep the latest error message in sync with the parent screen.
    setErrorMessage(initialErrorMessage);
  }, [initialErrorMessage]);

  const handleReset = async () => {
    // Validate locally before touching Supabase.
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
      // The reset link must hydrate a session before the password can change.
      if (!supabase) {
        throw new Error('Supabase is not configured.');
      }

      const {
        data: { session },
      } = await supabase.auth.getSession();
      console.log('[ResetPassword] getSession result before submit', { hasSession: !!session });

      if (!session) {
        setErrorMessage('Reset link session expired or was not loaded. Please request a new reset link.');
        return;
      }

      await updatePassword(trimmedPassword);
      setInfoMessage('Password updated. Log in with your new password.');
      setTimeout(onReset, 900);
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
              {/* Both fields are required so the new password can be confirmed. */}
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
              // Without a recovery session, this form is intentionally read-only.
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
