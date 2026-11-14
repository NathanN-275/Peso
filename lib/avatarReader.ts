import { fetch as streamingFetch } from 'expo/fetch';
import { Platform } from 'react-native';
import { getBackendApiUrl } from './backendConfig';
import { isLocalOrPrivateHostname } from './backendUrlPolicy';
import { getActivePrivateMediaSessionKey, getPrivateMediaEpoch, registerPrivateMediaRelease } from './privateMediaLifecycle';
import { getPrivateMediaSessionKey } from './privateMediaLogout';
import { supabaseAuthUrl } from './supabase';
import { isCanonicalUuid } from './profilePolicy';

const LIMIT = 512 * 1024;
const FAILURE = 'Unable to load profile picture. Reload your profile to retry.';
const LEGACY = 'Re-upload your profile picture to finish the security update.';
let generation = 0;
let order = 0;
let latestObservation = 0;
let mutation: symbol | null = null;
let observed: { key: string; revision: string | null } | null = null;
const requests = new Set<AbortController>();
const listeners = new Set<() => void>();

function invalidate() {
  generation += 1;
  for (const controller of requests) controller.abort();
  for (const listener of listeners) { try { listener(); } catch {} }
}
registerPrivateMediaRelease(() => { mutation = null; observed = null; invalidate(); });
export function subscribeProfileAvatarRelease(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

// A newer local write or observed metadata revision invalidates older image work.
export function beginProfileAvatarOperation(writing = false) {
  if (writing) {
    if (mutation !== null) throw new Error('A profile update is already in progress.');
    invalidate();
  }
  const intent = writing ? Symbol('profile mutation') : null;
  if (intent) mutation = intent;
  let expectedGeneration = generation;
  const requestOrder = ++order;
  const assertCurrent = () => {
    if (expectedGeneration !== generation || (mutation !== null && mutation !== intent)) {
      throw new Error('Your profile changed. Reload it before trying again.');
    }
  };
  return {
    assertCurrent,
    observe(key: string, revision: string | null) {
      assertCurrent();
      if (!intent && requestOrder < latestObservation) throw new Error('Your profile changed. Reload it before trying again.');
      if (intent || !observed || observed.key !== key || observed.revision !== revision) {
        invalidate(); expectedGeneration = generation;
      }
      observed = { key, revision }; latestObservation = requestOrder;
    },
    finish() { if (intent && mutation === intent) mutation = null; },
  };
}

export type AvatarReadResult = {
  avatar_data_uri: string | null;
  avatar_reupload_required: boolean;
  avatar_error: string | null;
};
const empty = (): AvatarReadResult => ({ avatar_data_uri: null, avatar_reupload_required: false, avatar_error: null });

function base64(bytes: Uint8Array) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let output = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const value = (bytes[i] << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0);
    output += alphabet[value >>> 18] + alphabet[(value >>> 12) & 63]
      + (i + 1 < bytes.length ? alphabet[(value >>> 6) & 63] : '=')
      + (i + 2 < bytes.length ? alphabet[value & 63] : '=');
  }
  return output;
}

async function boundedBody(response: Awaited<ReturnType<typeof streamingFetch>>, limit: number, check: () => void, wait: <T>(work: Promise<T>) => Promise<T>) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error(FAILURE);
  const output = new Uint8Array(limit); let size = 0;
  try {
    while (true) {
      check();
      const { done, value } = await wait(reader.read()); check();
      if (done) break;
      if (!(value instanceof Uint8Array) || value.byteLength === 0 || size + value.byteLength > limit) throw new Error(FAILURE);
      output.set(value, size); size += value.byteLength;
    }
    return output.subarray(0, size);
  } finally { void reader.cancel().catch(() => {}); reader.releaseLock(); }
}

export async function readProfileAvatar(accessToken: string, revision: string | null, assertCurrent: () => void, signal?: AbortSignal): Promise<AvatarReadResult> {
  assertCurrent();
  if (process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED !== 'true' || Platform.OS === 'web') return empty();
  const controller = new AbortController(); requests.add(controller);
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const epoch = getPrivateMediaEpoch();
  const key = getPrivateMediaSessionKey(accessToken, supabaseAuthUrl);
  const backend = getBackendApiUrl();
  const check = () => {
    assertCurrent();
    if (controller.signal.aborted || epoch !== getPrivateMediaEpoch() || !key
        || key !== getActivePrivateMediaSessionKey() || getBackendApiUrl() !== backend) throw new Error(FAILURE);
  };
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancelWait = () => {};
  const deadline = new Promise<never>((_, reject) => {
    cancelWait = () => reject(new Error(FAILURE));
    controller.signal.addEventListener('abort', cancelWait, { once: true });
    timer = setTimeout(() => controller.abort(), 30_000);
  });
  void deadline.catch(() => {});
  const wait = <T>(work: Promise<T>): Promise<T> => Promise.race([work, deadline]);
  try {
    check();
    if (!isCanonicalUuid(revision)) throw new Error(FAILURE);
    const origin = new URL(backend);
    if (origin.protocol !== 'https:' || isLocalOrPrivateHostname(origin.hostname) || origin.username || origin.password || origin.search || origin.hash
        || origin.href.replace(/\/$/, '') !== backend) throw new Error(FAILURE);
    const path = `${backend}/private-media/avatar/${revision}/`;
    const issued = await wait(streamingFetch(path + 'session', {
      method: 'POST', credentials: 'omit', redirect: 'error', signal: controller.signal,
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
      body: JSON.stringify({ transport: 'native', asset_kinds: ['avatar'] }),
    }));
    check();
    if (issued.redirected || issued.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json'
        || !/(?:^|,)\s*private\s*(?:,|$)/i.test(issued.headers.get('cache-control') ?? '')
        || !/(?:^|,)\s*no-store\s*(?:,|$)/i.test(issued.headers.get('cache-control') ?? '')) throw new Error(FAILURE);
    const raw = await boundedBody(issued, 8192, check, wait);
    const value = JSON.parse(new TextDecoder().decode(raw));
    if (issued.status === 409 && value && Object.keys(value).length === 1 && value.detail === LEGACY) {
      return { ...empty(), avatar_reupload_required: true };
    }
    const names = ['resource_kind', 'resource_id', 'urls', 'expires_in', 'expires_at', 'media_grant'];
    const expiry = Date.parse(value?.expires_at);
    const remaining = expiry - Date.now();
    const grant = value?.media_grant;
    if (issued.status !== 200 || issued.redirected || !value || Object.keys(value).length !== names.length
        || names.some((name) => !Object.hasOwn(value, name)) || value.resource_kind !== 'avatar' || value.resource_id !== revision
        || !value.urls || Object.keys(value.urls).length !== 1 || value.urls.avatar !== path + 'avatar'
        || !Number.isInteger(value.expires_in) || value.expires_in < 1 || value.expires_in > 300
        || typeof value.expires_at !== 'string' || value.expires_at.length > 64
        || !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value.expires_at) || !Number.isFinite(expiry)
        || remaining <= 0 || remaining > 300_000 || Math.abs(remaining / 1000 - value.expires_in) > 2
        || typeof grant !== 'string' || !/^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$/.test(grant)) throw new Error(FAILURE);
    check();
    const response = await wait(streamingFetch(path + 'avatar', {
      method: 'GET', credentials: 'omit', redirect: 'error', signal: controller.signal,
      headers: { 'X-Peso-Media-Grant': grant, Accept: 'image/jpeg', 'Cache-Control': 'no-store' },
    }));
    check();
    const length = response.headers.get('content-length');
    if (response.status !== 200 || response.redirected || response.headers.get('content-type')?.toLowerCase() !== 'image/jpeg'
        || !/(?:^|,)\s*private\s*(?:,|$)/i.test(response.headers.get('cache-control') ?? '')
        || !/(?:^|,)\s*no-store\s*(?:,|$)/i.test(response.headers.get('cache-control') ?? '')
        || length === null || !/^[1-9][0-9]{0,5}$/.test(length) || Number(length) > LIMIT) throw new Error(FAILURE);
    const bytes = await boundedBody(response, Math.min(LIMIT, Number(length)), check, wait);
    check();
    if (Date.now() >= expiry || bytes.length !== Number(length) || bytes.length < 4
        || bytes[0] !== 255 || bytes[1] !== 216 || bytes.at(-2) !== 255 || bytes.at(-1) !== 217) throw new Error(FAILURE);
    const avatar_data_uri = 'data:image/jpeg;base64,' + base64(bytes);
    check();
    return { ...empty(), avatar_data_uri };
  } catch {
    assertCurrent();
    if (signal?.aborted) throw new Error('Profile loading was cancelled.');
    if (epoch !== getPrivateMediaEpoch() || key !== getActivePrivateMediaSessionKey()) throw new Error(FAILURE);
    return { ...empty(), avatar_error: FAILURE };
  } finally { clearTimeout(timer); controller.signal.removeEventListener('abort', cancelWait); controller.abort(); signal?.removeEventListener('abort', abort); requests.delete(controller); }
}
