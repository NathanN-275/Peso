import { Ionicons } from '@expo/vector-icons';
import { Image, StyleSheet, View } from 'react-native';
import tokens from '../theme/tokens';

type SelectedVideoPreviewProps = {
  thumbnailUri?: string | null;
};

export default function SelectedVideoPreview({
  thumbnailUri,
}: SelectedVideoPreviewProps) {
  return (
    <View style={styles.container}>
      {thumbnailUri ? (
        <Image source={{ uri: thumbnailUri }} style={styles.thumbnail} />
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
