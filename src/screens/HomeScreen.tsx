import { SafeAreaView, Text, View } from 'react-native';
import tokens from '../theme/tokens';

type HomeScreenProps = {
  email?: string | null;
};

function HomeIcon() {
  return (
    <View style={{ width: 28, height: 28, alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          width: 14,
          height: 11,
          borderWidth: 2,
          borderColor: tokens.colors.brand,
          borderBottomLeftRadius: 2,
          borderBottomRightRadius: 2,
        }}
      />
      <View
        style={{
          position: 'absolute',
          top: 5,
          width: 14,
          height: 14,
          transform: [{ rotate: '45deg' }],
          borderTopWidth: 2,
          borderLeftWidth: 2,
          borderColor: tokens.colors.brand,
          backgroundColor: 'transparent',
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: 6,
          width: 3,
          height: 6,
          borderWidth: 1.5,
          borderColor: tokens.colors.brand,
          borderRadius: 1,
        }}
      />
    </View>
  );
}

function AddIcon({ large = false }: { large?: boolean }) {
  const size = large ? 60 : 28;
  const line = large ? 24 : 10;
  const stroke = large ? 3 : 2;

  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        borderWidth: stroke,
        borderColor: tokens.colors.brand,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <View
        style={{
          position: 'absolute',
          width: line,
          height: stroke,
          borderRadius: stroke,
          backgroundColor: tokens.colors.brand,
        }}
      />
      <View
        style={{
          position: 'absolute',
          width: stroke,
          height: line,
          borderRadius: stroke,
          backgroundColor: tokens.colors.brand,
        }}
      />
    </View>
  );
}

function ProfileIcon() {
  return (
    <View style={{ width: 28, height: 28, alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          position: 'absolute',
          top: 3,
          width: 9,
          height: 9,
          borderWidth: 2,
          borderColor: tokens.colors.brand,
          borderRadius: 999,
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: 3,
          width: 18,
          height: 10,
          borderWidth: 2,
          borderColor: tokens.colors.brand,
          borderTopLeftRadius: 12,
          borderTopRightRadius: 12,
          borderBottomWidth: 0,
        }}
      />
    </View>
  );
}

export default function HomeScreen({ email }: HomeScreenProps) {
  return (
    <SafeAreaView className="flex-1 bg-bg">
      <View className="flex-1" style={{ paddingHorizontal: tokens.spacing.screenX }}>
        <Text
          className="text-text-muted"
          style={{ marginTop: 8, marginBottom: 12, fontSize: 16, marginLeft: 2 }}
        >
          Home Screen - new user
        </Text>

        <View className="flex-1 bg-black" style={{ overflow: 'hidden' }}>
          <View
            className="flex-1 items-center justify-center"
            style={{ paddingHorizontal: 36, paddingBottom: 70 }}
          >
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

            <AddIcon large />

            {email ? (
              <Text
                className="text-text-muted"
                style={{ marginTop: 28, fontSize: 12, textAlign: 'center' }}
              >
                {email}
              </Text>
            ) : null}
          </View>

          <View
            style={{
              height: 58,
              backgroundColor: '#2A2A2A',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-around',
              paddingHorizontal: 24,
            }}
          >
            <HomeIcon />
            <AddIcon />
            <ProfileIcon />
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}
