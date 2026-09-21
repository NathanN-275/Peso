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
import AuthChallenge from '../components/auth/AuthChallenge';
import tokens from '../theme/tokens';

const titleImage = require('../../CreateAccount.png');

type CreateAccountScreenProps = {
  onBack: () => void;
};

type CreateAccountErrors = {
  name?: string;
  username?: string;
  phone?: string;
  email?: string;
  password?: string;
  residency?: string;
  terms?: string;
  general?: string;
};

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function isValidUsPhoneNumber(phone: string) {
  const strippedPhone = phone.replace(/[\s().-]/g, '');
  const digitsOnlyPhone = strippedPhone.startsWith('+') ? strippedPhone.slice(1) : strippedPhone;

  return /^\d{10}$/.test(digitsOnlyPhone) || /^1\d{10}$/.test(digitsOnlyPhone);
}

function AgreementRow({
  checked,
  label,
  onPress,
  testID,
}: {
  checked: boolean;
  label: string;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={label}
      testID={testID}
      onPress={onPress}
      style={styles.agreementRow}
    >
      <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
        {checked ? <Text style={styles.checkboxMark}>✓</Text> : null}
      </View>
      <Text style={styles.agreementLabel}>{label}</Text>
    </Pressable>
  );
}

export default function CreateAccountScreen({ onBack }: CreateAccountScreenProps) {
  // Collect profile fields before calling Supabase signup.
  const { signUpWithEmail } = useAuth();
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [usResident, setUsResident] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<CreateAccountErrors>({});
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaError, setCaptchaError] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);

  const clearFieldError = (field: keyof CreateAccountErrors) => {
    setErrors((currentErrors) => {
      if (!currentErrors[field]) {
        return currentErrors;
      }

      const nextErrors = { ...currentErrors };
      delete nextErrors[field];
      return nextErrors;
    });
  };

  const handleCreateAccount = async () => {
    // Trim the user input before sending it to auth.
    const trimmedName = name.trim();
    const trimmedPhoneNumber = phoneNumber.trim();
    const normalizedEmail = email.trim().toLowerCase();
    const trimmedPassword = password.trim();
    const trimmedUsername = username.trim();

    setErrors({});
    setInfoMessage(null);

    const nextErrors: CreateAccountErrors = {};

    if (!trimmedName) {
      nextErrors.name = 'Name is required.';
    }

    if (!trimmedUsername) {
      nextErrors.username = 'Username is required.';
    }

    if (!trimmedPhoneNumber) {
      nextErrors.phone = 'Phone number is required.';
    } else if (!isValidUsPhoneNumber(trimmedPhoneNumber)) {
      nextErrors.phone = 'Please enter a valid phone number.';
    }

    if (!normalizedEmail) {
      nextErrors.email = 'Email is required.';
    } else if (!isValidEmail(normalizedEmail)) {
      nextErrors.email = 'Please enter a valid email address.';
    }

    if (!trimmedPassword) {
      nextErrors.password = 'Password is required.';
    } else if (trimmedPassword.length < 8) {
      nextErrors.password = 'Password should be at least 8 characters.';
    }

    if (!usResident) {
      nextErrors.residency = 'Confirm United States residency to join the beta.';
    }

    if (!termsAccepted) {
      nextErrors.terms = 'Accept the beta Terms and Privacy Policy to continue.';
    }

    if (!captchaToken) {
      nextErrors.general = 'Complete the security check and try again.';
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    if (!captchaToken) {
      return;
    }

    setSubmitting(true);

    try {
      // Signup may return a session immediately or require email confirmation.
      const result = await signUpWithEmail(
        normalizedEmail,
        trimmedPassword,
        {
          name: trimmedName,
          username: trimmedUsername,
          phone: trimmedPhoneNumber,
        },
        captchaToken
      );

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

      setErrors({ general: 'Signup did not complete. Please try again.' });
    } catch (error) {
      setErrors({
        general: error instanceof Error ? error.message : 'Unable to create account.',
      });
    } finally {
      setSubmitting(false);
      setCaptchaToken(null);
      setCaptchaReset((value) => value + 1);
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
            {/* Decorative title art for the signup form. */}
            <Image
              source={titleImage}
              resizeMode="contain"
              style={styles.titleImage}
              accessible
              accessibilityLabel="Create Account"
            />

            <View className="items-center" style={{ marginBottom: 28 }}>
              {/* Static profile icon used as a visual anchor. */}
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
              <View>
                <Input
                  label="Name"
                  testID="auth-name"
                  placeholder="Value"
                  value={name}
                  onChangeText={(value) => {
                    setName(value);
                    clearFieldError('name');
                  }}
                  editable={!submitting}
                />
                {errors.name ? (
                  <Text style={styles.fieldErrorText}>{errors.name}</Text>
                ) : null}
              </View>
              <View>
                <Input
                  label="Username"
                  testID="auth-username"
                  placeholder="Value"
                  value={username}
                  onChangeText={(value) => {
                    setUsername(value);
                    clearFieldError('username');
                  }}
                  editable={!submitting}
                />
                {errors.username ? (
                  <Text style={styles.fieldErrorText}>{errors.username}</Text>
                ) : null}
              </View>
              <View>
                <Input
                  label="Phone Number"
                  testID="auth-phone"
                  placeholder="Value"
                  value={phoneNumber}
                  onChangeText={(value) => {
                    setPhoneNumber(value);
                    clearFieldError('phone');
                  }}
                  keyboardType="phone-pad"
                  editable={!submitting}
                />
                {errors.phone ? (
                  <Text style={styles.fieldErrorText}>{errors.phone}</Text>
                ) : null}
              </View>
              <View>
                <Input
                  label="Email"
                  testID="auth-email"
                  placeholder="Value"
                  value={email}
                  onChangeText={(value) => {
                    setEmail(value);
                    clearFieldError('email');
                  }}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  textContentType="emailAddress"
                  editable={!submitting}
                />
                {errors.email ? (
                  <Text style={styles.fieldErrorText}>{errors.email}</Text>
                ) : null}
              </View>
              <View>
                <Input
                  label="Password"
                  testID="auth-password"
                  placeholder="At least 8 characters"
                  value={password}
                  onChangeText={(value) => {
                    setPassword(value);
                    clearFieldError('password');
                  }}
                  secureTextEntry
                  textContentType="newPassword"
                  editable={!submitting}
                />
                {errors.password ? (
                  <Text style={styles.fieldErrorText}>{errors.password}</Text>
                ) : null}
              </View>
            </View>

            <View style={styles.agreements}>
              <AgreementRow
                checked={usResident}
                label="I confirm that I reside in the United States."
                testID="auth-us-resident"
                onPress={() => {
                  setUsResident((value) => !value);
                  clearFieldError('residency');
                }}
              />
              {errors.residency ? (
                <Text style={styles.fieldErrorText}>{errors.residency}</Text>
              ) : null}
              <AgreementRow
                checked={termsAccepted}
                label="I agree to the beta Terms and acknowledge the Privacy Policy."
                testID="auth-terms"
                onPress={() => {
                  setTermsAccepted((value) => !value);
                  clearFieldError('terms');
                }}
              />
              {errors.terms ? (
                <Text style={styles.fieldErrorText}>{errors.terms}</Text>
              ) : null}
            </View>

            <View style={{ marginTop: 20 }}>
              <Text style={styles.securityTitle}>Security check</Text>
              <AuthChallenge
                action="signup"
                resetSignal={captchaReset}
                onTokenChange={setCaptchaToken}
                onError={setCaptchaError}
              />
            </View>

            {errors.general || captchaError ? (
              <Text style={styles.generalErrorText}>{errors.general ?? captchaError}</Text>
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
                testID="auth-submit"
                onPress={handleCreateAccount}
                disabled={submitting || !captchaToken || !usResident || !termsAccepted}
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
  agreements: {
    gap: 8,
    marginTop: 20,
  },
  agreementRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
  },
  agreementLabel: {
    color: '#D0D5DD',
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  checkbox: {
    alignItems: 'center',
    borderColor: '#667085',
    borderRadius: 4,
    borderWidth: 1,
    height: 22,
    justifyContent: 'center',
    width: 22,
  },
  checkboxChecked: {
    backgroundColor: '#2457B2',
    borderColor: '#82AEFF',
  },
  checkboxMark: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  securityTitle: {
    color: '#D0D5DD',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  fieldErrorText: {
    marginTop: 6,
    fontSize: 14,
    lineHeight: 20,
    color: '#FF8A8A',
  },
  generalErrorText: {
    marginTop: 16,
    fontSize: 14,
    lineHeight: 20,
    color: '#FF8A8A',
  },
  titleImage: {
    alignSelf: 'center',
    width: '200%',
    height: 350,
    marginBottom: -125,
    marginTop: -100,
  },
});
