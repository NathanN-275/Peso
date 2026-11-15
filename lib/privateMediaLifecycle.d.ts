export function registerPrivateMediaRelease(release: () => void | Promise<void>): () => void;
export function releasePrivateMedia(): Promise<void>;
export function getPrivateMediaEpoch(): number;
export function setActivePrivateMediaSessionKey(key: string | null): void;
export function getActivePrivateMediaSessionKey(): string | null;
export function releaseBrowserMedia(video: {
  pause(): void; removeAttribute(name: string): void; load(): void;
} | null): void;
export function releaseNativeMedia(player: {
  pause(): void; replaceAsync(source: null): Promise<void>;
}): Promise<void>;
// Use from a useVideoPlayer effect; its hook owns object disposal.
export function registerNativePrivateMedia(player: {
  pause(): void; replaceAsync(source: null): Promise<void>;
}): () => void;

export function attachPrivateMediaSource(player: {
  pause(): void; replaceAsync(source: import('expo-video').VideoSource): Promise<void>;
}, source: import('expo-video').VideoSource, assertCurrent: () => void, onReady: () => void, onError: () => void): () => void;
