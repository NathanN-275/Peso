import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, SafeAreaView, Text, View } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import tokens from '../theme/tokens';

const SECONDARY_NAV_ICON = '#174A82';
const NAV_ICON_SIZE = 34;

type HomeScreenProps = {
  email?: string | null;
};

export default function HomeScreen({ email }: HomeScreenProps) {
  const { signOut } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleLogout = async () => {
    setSubmitting(true);
    setErrorMessage(null);

    try {
      await signOut();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to log out.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-bg" style={{ flex: 1, height: '100%' }}>
      <View className="flex-1 bg-black" style={{ flex: 1, height: '100%', overflow: 'hidden' }}>
        <Pressable
          onPress={handleLogout}
          disabled={submitting}
          accessibilityRole="button"
          style={{
            position: 'absolute',
            top: 18,
            left: 18,
            zIndex: 1,
            paddingHorizontal: 12,
            paddingVertical: 8,
            borderWidth: 1,
            borderColor: tokens.colors.brand,
            borderRadius: 999,
          }}
        >
          <Text style={{ color: tokens.colors.brand, fontSize: 12, fontWeight: '700' }}>
            {submitting ? 'Logging Out...' : 'Log Out'}
          </Text>
        </Pressable>

        <View
          className="flex-1 items-center justify-center"
          style={{ paddingHorizontal: 36, paddingBottom: 96 }}
        >
          <View style={{ alignItems: 'center', justifyContent: 'center', maxWidth: 320 }}>
            <Text
              style={{
                color: tokens.colors.brand,
                fontSize: 16,
                lineHeight: 25,
                fontWeight: '700',
                textAlign: 'center',
                marginBottom: 28,
              }}
            >
              Add or record a video,{'\n'}saved videos will appear{'\n'}on the home screen
            </Text>

            <Ionicons name="add-circle-outline" size={60} color={tokens.colors.brand} />

            {errorMessage ? (
              <Text
                className="text-text-primary"
                style={{ marginTop: 20, fontSize: 12, textAlign: 'center', color: '#FF8A8A' }}
              >
                {errorMessage}
              </Text>
            ) : null}

          </View>
        </View>

        <View
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            height: 58,
            width: '100%',
            backgroundColor: '#2A2A2A',
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-around',
            paddingHorizontal: 24,
          }}
        >
          <Ionicons name="home-outline" size={NAV_ICON_SIZE} color={tokens.colors.brand} />
          <Ionicons name="add-circle-outline" size={NAV_ICON_SIZE} color={SECONDARY_NAV_ICON} />
          <Ionicons name="person-outline" size={NAV_ICON_SIZE} color={SECONDARY_NAV_ICON} />
        </View>
      </View>
    </SafeAreaView>
  );
}
