// when the user logs in, this is the home screen
import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import tokens from '../theme/tokens';

type HomeScreenProps = {
  email?: string | null;
  onNavigateToAddVideo?: () => void;
};

export default function HomeScreen({ email, onNavigateToAddVideo }: HomeScreenProps) {
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
          style={{ paddingHorizontal: 36, paddingBottom: NAV_HEIGHT + 38 }}
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

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Add video"
              hitSlop={16}
              onPress={onNavigateToAddVideo}
            >
              <Ionicons name="add-circle-outline" size={60} color={tokens.colors.brand} />
            </Pressable>

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

        <BottomNav activeTab="home" onHomePress={() => {}} onAddPress={onNavigateToAddVideo} />
      </View>
    </SafeAreaView>
  );
}
