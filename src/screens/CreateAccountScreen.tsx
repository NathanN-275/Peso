import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
  ScrollView,
  View,
} from 'react-native';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

const titleImage = require('../../CreateAccount.png');

type CreateAccountScreenProps = {
  onBack: () => void;
};

export default function CreateAccountScreen({ onBack }: CreateAccountScreenProps) {
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [email, setEmail] = useState('');
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
          <View
            className="rounded-[2px] bg-black"
            style={{ paddingHorizontal: 44, paddingVertical: 36, marginTop: 8 }}
          >
            <Image
              source={titleImage}
              resizeMode="contain"
              style={{ width: '100%', height: 64, marginBottom: 22 }}
              accessible
              accessibilityLabel="Create Account"
            />

            <View className="items-center" style={{ marginBottom: 28 }}>
              <View
                className="items-center justify-center rounded-full"
                style={{ width: 108, height: 108, backgroundColor: '#E8DDFD' }}
              >
                <View
                  className="items-center"
                  style={{ width: 56, height: 62, justifyContent: 'center' }}
                >
                  <View
                    className="rounded-full"
                    style={{
                      width: 24,
                      height: 24,
                      borderWidth: 3,
                      borderColor: '#5C4AA3',
                    }}
                  />
                  <View
                    style={{
                      width: 46,
                      height: 24,
                      marginTop: 8,
                      borderWidth: 3,
                      borderColor: '#5C4AA3',
                      borderTopLeftRadius: 24,
                      borderTopRightRadius: 24,
                      borderBottomWidth: 0,
                    }}
                  />
                </View>
              </View>
            </View>

            <View style={{ gap: 14 }}>
              <Input label="Name" placeholder="Value" value={name} onChangeText={setName} />
              <Input
                label="Username"
                placeholder="Value"
                value={username}
                onChangeText={setUsername}
              />
              <Input
                label="Phone Number"
                placeholder="Value"
                value={phoneNumber}
                onChangeText={setPhoneNumber}
              />
              <Input label="Email" placeholder="Value" value={email} onChangeText={setEmail} />
              <Input
                label="Password"
                placeholder="Value"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
              />
            </View>

            <View style={{ marginTop: 24, gap: 24 }}>
              <Button label="Create Account" style={{ width: '100%' }} />
              <Button label="Back" onPress={onBack} style={{ width: '100%' }} />
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
