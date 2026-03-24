import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

const titleImage = require('../../CreateAccount.png');

type CreateAccountScreenProps = {
  onBack: () => void;
  onSuccess: () => void;
};

export default function CreateAccountScreen({ onBack, onSuccess }: CreateAccountScreenProps) {
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
            style={{ paddingHorizontal: 44, paddingTop: 16, paddingBottom: 36, marginTop: -50}}
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
                      marginTop: 6,
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
              <Button label="Create Account" onPress={onSuccess} style={{ width: '100%' }} />
              <Button label="Back" onPress={onBack} style={{ width: '100%' }} />
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
  },
});
