import { Ionicons } from '@expo/vector-icons';
import { Image, StyleSheet, View } from 'react-native';
import tokens from '../theme/tokens';

type SelectedVideoPreviewProps = {
  videoUri: string;
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
          <Ionicons name="videocam" size={20} color={tokens.colors.textMuted} />
        </View>
      )}

      <View style={styles.overlay}>
        <View style={styles.playbackBadge}>
          <Ionicons name="play" size={14} color={tokens.colors.textPrimary} />
        </View>
      </View>
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
  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'flex-end',
    alignItems: 'flex-end',
    padding: 8,
  },
  playbackBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
  },
});
