import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
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
  const { signInWithEmail } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSignIn = async () => {
    if (!email.trim() || !password) {
      setError('Enter both email and password.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await signInWithEmail(email.trim(), password);
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : 'Unable to sign in.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-bg">
      <StatusBar style="light" />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        className="flex-1"
      >
        <ScrollView
          className="flex-1"
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
              marginTop: 8,
              paddingTop: 20,
              paddingHorizontal: 46,
              paddingBottom: 40,
            }}
          >
            <Image
              source={titleImage}
              resizeMode="contain"
              style={styles.titleImage}
              accessible
              accessibilityLabel="Login"
            />

            {error ? (
              <View
                style={{
                  marginBottom: 20,
                  borderWidth: 1,
                  borderColor: '#5A1E24',
                  backgroundColor: '#2C0E12',
                  borderRadius: 12,
                  paddingHorizontal: 14,
                  paddingVertical: 12,
                }}
              >
                <Text className="text-text-primary" style={{ color: '#FFC8CF' }}>
                  {error}
                </Text>
              </View>
            ) : null}

            <View style={{ gap: 28 }}>
              <Input
                label="Email"
                placeholder="name@example.com"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                textContentType="emailAddress"
              />
              <Input
                label="Password"
                placeholder="Enter your password"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                textContentType="password"
              />
            </View>

            <Pressable
              onPress={onForgotPassword}
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

            <View style={{ marginTop: 20, gap: 28 }}>
              <Button
                label={loading ? 'Signing In' : 'Sign In'}
                onPress={handleSignIn}
                disabled={loading}
                style={{ width: '100%', height: 32 }}
              />
              <Button
                label="Back"
                onPress={onBack}
                disabled={loading}
                style={{ width: '100%', height: 32 }}
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
    marginBottom: -80,
    alignSelf: 'center',
  },
});
