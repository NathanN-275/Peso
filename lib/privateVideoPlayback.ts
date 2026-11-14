import { fetch as streamingFetch } from 'expo/fetch';
import type { VideoSource } from 'expo-video';
import { Platform } from 'react-native';
import { getBackendApiUrl } from './backendConfig';
import { isLocalOrPrivateHostname } from './backendUrlPolicy';
import { getPrivateMediaEpoch, getActivePrivateMediaSessionKey, registerPrivateMediaRelease } from './privateMediaLifecycle';
import { getPrivateMediaSessionKey } from './privateMediaLogout';
import { isCanonicalUuid } from './profilePolicy';
import { supabaseAuthUrl } from './supabase';

export const VIDEO_PLAYBACK_FAILURE = 'Unable to load this video. Retry playback to request a new media session.';
export type VideoPlaybackLease = {
  source: VideoSource;
  expiresAt: number;
  assertCurrent(): void;
};
export type PrivateVideoAssetLease = {
  uri: string; headers: Readonly<Record<string, string>>; credentials: 'include' | 'omit'; expiresAt: number; assertCurrent(): void;
};
const browserAssets = ['export:barbell', 'export:clean', 'export:pose', 'export:pose-barbell', 'playback', 'thumbnail'] as const;
type VideoAsset = typeof browserAssets[number];
type ExportAsset = Extract<VideoAsset, `export:${string}`>;
export type VideoExportVariant = ExportAsset extends `export:${infer Variant}` ? Variant : never;
type DownloadAsset = { kind: 'video'; id: string; asset: ExportAsset }
  | { kind: 'archive'; id: string; asset: 'archive' };
type MediaAsset = { kind: 'video'; id: string; asset: VideoAsset } | Extract<DownloadAsset, { kind: 'archive' }>;
const DOWNLOAD_FAILURE = 'Unable to prepare this download. Try again.';
const requests = new Set<AbortController>();
registerPrivateMediaRelease(() => { for (const request of requests) request.abort(); });

// Only the fixed issuer receives the account JWT. Native byte sources get a media grant;
// browser byte sources rely on the host-only cookie at the verified session path.
async function issueMediaAsset({ kind, id, asset }: MediaAsset, accessToken: string, signal?: AbortSignal): Promise<PrivateVideoAssetLease> {
  const backend = getBackendApiUrl();
  const epoch = getPrivateMediaEpoch();
  const key = getPrivateMediaSessionKey(accessToken, supabaseAuthUrl);
  const assertIdentity = () => {
    if (!key || key !== getActivePrivateMediaSessionKey() || epoch !== getPrivateMediaEpoch()
        || backend !== getBackendApiUrl()) throw new Error(VIDEO_PLAYBACK_FAILURE);
  };
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  requests.add(controller);
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let cancel = () => {};
  const deadline = new Promise<never>((_, reject) => {
    cancel = () => reject(new Error(VIDEO_PLAYBACK_FAILURE));
    controller.signal.addEventListener('abort', cancel, { once: true });
    timeout = setTimeout(abort, 30_000);
  });
  void deadline.catch(() => {});
  const wait = <T>(work: Promise<T>): Promise<T> => Promise.race([work, deadline]);
  const check = () => { assertIdentity(); if (controller.signal.aborted) throw new Error(VIDEO_PLAYBACK_FAILURE); };
  try {
    check();
    if (process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED !== 'true' || !isCanonicalUuid(id)
        || !(kind === 'video' ? browserAssets.includes(asset as VideoAsset) : kind === 'archive' && asset === 'archive')) throw new Error(VIDEO_PLAYBACK_FAILURE);
    const origin = new URL(backend);
    if (origin.protocol !== 'https:' || isLocalOrPrivateHostname(origin.hostname) || origin.username || origin.password
        || origin.search || origin.hash || origin.href.replace(/\/$/, '') !== backend) throw new Error(VIDEO_PLAYBACK_FAILURE);
    const browser = Platform.OS === 'web';
    const root = `${backend}/private-media/${browser ? `session/${key!.split(':')[1]}/` : ''}${kind}/${id}/`;
    const response = await wait(streamingFetch(root + 'session', {
      method: 'POST', credentials: browser ? 'include' : 'omit', redirect: 'error', keepalive: false,
      ...(browser ? { cache: 'no-store' as const } : {}), signal: controller.signal,
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
      body: JSON.stringify({ transport: browser ? 'browser' : 'native', asset_kinds: [asset] }),
    }));
    check();
    if (response.status !== 200 || response.redirected
        || response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json'
        || !/(?:^|,)\s*private\s*(?:,|$)/i.test(response.headers.get('cache-control') ?? '')
        || !/(?:^|,)\s*no-store\s*(?:,|$)/i.test(response.headers.get('cache-control') ?? '')) throw new Error(VIDEO_PLAYBACK_FAILURE);
    const reader = response.body?.getReader();
    if (!reader) throw new Error(VIDEO_PLAYBACK_FAILURE);
    const bytes = new Uint8Array(8192); let size = 0;
    try {
      while (true) {
        const { done, value } = await wait(reader.read()); check();
        if (done) break;
        if (!(value instanceof Uint8Array) || !value.byteLength || size + value.byteLength > bytes.length) throw new Error(VIDEO_PLAYBACK_FAILURE);
        bytes.set(value, size); size += value.byteLength;
      }
    } finally { void reader.cancel().catch(() => {}); reader.releaseLock(); }
    const value = JSON.parse(new TextDecoder().decode(bytes.subarray(0, size)));
    const names = ['resource_kind', 'resource_id', 'urls', 'expires_in', 'expires_at', ...(browser ? [] : ['media_grant'])];
    const assets = browser && kind === 'video' ? browserAssets : [asset];
    const expiresAt = Date.parse(value?.expires_at);
    const remaining = expiresAt - Date.now();
    if (!value || Array.isArray(value) || Object.keys(value).length !== names.length || names.some(name => !Object.hasOwn(value, name))
        || value.resource_kind !== kind || value.resource_id !== id || !value.urls || Array.isArray(value.urls)
        || Object.keys(value.urls).length !== assets.length || assets.some(asset => value.urls[asset] !== root + encodeURIComponent(asset))
        || !Number.isInteger(value.expires_in) || value.expires_in < 1 || value.expires_in > 300
        || typeof value.expires_at !== 'string' || value.expires_at.length > 64
        || !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value.expires_at) || !Number.isFinite(expiresAt)
        || remaining <= 0 || remaining > 300_000 || remaining > (value.expires_in + 2) * 1000
        || !browser && (typeof value.media_grant !== 'string' || !/^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$/.test(value.media_grant))) throw new Error(VIDEO_PLAYBACK_FAILURE);
    check();
    const headers: Readonly<Record<string, string>> = browser ? Object.freeze({}) : Object.freeze({ 'X-Peso-Media-Grant': value.media_grant });
    return { uri: root + encodeURIComponent(asset), headers,
      credentials: browser ? 'include' : 'omit', expiresAt, assertCurrent() {
      assertIdentity();
      if (Date.now() >= expiresAt) throw new Error(VIDEO_PLAYBACK_FAILURE);
    } };
  } catch { throw new Error(VIDEO_PLAYBACK_FAILURE); }
  finally {
    clearTimeout(timeout); controller.signal.removeEventListener('abort', cancel); controller.abort();
    signal?.removeEventListener('abort', abort); requests.delete(controller);
  }
}


export async function issuePrivateVideoAsset(videoId: string, accessToken: string, asset: 'playback' | 'thumbnail', signal?: AbortSignal) {
  if (asset !== 'playback' && asset !== 'thumbnail') throw new Error(VIDEO_PLAYBACK_FAILURE);
  return issueMediaAsset({ kind: 'video', id: videoId, asset }, accessToken, signal);
}

export async function issueBrowserPrivateDownload(target: DownloadAsset, accessToken: string, signal?: AbortSignal) {
  try {
    if (Platform.OS !== 'web' || !(target.kind === 'archive' ? target.asset === 'archive'
        : target.kind === 'video' && target.asset.startsWith('export:'))) throw new Error(DOWNLOAD_FAILURE);
    const asset = encodeURIComponent(target.asset);
    const lease = await issueMediaAsset(target, accessToken, signal);
    const root = lease.uri.slice(0, -asset.length);
    return { href: root + 'download/' + asset, expiresAt: lease.expiresAt, assertCurrent: lease.assertCurrent };
  } catch {
    throw new Error(DOWNLOAD_FAILURE);
  }
}

export async function issueNativePrivateDownload(videoId: string, accessToken: string,
  variant: VideoExportVariant, signal?: AbortSignal) {
  try {
    if (Platform.OS !== 'ios' && Platform.OS !== 'android') throw new Error(DOWNLOAD_FAILURE);
    const lease = await issueMediaAsset({ kind: 'video', id: videoId, asset: `export:${variant}` }, accessToken, signal);
    return { uri: lease.uri, grant: lease.headers['X-Peso-Media-Grant'], assertCurrent: lease.assertCurrent };
  } catch {
    throw new Error(DOWNLOAD_FAILURE);
  }
}

export async function issuePrivateVideoPlayback(videoId: string, accessToken: string, signal?: AbortSignal): Promise<VideoPlaybackLease> {
  const lease = await issuePrivateVideoAsset(videoId, accessToken, 'playback', signal);
  return { expiresAt: lease.expiresAt, assertCurrent: lease.assertCurrent,
    source: Object.freeze({ uri: lease.uri, useCaching: false, contentType: 'progressive' as const,
      ...(lease.credentials === 'omit' ? { headers: Object.freeze({ ...lease.headers, 'Cache-Control': 'no-store' }) } : {}) }) };
}
