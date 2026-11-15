import { fetch as streamingFetch } from 'expo/fetch';
import { Platform } from 'react-native';
import { issuePrivateVideoAsset } from './privateVideoPlayback';
import { getBackendApiUrl } from './backendConfig';
import { getPrivateMediaEpoch, getActivePrivateMediaSessionKey, registerPrivateMediaRelease } from './privateMediaLifecycle';
import { thumbnailDataUri, THUMBNAIL_BYTE_LIMIT } from './thumbnailBytes';

export const THUMBNAIL_FAILURE = 'Unable to load this preview.';
const requests = new Set<AbortController>();
registerPrivateMediaRelease(() => { for (const request of requests) request.abort(); });
let active = 0;
const queue: Array<{ signal: AbortSignal; start(): void }> = [];
function enter(signal: AbortSignal): Promise<() => void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      const index = queue.indexOf(ticket); if (index >= 0) queue.splice(index, 1);
      reject(new Error(THUMBNAIL_FAILURE));
    };
    const ticket = { signal, start() {
      signal.removeEventListener('abort', abort);
      if (signal.aborted) { reject(new Error(THUMBNAIL_FAILURE)); return; }
      active++;
      resolve(() => {
        active--;
        while (active < 2 && queue.length) queue.shift()!.start();
      });
    } };
    if (signal.aborted || queue.length >= 64) { reject(new Error(THUMBNAIL_FAILURE)); return; }
    if (active < 2) ticket.start();
    else { queue.push(ticket); signal.addEventListener('abort', abort, { once: true }); }
  });
}

// The four-MiB budget bounds optional preview memory, not video uploads/exports.
// Two admitted reads fit below the backend's four-stream per-owner limit.
export async function readPrivateVideoThumbnail(videoId: string, accessToken: string, signal?: AbortSignal) {
  const epoch = getPrivateMediaEpoch(), key = getActivePrivateMediaSessionKey(), backend = getBackendApiUrl();
  const context = () => { if (!key || key !== getActivePrivateMediaSessionKey() || epoch !== getPrivateMediaEpoch() || backend !== getBackendApiUrl()) throw new Error(THUMBNAIL_FAILURE); };
  const controller = new AbortController(); requests.add(controller);
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true }); if (signal?.aborted) abort();
  let timeout: ReturnType<typeof setTimeout> | undefined, cancel = () => {};
  const deadline = new Promise<never>((_, reject) => {
    cancel = () => reject(new Error(THUMBNAIL_FAILURE)); controller.signal.addEventListener('abort', cancel, { once: true });
    timeout = setTimeout(abort, 30_000);
  });
  void deadline.catch(() => {});
  const wait = <T>(work: Promise<T>): Promise<T> => Promise.race([work, deadline]);
  let leave: (() => void) | undefined;
  try {
    leave = await enter(controller.signal); context();
    const lease = await wait(issuePrivateVideoAsset(videoId, accessToken, 'thumbnail', controller.signal));
    const check = () => { context(); lease.assertCurrent(); if (controller.signal.aborted) throw new Error(THUMBNAIL_FAILURE); };
    check();
    const response = await wait(streamingFetch(lease.uri, {
      method: 'GET', credentials: lease.credentials, redirect: 'error', keepalive: false,
      ...(Platform.OS === 'web' ? { cache: 'no-store' as const } : {}), signal: controller.signal,
      headers: { ...lease.headers, Accept: 'image/jpeg', 'Cache-Control': 'no-store' },
    }));
    check();
    const length = response.headers.get('content-length');
    if (response.status !== 200 || response.redirected || response.headers.get('content-type')?.toLowerCase() !== 'image/jpeg'
        || !/(?:^|,)\s*private\s*(?:,|$)/i.test(response.headers.get('cache-control') ?? '')
        || !/(?:^|,)\s*no-store\s*(?:,|$)/i.test(response.headers.get('cache-control') ?? '')
        || length === null || !/^[1-9][0-9]{0,6}$/.test(length) || Number(length) > THUMBNAIL_BYTE_LIMIT) throw new Error(THUMBNAIL_FAILURE);
    const reader = response.body?.getReader(); if (!reader) throw new Error(THUMBNAIL_FAILURE);
    const bytes = new Uint8Array(Number(length)); let size = 0;
    try {
      while (true) {
        const { done, value } = await wait(reader.read()); check();
        if (done) break;
        if (!(value instanceof Uint8Array) || !value.byteLength || size + value.byteLength > bytes.length) throw new Error(THUMBNAIL_FAILURE);
        bytes.set(value, size); size += value.byteLength;
      }
    } finally { void reader.cancel().catch(() => {}); reader.releaseLock(); }
    check(); if (size !== bytes.length) throw new Error(THUMBNAIL_FAILURE);
    const dataUri = thumbnailDataUri(bytes); check();
    return { dataUri, expiresAt: lease.expiresAt, assertCurrent: lease.assertCurrent };
  } catch { throw new Error(THUMBNAIL_FAILURE); }
  finally {
    clearTimeout(timeout); controller.signal.removeEventListener('abort', cancel); controller.abort();
    signal?.removeEventListener('abort', abort); requests.delete(controller); leave?.();
  }
}
