import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useEffect, useState } from 'react';
import { LayoutChangeEvent } from 'react-native';
import { Alert, Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Button from '../components/Button';
import VideoSetupModal from '../components/VideoSetupModal';
import { VideoSetupSelection } from '../constants/videoSetup';
import tokens from '../theme/tokens';

type UploadVideoScreenProps = {
  onBack?: () => void;
};

function formatFileSize(fileSize?: number | null) {
  if (typeof fileSize !== 'number') {
    return null;
  }

  return `${(fileSize / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadVideoScreen({ onBack }: UploadVideoScreenProps) {
  const [permissionStatus, setPermissionStatus] = useState<ImagePicker.PermissionStatus | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [setupModalVisible, setSetupModalVisible] = useState(true);
  const [videoSetup, setVideoSetup] = useState<VideoSetupSelection | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [screenLayout, setScreenLayout] = useState({ width: 0, height: 0 });

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

      const nextAsset = result.assets[0];

      if (nextAsset) {
        setSelectedVideo(nextAsset);
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

  const syncPermissionStatus = async () => {
    const currentPermission = await ImagePicker.getMediaLibraryPermissionsAsync();
    setPermissionStatus(currentPermission.status);
    return currentPermission;
  };

  const requestPermission = async (forcePrompt = false) => {
    const currentPermission = await syncPermissionStatus();

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
    void syncPermissionStatus();
  }, []);

  const handleModalContinue = async (selection: VideoSetupSelection) => {
    setVideoSetup(selection);
    setSetupModalVisible(false);
    await requestPermission(true);
  };

  const handleModalCancel = () => {
    if (onBack) {
      onBack();
      return;
    }

    setSetupModalVisible(false);
  };

  const handlePickVideoPress = () => {
    if (permissionStatus === 'granted') {
      void launchPicker();
      return;
    }

    void requestPermission(true);
  };

  const resolvedVideoName =
    selectedVideo?.fileName ?? selectedVideo?.uri.split('/').pop() ?? 'Selected video';
  const resolvedFileSize = formatFileSize(selectedVideo?.fileSize);
  const handleScreenLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    const { width, height } = nativeEvent.layout;

    if (width === screenLayout.width && height === screenLayout.height) {
      return;
    }

    setScreenLayout({ width, height });
  };

  return (
    <SafeAreaView style={styles.safeArea} onLayout={handleScreenLayout}>
      <VideoSetupModal
        visible={setupModalVisible}
        initialSelection={videoSetup}
        availableWidth={screenLayout.width || undefined}
        availableHeight={screenLayout.height || undefined}
        onContinue={(selection) => {
          void handleModalContinue(selection);
        }}
        onCancel={handleModalCancel}
      />

      <View style={styles.container}>
        <Button label="Back" onPress={onBack} style={styles.backButton} />

        <View style={styles.content}>
          <Ionicons name="cloud-upload-outline" size={72} color={tokens.colors.textPrimary} />
          <Text style={styles.title}>Upload Video</Text>
          <Text style={styles.copy}>
            Confirm the exercise and camera angle, then select a video from your camera roll.
          </Text>

          {videoSetup ? (
            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>Selected setup</Text>
              <View style={styles.badgesRow}>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{videoSetup.exercise}</Text>
                </View>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{videoSetup.angle}</Text>
                </View>
              </View>
            </View>
          ) : null}

          {selectedVideo ? (
            <View style={styles.videoCard}>
              <Text style={styles.videoCardLabel}>Selected video</Text>
              <Text style={styles.videoCardName}>{resolvedVideoName}</Text>
              {resolvedFileSize ? <Text style={styles.videoCardMeta}>{resolvedFileSize}</Text> : null}
            </View>
          ) : null}

          <View style={styles.actions}>
            <Button
              label={selectedVideo ? 'Choose Another Video' : 'Choose Video'}
              onPress={handlePickVideoPress}
              style={styles.primaryAction}
            />
            <Pressable
              accessibilityRole="button"
              onPress={() => setSetupModalVisible(true)}
              style={styles.secondaryAction}
            >
              <Text style={styles.secondaryActionText}>
                {videoSetup ? 'Edit Video Setup' : 'Open Video Setup'}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
    position: 'relative',
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
    paddingHorizontal: 28,
    paddingBottom: 72,
  },
  title: {
    marginTop: 22,
    color: tokens.colors.textPrimary,
    fontSize: 26,
    lineHeight: 32,
    fontWeight: '700',
    textAlign: 'center',
  },
  copy: {
    marginTop: 18,
    color: '#E6E6E6',
    fontSize: 16,
    lineHeight: 25,
    fontWeight: '500',
    textAlign: 'center',
    maxWidth: 292,
  },
  summaryCard: {
    width: '100%',
    marginTop: 26,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#12161D',
    paddingHorizontal: 18,
    paddingVertical: 18,
    gap: 14,
  },
  summaryTitle: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  badgesRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  badge: {
    borderRadius: 999,
    backgroundColor: '#1A2432',
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  badgeText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '600',
  },
  videoCard: {
    width: '100%',
    marginTop: 16,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0F1218',
    paddingHorizontal: 18,
    paddingVertical: 16,
    gap: 6,
  },
  videoCardLabel: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  videoCardName: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
  },
  videoCardMeta: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  actions: {
    width: '100%',
    marginTop: 28,
    gap: 12,
  },
  primaryAction: {
    width: '100%',
    maxWidth: 320,
  },
  secondaryAction: {
    alignSelf: 'center',
    paddingVertical: 8,
  },
  secondaryActionText: {
    color: tokens.colors.textMuted,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '600',
  },
});
