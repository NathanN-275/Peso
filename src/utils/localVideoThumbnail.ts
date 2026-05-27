import * as VideoThumbnails from 'expo-video-thumbnails';
import { Platform } from 'react-native';

type LocalVideoThumbnailOptions = {
  timeMs: number;
  quality?: number;
};

export function getUriScheme(uri: string) {
  const match = /^([a-z][a-z0-9+.-]*):/i.exec(uri);
  return match?.[1] ?? 'unknown';
}

async function createWebVideoThumbnail(
  uri: string,
  { timeMs, quality = 0.7 }: LocalVideoThumbnailOptions
) {
  if (typeof document === 'undefined') {
    throw new Error('Document is unavailable for web video thumbnail generation.');
  }

  return new Promise<string>((resolve, reject) => {
    const video = document.createElement('video');
    const canvas = document.createElement('canvas');
    const cleanup = () => {
      video.pause();
      video.removeAttribute('src');
      video.load();
    };
    const fail = (error: unknown) => {
      cleanup();
      reject(error instanceof Error ? error : new Error('Unable to generate web video thumbnail.'));
    };

    video.muted = true;
    video.playsInline = true;
    video.preload = 'metadata';
    video.crossOrigin = 'anonymous';

    video.addEventListener(
      'loadedmetadata',
      () => {
        const durationMs = Number.isFinite(video.duration) ? video.duration * 1000 : timeMs;
        const targetSeconds = Math.max(0, Math.min(timeMs, durationMs || timeMs) / 1000);
        video.currentTime = targetSeconds;
      },
      { once: true }
    );

    video.addEventListener(
      'seeked',
      () => {
        const width = video.videoWidth;
        const height = video.videoHeight;

        if (!width || !height) {
          fail(new Error('Selected video did not expose frame dimensions.'));
          return;
        }

        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext('2d');

        if (!context) {
          fail(new Error('Canvas 2D context is unavailable.'));
          return;
        }

        context.drawImage(video, 0, 0, width, height);

        try {
          const dataUrl = canvas.toDataURL('image/jpeg', quality);
          cleanup();
          resolve(dataUrl);
        } catch (error) {
          fail(error);
        }
      },
      { once: true }
    );

    video.addEventListener('error', () => fail(new Error('Selected video could not be loaded.')), {
      once: true,
    });

    video.src = uri;
    video.load();
  });
}

export async function createLocalVideoThumbnail(
  uri: string,
  options: LocalVideoThumbnailOptions
) {
  if (Platform.OS === 'web') {
    return createWebVideoThumbnail(uri, options);
  }

  const thumbnail = await VideoThumbnails.getThumbnailAsync(uri, {
    time: options.timeMs,
    quality: options.quality ?? 0.7,
  });

  return thumbnail.uri;
}
