import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Button from '../components/Button';
import tokens from '../theme/tokens';

type UploadVideoScreenProps = {
  onBack?: () => void;
};

export default function UploadVideoScreen({ onBack }: UploadVideoScreenProps) {
  const [permissionStatus, setPermissionStatus] = useState<ImagePicker.PermissionStatus | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const hasRequestedPermissionRef = useRef(false);

  const launchPicker = async () => {
    if (pickerOpen) {
      return;
    }

    setPickerOpen(true);

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
        allowsEditing: false,
        quality: 1,
      });

      if (result.canceled) {
        return;
      }
    } finally {
      setPickerOpen(false);
    }
  };

  const promptForSettings = () => {
    Alert.alert(
      'Camera roll access needed',
      'Peso needs access to your camera roll to upload videos.',
      [
        {
          text: 'Accept',
          onPress: () => {
            void requestPermission(true);
          },
        },
        {
          text: 'Settings',
          onPress: () => {
            void Linking.openSettings();
          },
        },
      ],
      { cancelable: true }
    );
  };

  const requestPermission = async (forcePrompt = false) => {
    const currentPermission = await ImagePicker.getMediaLibraryPermissionsAsync();
    setPermissionStatus(currentPermission.status);

    if (currentPermission.granted) {
      await launchPicker();
      return;
    }

    if (currentPermission.canAskAgain || forcePrompt) {
      const requestedPermission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      setPermissionStatus(requestedPermission.status);

      if (requestedPermission.granted) {
        await launchPicker();
        return;
      }
    }

    if (Platform.OS !== 'web') {
      promptForSettings();
    }
  };

  useEffect(() => {
    let isMounted = true;

    const initializePermissionFlow = async () => {
      const currentPermission = await ImagePicker.getMediaLibraryPermissionsAsync();

      if (!isMounted) {
        return;
      }

      setPermissionStatus(currentPermission.status);

      if (!currentPermission.granted && !hasRequestedPermissionRef.current) {
        hasRequestedPermissionRef.current = true;
        await requestPermission();
        return;
      }

      if (currentPermission.granted) {
        await launchPicker();
      }
    };

    void initializePermissionFlow();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <Button label="Back" onPress={onBack} style={styles.backButton} />

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Choose video from camera roll"
          onPress={() => {
            if (permissionStatus === 'granted') {
              void launchPicker();
              return;
            }

            void requestPermission(true);
          }}
          style={styles.content}
        >
          <Ionicons name="cloud-upload-outline" size={72} color={tokens.colors.textPrimary} />
          <Text style={styles.copy}>Select a video from your camera roll to upload</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
  },
  container: {
    flex: 1,
    backgroundColor: '#000',
    paddingHorizontal: 16,
  },
  backButton: {
    width: 52,
    minHeight: 32,
    alignSelf: 'flex-start',
    marginTop: 18,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 7,
    backgroundColor: '#3B6EEA',
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 36,
    paddingBottom: 88,
  },
  copy: {
    marginTop: 28,
    color: '#E6E6E6',
    fontSize: 16,
    lineHeight: 27,
    fontWeight: '600',
    textAlign: 'center',
    maxWidth: 260,
  },
});
