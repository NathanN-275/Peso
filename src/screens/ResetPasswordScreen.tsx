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

type ResetPasswordScreenProps = {
  onBack: () => void;
  onSubmit: () => void;
};

export default function ResetPasswordScreen({ onBack, onSubmit }: ResetPasswordScreenProps) {
  const { resetPasswordForEmail } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const handleSubmit = async () => {
    const normalizedIdentifier = identifier.trim().toLowerCase();

    if (!normalizedIdentifier) {
      setInfoMessage(null);
      setErrorMessage('Enter the email address for your account.');
      return;
    }

    if (!normalizedIdentifier.includes('@')) {
      setInfoMessage(null);
      setErrorMessage('Password reset is currently set up for email addresses only.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);
    setInfoMessage(null);

    try {
      await resetPasswordForEmail(normalizedIdentifier);
      setInfoMessage('Reset email sent. Open the link in your email to choose a new password.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to send reset email.');
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

            <Input
              label="Email or Phone Number"
              placeholder="Value"
              value={identifier}
              onChangeText={setIdentifier}
              keyboardType="email-address"
              autoCapitalize="none"
              editable={!submitting}
            />

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

            <View style={{ marginTop: 34, gap: 26 }}>
              <Button
                label={submitting ? 'Sending...' : 'Submit'}
                onPress={handleSubmit}
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
