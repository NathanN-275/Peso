import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient, processLock, type Session } from '@supabase/supabase-js';
import { Platform } from 'react-native';
import { getBackendApiUrl, revokeGlobalPrivateMediaSession, revokeReplacementPrivateMediaSession, verifyIncomingPrivateMediaSession } from './backendApi';
import { createMediaLogoutFetch, getPrivateMediaSessionKey } from './privateMediaLogout';
import { releasePrivateMedia, setActivePrivateMediaSessionKey, getActivePrivateMediaSessionKey } from './privateMediaLifecycle';
import { createPrivateMediaSessionController, type PrivateMediaSessionSnapshot } from './privateMediaSession';
import { ensurePrivateExportStartupCleanup } from './privateExportFiles';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabasePublishableKey = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const legacySupabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
const supabaseClientKey = supabasePublishableKey || legacySupabaseAnonKey;
const supabaseConfig =
  supabaseUrl && supabaseClientKey
    ? { url: supabaseUrl, clientKey: supabaseClientKey }
    : null;

if (!supabasePublishableKey && legacySupabaseAnonKey) {
  console.warn(
    'EXPO_PUBLIC_SUPABASE_ANON_KEY is deprecated; migrate this build to EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY.'
  );
}

export const supabaseConfigError =
  supabaseConfig === null
    ? 'Missing Supabase environment variables. Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY.'
    : null;

export const supabaseAuthUrl = supabaseConfig ? `${supabaseConfig.url.replace(/\/$/, '')}/auth/v1` : '';
const privateMediaEnabled = process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED === 'true';
// Keep this off until all media clients, account replacement and deletion flows are accepted.
let acceptedSessions: ReturnType<typeof createPrivateMediaSessionController> | null = null;
const mediaLogout = supabaseConfig ? createMediaLogoutFetch({
  enabled: privateMediaEnabled,
  browserInventoryVersion: Platform.OS === 'web' ? 2 : 1,
  beginGlobalLogout: (token: string, backend: string, action) => {
    if (!acceptedSessions) throw new Error('Secure session coordination is unavailable.');
    return acceptedSessions.beginGlobalLogout(token, backend, action);
  },
  hasPendingGlobalIntent: (token: string, backend: string) => {
    if (!acceptedSessions) throw new Error('Secure session coordination is unavailable.');
    return acceptedSessions.hasPendingGlobalIntent(token, backend);
  },
  completeGlobalLogout: (token: string, backend: string) => {
    if (!acceptedSessions) throw new Error('Secure session coordination is unavailable.');
    return acceptedSessions.completeGlobalLogout(token, backend);
  },
  authUrl: supabaseAuthUrl,
  getBackendUrl: getBackendApiUrl,
  storage: AsyncStorage,
  revokeMedia: revokeGlobalPrivateMediaSession,
  stopMedia: releasePrivateMedia,
  getActiveSessionKey: getActivePrivateMediaSessionKey,
  fetch: (input, init) => fetch(input, init),
}) : null;

const authStorageKey = supabaseConfig ? `sb-${new URL(supabaseConfig.url).hostname.split('.')[0]}-auth-token` : '';
// Resolve the real browser store at use time; failures must reach the transition UI.
const browserSessionStorage = {
  getItem: (key: string) => globalThis.localStorage.getItem(key),
  setItem: (key: string, value: string) => globalThis.localStorage.setItem(key, value),
  removeItem: (key: string) => globalThis.localStorage.removeItem(key),
};
acceptedSessions = supabaseConfig && mediaLogout ? createPrivateMediaSessionController({
  enabled: privateMediaEnabled,
  browserInventoryVersion: Platform.OS === 'web' ? 2 : 1,
  storage: privateMediaEnabled && Platform.OS === 'web' ? browserSessionStorage : AsyncStorage,
  storageKey: authStorageKey,
  authUrl: supabaseAuthUrl,
  getBackendUrl: getBackendApiUrl,
  runExclusive: async <T,>(action: () => Promise<T>): Promise<T> => {
    if (Platform.OS !== 'web') return action();
    const locks = globalThis.navigator?.locks;
    if (!locks?.request) throw new Error('Secure session coordination is unavailable in this browser.');
    return locks.request(`peso:private-media-session:v1:${authStorageKey}`, action);
  },
  stopMedia: releasePrivateMedia,
  onActiveKey: setActivePrivateMediaSessionKey,
  revokeSession: revokeReplacementPrivateMediaSession,
  validateIncomingSession: async (token, backend) => {
    if (privateMediaEnabled) ensurePrivateExportStartupCleanup();
    return verifyIncomingPrivateMediaSession(token, backend);
  },
  getGlobalReceipt: (token: string, backend: string) => mediaLogout.getConfirmedGlobalReceipt(token, backend),
  getAuthMutationKey: () => mediaLogout.getAuthMutationKey(),
  getLogoutIntentKey: () => mediaLogout.getLogoutIntentKey(),
}) : null;

export const supabase =
  supabaseConfig
    ? createClient(supabaseConfig.url, supabaseConfig.clientKey, {
        global: { fetch: mediaLogout?.fetch },
        auth: {
          storage: privateMediaEnabled ? acceptedSessions?.storage : Platform.OS === 'web' ? undefined : AsyncStorage,
          storageKey: authStorageKey,
          autoRefreshToken: true,
          persistSession: true,
          detectSessionInUrl: Platform.OS === 'web',
          flowType: 'pkce',
          lock: Platform.OS === 'web' ? undefined : processLock,
        },
      })
    : null;

if (supabase && mediaLogout) {
  if (privateMediaEnabled) {
    acceptedSessions?.subscribe((snapshot) => {
      if (snapshot.status === 'ready' && !snapshot.session) void mediaLogout.finishLocalSignOut();
    });
  }
  supabase.auth.onAuthStateChange((event, nextSession) => {
    // SDK events are hints; only the controller publishes an accepted media key.
    acceptedSessions?.authStateChanged(event, nextSession);
    if (!privateMediaEnabled) {
      setActivePrivateMediaSessionKey(getPrivateMediaSessionKey(nextSession?.access_token, supabaseAuthUrl));
      mediaLogout.authStateChanged(event, nextSession?.access_token);
    }
  });
}

const unavailableSnapshot: PrivateMediaSessionSnapshot = {
  session: null, event: 'INITIAL_SESSION', status: 'ready', error: null, revision: 0,
};
export function getAcceptedAuthSnapshot() {
  return acceptedSessions?.getSnapshot() ?? unavailableSnapshot;
}
export function subscribeAcceptedAuthSession(listener: (snapshot: PrivateMediaSessionSnapshot) => void) {
  return acceptedSessions?.subscribe(listener) ?? (() => {});
}
let initialization: Promise<void> | null = null;
export function initializeAcceptedAuthSession(): Promise<void> {
  if (!supabase || !acceptedSessions) return Promise.resolve();
  const client = supabase;
  const controller = acceptedSessions;
  if (!initialization) {
    initialization = (async () => {
      // Never call Auth from its event callback or from the storage boundary.
      let rawSession: Session | null = null;
      let readSucceeded = false;
      try {
        const { data, error } = await client.auth.getSession();
        if (!error) { rawSession = data.session; readSucceeded = true; }
      } catch { /* The controller still reads pending durable transition state. */ }
      if (!privateMediaEnabled && readSucceeded) controller.authStateChanged('INITIAL_SESSION', rawSession);
      await controller.initialize();
      if (readSucceeded && rawSession) {
        try { await controller.waitForSession(rawSession); }
        catch {
          // A newer accepted generation can supersede the bootstrap hint.
          if (controller.getSnapshot().status !== 'ready') throw new Error('Session transition is unresolved.');
        }
      }
    })().catch(() => {
      initialization = null;
      throw new Error('Unable to finish your sign-in change. Please retry.');
    });
  }
  return initialization;
}
export async function waitForAcceptedAuthSession(session: Session | null): Promise<Session | null> {
  if (!acceptedSessions) {
    if (session) throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
    return null;
  }
  return acceptedSessions.waitForSession(session);
}
export async function retryAuthSessionTransition() {
  if (!acceptedSessions) throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  if (!privateMediaEnabled) return acceptedSessions.retry();
  try {
    if (!supabase || !mediaLogout) throw new Error('Supabase is not configured.');
    // Capture the unresolved outgoing identity, then release the controller lock before Auth I/O.
    const expectedKey = await acceptedSessions.getTransitionSessionKey();
    const { data, error } = await supabase.auth.getSession();
    if (error) throw new Error('Current session could not be read.');
    const token = data.session?.access_token;
    if (token) {
      const key = getPrivateMediaSessionKey(token, supabaseAuthUrl);
      if (!key) throw new Error('Current session is unavailable.');
      if (expectedKey !== null && key === expectedKey
          && await mediaLogout.hasPendingGlobalLogout(token, getBackendApiUrl())) {
        const { error: logoutError } = await signOutWithPrivateMedia(expectedKey);
        if (logoutError) throw new Error('Global logout remains unconfirmed.');
        return;
      }
    }
    await acceptedSessions.retry();
  } catch {
    throw new Error('Unable to finish your sign-in change. Please retry.');
  }
}

export async function updateUserWithPrivateMedia(
  expectedSessionKey: string | null, attributes: { email?: string; password?: string }
) {
  const client = supabase;
  if (!client || !mediaLogout) throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  if (!privateMediaEnabled) return client.auth.updateUser(attributes);
  const failure = 'Your sign-in session changed. Please retry the account update.';
  const matches = (session: Session | null) => expectedSessionKey !== null
    && getPrivateMediaSessionKey(session?.access_token, supabaseAuthUrl) === expectedSessionKey;
  const before = getAcceptedAuthSnapshot();
  if (before.status !== 'ready' || !matches(before.session)) throw new Error(failure);
  const { data, error } = await client.auth.getSession();
  if (error) throw new Error(failure);
  const accepted = await waitForAcceptedAuthSession(data.session);
  const current = getAcceptedAuthSnapshot();
  if (!matches(accepted) || current.status !== 'ready' || !matches(current.session)) throw new Error(failure);
  // The fetch seam also checks the actual request token after the SDK selects it.
  return mediaLogout.updateUser(expectedSessionKey, () => client.auth.updateUser(attributes));
}

export async function signOutWithPrivateMedia(expectedSessionKey: string | null) {
  const client = supabase;
  if (!client || !mediaLogout) throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  return mediaLogout.signOut(expectedSessionKey, async () => {
    // Also stop media when Auth has already removed its token and sends no request.
    await releasePrivateMedia();
    return client.auth.signOut({ scope: 'global' });
  });
}
