import {
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  Text,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
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
              width: '100%',
            }}
          >
            <View className="items-center">
              <Pressable
                onPress={onLogin}
                accessibilityRole="button"
                style={({ pressed }) => ({
                  width: tokens.sizes.buttonWidth,
                  height: tokens.sizes.buttonHeight,
                  borderRadius: tokens.radii.button,
                  backgroundColor: pressed ? tokens.colors.brandPress : tokens.colors.brand,
                  alignItems: 'center',
                  justifyContent: 'center',
                })}
              >
                <Text
                  style={{
                    color: tokens.colors.textPrimary,
                    fontSize: tokens.typography.buttonSize,
                    lineHeight: tokens.typography.buttonLineHeight,
                    fontWeight: '600',
                    letterSpacing: tokens.typography.buttonLetterSpacing,
                  }}
                >
                  Log in
                </Text>
              </Pressable>
            </View>
            <View
              className="items-center"
              style={{ marginTop: tokens.spacing.buttonGap }}
            >
              <Pressable
                onPress={onCreateAccount}
                accessibilityRole="button"
                style={({ pressed }) => ({
                  width: tokens.sizes.buttonWidth,
                  height: tokens.sizes.buttonHeight,
                  borderRadius: tokens.radii.button,
                  backgroundColor: pressed ? tokens.colors.brandPress : tokens.colors.brand,
                  alignItems: 'center',
                  justifyContent: 'center',
                })}
              >
                <Text
                  style={{
                    color: tokens.colors.textPrimary,
                    fontSize: tokens.typography.buttonSize,
                    lineHeight: tokens.typography.buttonLineHeight,
                    fontWeight: '600',
                    letterSpacing: tokens.typography.buttonLetterSpacing,
                  }}
                >
                  Create an Account
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
