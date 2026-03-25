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

const titleImage = require('../../CreateAccount.png');

type CreateAccountScreenProps = {
  onBack: () => void;
};

export default function CreateAccountScreen({ onBack }: CreateAccountScreenProps) {
  const { signUpWithEmail } = useAuth();
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const handleCreateAccount = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    const trimmedPassword = password.trim();
    const trimmedUsername = username.trim();

    if (!name.trim() || !trimmedUsername || !normalizedEmail || !trimmedPassword) {
      setInfoMessage(null);
      setErrorMessage('Enter your name, username, email, and password.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);
    setInfoMessage(null);

    try {
      const result = await signUpWithEmail(normalizedEmail, trimmedPassword, {
        name,
        username: trimmedUsername,
        phone: phoneNumber,
      });

      if (result.session) {
        return;
      }

      if (result.requiresEmailConfirmation) {
        setInfoMessage(
          'Account created, but you are not signed in yet. Check your email to verify your account, then log in.'
        );
        return;
      }

      if (result.user && !result.session) {
        setInfoMessage(
          'Signup succeeded, but login is not active yet. Verify your email or finish account activation before logging in.'
        );
        return;
      }

      setErrorMessage('Signup did not complete. Please try again.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to create account.');
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
            className="rounded-[2px] bg-black"
            style={{ paddingHorizontal: 44, paddingTop: 0, paddingBottom: 0, marginTop: 0 }}
          >
            <Image
              source={titleImage}
              resizeMode="contain"
              style={styles.titleImage}
              accessible
              accessibilityLabel="Create Account"
            />

            <View className="items-center" style={{ marginBottom: 28 }}>
              <View
                className="items-center justify-center rounded-full"
                style={{ width: 84, height: 84, backgroundColor: '#E8DDFD' }}
              >
                <View
                  className="items-center"
                  style={{ width: 44, height: 48, justifyContent: 'center' }}
                >
                  <View
                    className="rounded-full"
                    style={{
                      width: 18,
                      height: 18,
                      borderWidth: 2.5,
                      borderColor: '#5C4AA3',
                    }}
                  />
                  <View
                    style={{
                      width: 34,
                      height: 18,
                      marginTop: 0,
                      borderWidth: 2.5,
                      borderColor: '#5C4AA3',
                      borderTopLeftRadius: 18,
                      borderTopRightRadius: 18,
                      borderBottomWidth: 0,
                    }}
                  />
                </View>
              </View>
            </View>

            <View style={{ gap: 14 }}>
              <Input
                label="Name"
                placeholder="Value"
                value={name}
                onChangeText={setName}
                editable={!submitting}
              />
              <Input
                label="Username"
                placeholder="Value"
                value={username}
                onChangeText={setUsername}
                editable={!submitting}
              />
              <Input
                label="Phone Number"
                placeholder="Value"
                value={phoneNumber}
                onChangeText={setPhoneNumber}
                keyboardType="phone-pad"
                editable={!submitting}
              />
              <Input
                label="Email"
                placeholder="Value"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                textContentType="emailAddress"
                editable={!submitting}
              />
              <Input
                label="Password"
                placeholder="Value"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                textContentType="newPassword"
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

            {infoMessage ? (
              <Text
                className="text-text-primary"
                style={{ marginTop: 16, fontSize: 14, lineHeight: 20 }}
              >
                {infoMessage}
              </Text>
            ) : null}

            <View style={{ marginTop: 24, gap: 12 }}>
              <Button
                label={submitting ? 'Creating...' : 'Create Account'}
                onPress={handleCreateAccount}
                disabled={submitting}
                style={{ width: '100%' }}
              />
              <Button label="Back" onPress={onBack} disabled={submitting} style={{ width: '100%' }} />
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
    width: '200%',
    height: 350,
    marginBottom: -125,
    marginTop: -100,
  },
});
