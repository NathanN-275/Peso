import type { ReactNode } from 'react';
import { Image, Pressable, StyleSheet, Text, View, type ImageStyle, type StyleProp } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import { useVideoThumbnail } from '../../lib/useVideoThumbnail';

export default function VideoThumbnail({ videoId, available, legacyUrl, style, placeholder, label = 'Video preview' }: {
  videoId: string; available: boolean; legacyUrl: string | null; style: StyleProp<ImageStyle>;
  placeholder?: ReactNode; label?: string;
}) {
  const { session } = useAuth();
  const preview = useVideoThumbnail(videoId, available, session?.access_token, legacyUrl);
  const { resizeMode: _resizeMode, ...container } = StyleSheet.flatten(style) ?? {};
  return (
    <View style={[container, styles.container]}>
      {preview.uri ? <Image source={{ uri: preview.uri }} style={StyleSheet.absoluteFill} resizeMode="cover" resizeMethod="resize"
        accessibilityLabel={label} accessibilityIgnoresInvertColors onError={preview.onImageError} /> : !preview.error ? placeholder : null}
      {preview.error ? <Pressable accessibilityRole="button" accessibilityLabel="Retry video preview" style={styles.retry}
        onPress={event => { event.stopPropagation(); preview.retry(); }}><Text style={styles.retryText}>Retry</Text></Pressable> : null}
    </View>
  );
}
const styles = StyleSheet.create({
  container: { overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  retry: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 6, backgroundColor: '#252525' },
  retryText: { color: '#FFFFFF', fontSize: 11 },
});
