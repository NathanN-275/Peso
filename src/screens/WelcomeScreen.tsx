import { Image, KeyboardAvoidingView, Platform, SafeAreaView, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import Button from '../components/Button';
import tokens from '../theme/tokens';

const logo = require('../../AppLogo.png');

type WelcomeScreenProps = {
  onLogin?: () => void;
  onCreateAccount?: () => void;
};

export default function WelcomeScreen({ onLogin, onCreateAccount }: WelcomeScreenProps) {
  return (
    <SafeAreaView className="flex-1 bg-bg">
      <StatusBar style="light" />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        className="flex-1"
      >
        <View
          className="flex-1 items-center"
          style={{ paddingHorizontal: tokens.spacing.screenX }}
        >
          <View
            className="items-center"
            style={{ marginTop: tokens.spacing.logoTop }}
          >
            <Image
              source={logo}
              style={{
                width: tokens.sizes.logoWidth,
                height: tokens.sizes.logoHeight,
              }}
              resizeMode="contain"
              accessible
              accessibilityLabel="Peso"
            />
          </View>

          <View
            className="items-center"
            style={{
              marginTop: tokens.spacing.logoBottom,
              gap: tokens.spacing.buttonGap,
            }}
          >
            <Button label="Log in" onPress={onLogin} />
            <Button label="Create an Account" onPress={onCreateAccount} />
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
