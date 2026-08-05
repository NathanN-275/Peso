import * as VideoThumbnails from 'expo-video-thumbnails';
import { Platform } from 'react-native';
import { createWebVideoPreview } from '../../lib/webVideoSelectionPolicy';

type LocalVideoThumbnailOptions = {
  timeMs: number;
  quality?: number;
};

export function getUriScheme(uri: string) {
  const match = /^([a-z][a-z0-9+.-]*):/i.exec(uri);
  return match?.[1] ?? 'unknown';
}

export async function createLocalVideoThumbnail(
  uri: string,
  options: LocalVideoThumbnailOptions
) {
  if (Platform.OS === 'web') {
    const preview = await createWebVideoPreview(uri, options);
    return preview.thumbnail;
  }

  const thumbnail = await VideoThumbnails.getThumbnailAsync(uri, {
    time: options.timeMs,
    quality: options.quality ?? 0.7,
  });

  return thumbnail.uri;
}

export async function createLocalVideoPreview(
  uri: string,
  options: LocalVideoThumbnailOptions
) {
  if (Platform.OS === 'web') {
    const preview = await createWebVideoPreview(uri, options);
    return {
      thumbnailUri: preview.thumbnail,
      durationSeconds: preview.durationSeconds,
    };
  }

  return {
    thumbnailUri: await createLocalVideoThumbnail(uri, options),
    durationSeconds: null,
  };
}
