import { fetch as streamingFetch } from 'expo/fetch';
import type { AnalyzedVideoExportOptions } from './backendApi';
import { getBackendApiUrl } from './backendConfig';
import { getPrivateExportFiles } from './privateExportFiles';
import { getActivePrivateMediaSessionKey, getPrivateMediaEpoch, registerPrivateMediaRelease } from './privateMediaLifecycle';
import { getPrivateMediaSessionKey } from './privateMediaLogout';
import { issueNativePrivateDownload, type VideoExportVariant } from './privateVideoPlayback';
import { isCanonicalUuid } from './profilePolicy';
import { supabaseAuthUrl } from './supabase';
import { buildAnalyzedVideoExportPayload } from './videoRequestPayloadPolicy';

const failure = 'Unable to save the private video export. Try again.';
const cleanupFailure = 'Unable to clear the temporary video export. Try again.';
let active: { retryCleanup(): void } | null = null;

async function prepareVideo(backend: string, videoId: string, accessToken: string,
  options: AnalyzedVideoExportOptions, variant: VideoExportVariant, signal: AbortSignal) {
  const controller = new AbortController();
  let rejectStop: () => void = () => {};
  const stopped = new Promise<never>((_, reject) => {
    rejectStop = () => reject(new Error(failure));
  });
  void stopped.catch(() => {});
  const stop = () => {
    controller.abort();
    rejectStop();
  };
  signal.addEventListener('abort', stop, { once: true });
  const timer = setTimeout(stop, 5 * 60_000);
  const wait = <T>(pending: Promise<T>) => Promise.race([pending, stopped]);
  try {
    if (signal.aborted) throw new Error(failure);
    const response = await wait(streamingFetch(`${backend}/videos/${videoId}/analyzed-export`, {
      method: 'POST',
      signal: controller.signal,
      redirect: 'error',
      credentials: 'omit',
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
      body: JSON.stringify(buildAnalyzedVideoExportPayload(options)),
    }));
    if (signal.aborted || response.redirected || response.status !== 200
        || response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') throw new Error(failure);
    const reader = response.body?.getReader();
    if (!reader) throw new Error(failure);
    const bytes = new Uint8Array(8192);
    let used = 0;
    try {
      while (true) {
        const { done, value } = await wait(reader.read());
        if (signal.aborted) throw new Error(failure);
        if (done) break;
        if (!(value instanceof Uint8Array) || value.byteLength === 0 || used + value.byteLength > bytes.length) {
          throw new Error(failure);
        }
        bytes.set(value, used);
        used += value.byteLength;
      }
    } finally {
      void reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    const value = JSON.parse(new TextDecoder().decode(bytes.subarray(0, used)));
    if (!value || Array.isArray(value) || Object.keys(value).length !== 5
        || value.video_id !== videoId || value.variant !== variant || !isCanonicalUuid(value.analysis_id)
        || value.export_url !== null || value.storage_path !== null) throw new Error(failure);
  } finally {
    clearTimeout(timer);
    controller.abort();
    signal.removeEventListener('abort', stop);
  }
}

export async function savePrivateVideoExports(
  videoIds: string[],
  accessToken: string,
  options: AnalyzedVideoExportOptions,
  variant: VideoExportVariant,
  saveToLibrary: (uri: string) => Promise<void>,
  onSaved: (videoId: string) => void,
  signal: AbortSignal,
) {
  if (process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED !== 'true') throw new Error(failure);
  active?.retryCleanup();
  if (active || !videoIds.length || videoIds.some(id => !isCanonicalUuid(id))) throw new Error(failure);

  const files = getPrivateExportFiles();
  const key = getPrivateMediaSessionKey(accessToken, supabaseAuthUrl);
  const backend = getBackendApiUrl();
  const origin = new URL(backend);
  if (origin.protocol !== 'https:' || origin.port || origin.username || origin.password
      || origin.origin !== backend
      || (origin.hostname !== 'usepeso.com' && !origin.hostname.endsWith('.usepeso.com'))) throw new Error(failure);
  const epoch = getPrivateMediaEpoch();
  const controller = new AbortController();
  const check = () => {
    if (controller.signal.aborted || signal.aborted || !key || key !== getActivePrivateMediaSessionKey()
        || epoch !== getPrivateMediaEpoch() || backend !== getBackendApiUrl()) throw new Error(failure);
  };
  check();

  let fileId: string | null = null;
  let settled = false;
  let unregister: () => void;
  const cleanup = () => {
    if (!fileId) return;
    try {
      files.remove(fileId);
      fileId = null;
    } catch {
      throw new Error(cleanupFailure);
    }
  };
  const finishCleanup = () => {
    cleanup();
    active = null;
    unregister();
  };
  const cancel = () => {
    controller.abort();
    // The native promise must settle even after cancellation. Only then may
    // cleanup unlink a file or acknowledge release.
    if (fileId) {
      try { files.cancel(fileId); } catch { /* Join the original promise below. */ }
    }
  };
  let work: Promise<void>;
  const release = async () => {
    cancel();
    await work.catch(() => {});
    if (fileId) finishCleanup();
  };
  active = { retryCleanup() { if (settled && fileId) finishCleanup(); } };
  unregister = registerPrivateMediaRelease(release);
  signal.addEventListener('abort', cancel, { once: true });

  work = Promise.resolve().then(async () => {
    for (const videoId of videoIds) {
      check();
      await prepareVideo(backend, videoId, accessToken, options, variant, controller.signal);
      check();
      const lease = await issueNativePrivateDownload(videoId, accessToken, variant, controller.signal);
      check();
      lease.assertCurrent();
      fileId = files.reserve();
      try {
        if (!isCanonicalUuid(fileId)) throw new Error(failure);
        const uri = await files.download(fileId, lease.uri, lease.grant);
        check();
        const file = new URL(uri);
        const suffix = file.pathname.split('/').at(-1);
        if (file.protocol !== 'file:' || file.host || file.search || file.hash
            || !suffix || !/^asset\.(mp4|mov|m4v|webm|mkv)$/.test(suffix)
            || !file.pathname.endsWith(`/peso-private-export-v1/${fileId}/${suffix}`)) throw new Error(failure);
        await saveToLibrary(uri);
        check();
        onSaved(videoId);
      } finally {
        cleanup();
      }
    }
  }).finally(() => {
    settled = true;
    signal.removeEventListener('abort', cancel);
    if (!fileId) finishCleanup();
  });
  try {
    await work;
  } catch {
    if (fileId) throw new Error(cleanupFailure);
    throw new Error(failure);
  }
}
