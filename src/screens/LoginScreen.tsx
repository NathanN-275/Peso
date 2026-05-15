import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useAuth } from '../../context/AuthContext';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

const titleImage = require('../../Login.png');

type LoginScreenProps = {
  onBack: () => void;
  onForgotPassword: () => void;
};

export default function LoginScreen({ onBack, onForgotPassword }: LoginScreenProps) {
  // Login uses the shared auth context for email/password sign-in.
  const { signInWithEmail } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSignIn = async () => {
    // Normalize the email so duplicate casing does not matter.
    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password.trim()) {
      setErrorMessage('Enter your email and password.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);

    try {
      // Any auth error is surfaced directly in the form.
      await signInWithEmail(normalizedEmail, password);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to log in.');
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
              marginTop: -50,
              paddingTop: 0,
              paddingHorizontal: 46,
              paddingBottom: 10,
            }}
          >
            {/* Decorative title art for the login form. */}
            <Image
              source={titleImage}
              resizeMode="contain"
              style={styles.titleImage}
              accessible
              accessibilityLabel="Login"
            />

            <View style={{ gap: 28 }}>
              {/* These are the only fields needed for password auth. */}
              <Input
                label="Email"
                placeholder="name@example.com"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                textContentType="emailAddress"
                editable={!submitting}
              />
              <Input
                label="Password"
                placeholder="Enter your password"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                textContentType="password"
                editable={!submitting}
              />
            </View>

            {errorMessage ? (
              <Text
                className="text-text-primary"
                style={{ marginTop: 16, fontSize: 14, lineHeight: 20, color: '#FF8A8A' }}
              >
                {errorMessage}
              </Text>
            ) : null}

            <Pressable
              onPress={submitting ? undefined : onForgotPassword}
              accessibilityRole="link"
              style={{ marginTop: 12, alignSelf: 'flex-start' }}
            >
              <Text
                className="text-text-muted"
                style={{ fontSize: 14, textDecorationLine: 'underline' }}
              >
                Forgot password?
              </Text>
            </Pressable>

            <View style={{ marginTop: 20, gap: 12 }}>
              <Button
                label={submitting ? 'Logging In...' : 'Log In'}
                onPress={handleSignIn}
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
    width: '1000%',
    height: 500, 
    marginBottom: -180,
    alignSelf: 'center',
  },
});
