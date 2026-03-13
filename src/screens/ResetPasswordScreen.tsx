import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
  ScrollView,
  Text,
  View,
} from 'react-native';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

const titleImage = require('../../ResetPassword.png');

type ResetPasswordScreenProps = {
  onBack: () => void;
  onSubmit: () => void;
};

export default function ResetPasswordScreen({ onBack, onSubmit }: ResetPasswordScreenProps) {
  const [identifier, setIdentifier] = useState('');

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
            Forgot Password
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
              accessibilityLabel="Reset Password"
            />

            <Input
              label="Email or Phone Number"
              placeholder="Value"
              value={identifier}
              onChangeText={setIdentifier}
            />

            <View style={{ marginTop: 34, gap: 26 }}>
              <Button label="Submit" onPress={onSubmit} style={{ width: '100%', height: 32 }} />
              <Button label="Back" onPress={onBack} style={{ width: '100%', height: 32 }} />
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
