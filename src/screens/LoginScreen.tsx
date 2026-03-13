import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  Text,
  View,
} from 'react-native';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

const titleImage = require('../../Login.png');

type LoginScreenProps = {
  onBack: () => void;
  onForgotPassword: () => void;
};

export default function LoginScreen({ onBack, onForgotPassword }: LoginScreenProps) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

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
          <Text
            className="text-text-muted"
            style={{ marginTop: 8, marginBottom: 12, fontSize: 16, marginLeft: 2 }}
          >
            Login
          </Text>

          <View
            className="bg-black"
            style={{
              minHeight: 705,
              paddingTop: 96,
              paddingHorizontal: 46,
              paddingBottom: 40,
            }}
          >
            <Image
              source={titleImage}
              resizeMode="contain"
              style={{ width: '100%', height: 62, marginBottom: 42 }}
              accessible
              accessibilityLabel="Login"
            />

            <View style={{ gap: 18 }}>
              <Input
                label="Mobile number or email"
                placeholder="Value"
                value={identifier}
                onChangeText={setIdentifier}
              />
              <Input
                label="Password"
                placeholder="Value"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
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

            <View style={{ marginTop: 20, gap: 26 }}>
              <Button label="Sign In" style={{ width: '100%', height: 32 }} />
              <Button label="Back" onPress={onBack} style={{ width: '100%', height: 32 }} />
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
