import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Image, StyleSheet, View } from 'react-native';
import type { ImageErrorEventData, NativeSyntheticEvent } from 'react-native';
import tokens from '../theme/tokens';

type SelectedVideoPreviewProps = {
  thumbnailUri?: string | null;
  thumbnailLoading?: boolean;
};

export default function SelectedVideoPreview({
  thumbnailUri,
  thumbnailLoading = false,
}: SelectedVideoPreviewProps) {
  const handleThumbnailError = (event: NativeSyntheticEvent<ImageErrorEventData>) => {
    if (__DEV__) {
      console.warn('[SelectedVideoPreview] thumbnail image failed to render', {
        thumbnailUri,
        error: event.nativeEvent,
      });
    }
  };

  return (
    <View style={styles.container}>
      {thumbnailUri ? (
        <Image
          source={{ uri: thumbnailUri }}
          style={styles.thumbnail}
          resizeMode="cover"
          onError={handleThumbnailError}
        />
      ) : thumbnailLoading ? (
        <View style={styles.placeholder}>
          <ActivityIndicator color={tokens.colors.textMuted} />
        </View>
      ) : (
        <View style={styles.placeholder}>
          <Ionicons name="image-outline" size={20} color={tokens.colors.textMuted} />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    height: '100%',
    position: 'relative',
    backgroundColor: '#151A22',
  },
  thumbnail: {
    ...StyleSheet.absoluteFillObject,
    width: undefined,
    height: undefined,
  },
  placeholder: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#151A22',
  },
});
