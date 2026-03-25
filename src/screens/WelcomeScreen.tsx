import {
  Image,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';
import Button from '../components/Button';
import tokens from '../theme/tokens';

const logo = require('../../AppLogo.png');

type WelcomeScreenProps = {
  onLogin: () => void;
  onCreateAccount: () => void;
};

export default function WelcomeScreen({ onLogin, onCreateAccount }: WelcomeScreenProps) {
  return (
    <SafeAreaView className="flex-1" style={{ backgroundColor: '#000' }}>
      <StatusBar style="light" />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        className="flex-1"
        style={{ backgroundColor: '#000' }}
      >
        <View
          className="flex-1 items-center"
          style={{
            paddingHorizontal: tokens.spacing.screenX,
            backgroundColor: '#000',
          }}
        >
          <View
            className="items-center"
            style={{ marginTop: tokens.spacing.logoTop }}
          >

          <View
            className="items-center"
            style={{
              marginTop: tokens.spacing.logoTop - 160,
              width: '100%',
            }}
          >
           <Image
              source={logo}
              style={styles.logoImage}
              resizeMode="contain"
              accessible
              accessibilityLabel="Peso"
            />  
          </View>
            <View className="items-center">
              <Button label="Log in" onPress={onLogin} />
            </View>
            <View
              className="items-center"
              style={{ marginTop: tokens.spacing.buttonGap }}
            >
              <Button label="Create an Account" onPress={onCreateAccount} />
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  logoImage: {
    width: 500,
    height: 300,
  },
});
