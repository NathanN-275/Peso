import { useEvent } from 'expo';
import { Ionicons } from '@expo/vector-icons';
import { VideoView, useVideoPlayer } from 'expo-video';
import { useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';
import tokens from '../theme/tokens';

type SelectedVideoPreviewProps = {
  videoUri: string;
  thumbnailUri?: string | null;
};

export default function SelectedVideoPreview({
  videoUri,
  thumbnailUri,
}: SelectedVideoPreviewProps) {
  const [hasRenderedFrame, setHasRenderedFrame] = useState(false);
  const player = useVideoPlayer(videoUri, (videoPlayer) => {
    videoPlayer.muted = true;
    videoPlayer.loop = false;
  });
  const { isPlaying } = useEvent(player, 'playingChange', { isPlaying: player.playing });

  useEffect(() => {
    setHasRenderedFrame(false);
    player.pause();
    player.currentTime = 0;
  }, [player, videoUri]);

  const handleTogglePlayback = () => {
    if (isPlaying) {
      player.pause();
      return;
    }

    player.play();
  };

  return (
    <Pressable onPress={handleTogglePlayback} style={styles.container}>
      <VideoView
        style={styles.video}
        player={player}
        nativeControls={false}
        allowsPictureInPicture={false}
        contentFit="cover"
        onFirstFrameRender={() => {
          setHasRenderedFrame(true);
        }}
      />

      {!hasRenderedFrame ? (
        thumbnailUri ? (
          <Image source={{ uri: thumbnailUri }} style={styles.thumbnail} />
        ) : (
          <View style={styles.placeholder}>
            <Ionicons name="videocam" size={20} color={tokens.colors.textMuted} />
          </View>
        )
      ) : null}

      <View style={styles.overlay}>
        <View style={styles.playbackBadge}>
          <Ionicons
            name={isPlaying ? 'pause' : 'play'}
            size={14}
            color={tokens.colors.textPrimary}
          />
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    height: '100%',
    position: 'relative',
    backgroundColor: '#151A22',
  },
  video: {
    width: '100%',
    height: '100%',
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
