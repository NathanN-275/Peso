const UPDATE_FAILURE = 'Unable to update your account because the sign-in session changed. Please retry.';
const FAILURE = 'Unable to complete sign out. Check your connection and try again.';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const NIL = '00000000-0000-0000-0000-000000000000';
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

// Correlate a local completion checkpoint only. The backend verifies the JWT.
function sessionIdentity(token, issuer) {
  if (typeof token !== 'string' || token.length > 131072) throw new Error(FAILURE);
  const parts = token.split('.');
  if (parts.length !== 3 || parts.some((part) => !/^[A-Za-z0-9_-]+$/.test(part))) throw new Error(FAILURE);
  const payload = parts[1];
  if (payload.length % 4 === 1) throw new Error(FAILURE);
  let bits = 0;
  let value = 0;
  let encoded = '';
  for (const character of payload) {
    value = (value << 6) | ALPHABET.indexOf(character);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      encoded += '%' + ((value >>> bits) & 255).toString(16).padStart(2, '0');
    }
  }
  if (bits && (value & ((1 << bits) - 1))) throw new Error(FAILURE);
  const claims = JSON.parse(decodeURIComponent(encoded));
  if (!claims || claims.iss !== issuer || !UUID.test(claims.sub) || !UUID.test(claims.session_id)
      || claims.sub === NIL || claims.session_id === NIL) throw new Error(FAILURE);
  return { owner: claims.sub, session: claims.session_id };
}

function validReceipt(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === (Object.hasOwn(value, 'cookie_inventory_version')
      ? 'completed_at,cookie_inventory_version,replayed,scope' : 'completed_at,replayed,scope')
    && (!Object.hasOwn(value, 'cookie_inventory_version') || value.cookie_inventory_version === 2)
    && value.scope === 'global' && typeof value.replayed === 'boolean'
    && typeof value.completed_at === 'string' && value.completed_at.length <= 64
    && /^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value.completed_at)
    && Number.isFinite(Date.parse(value.completed_at));
}

function validCookieProgress(value, identity) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const version = Object.hasOwn(value, 'cookie_inventory_version') ? 2 : 1;
  const names = ['scope', 'owner_id', 'session_id', 'completed_at', 'replayed', 'next_cursor', 'cookie_cleanup_complete', ...(version === 2 ? ['cookie_inventory_version'] : [])];
  const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
  const cursor = typeof value.next_cursor === 'string' ? new RegExp(`^(archive|avatar|video):(${uuid})${version === 2 ? `:(${uuid})` : ''}$`).exec(value.next_cursor) : null;
  return Object.keys(value).length === names.length && names.every((name) => Object.hasOwn(value, name))
    && value.scope === 'global' && value.owner_id === identity.owner && value.session_id === identity.session
    && typeof value.replayed === 'boolean' && typeof value.completed_at === 'string' && value.completed_at.length <= 64
    && /^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value.completed_at)
    && Number.isFinite(Date.parse(value.completed_at)) && typeof value.cookie_cleanup_complete === 'boolean'
    && (version !== 2 || value.cookie_inventory_version === 2)
    && (value.next_cursor === null || Boolean(cursor && cursor[2] !== NIL))
    && value.cookie_cleanup_complete === (value.next_cursor === null);
}

function acknowledgedReceipt(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value.provider_acknowledged !== true) return null;
  const { provider_acknowledged, ...receipt } = value;
  return validReceipt(receipt) ? receipt : null;
}

function getPrivateMediaSessionKey(token, issuer) {
  if (!token) return null;
  try {
    const identity = sessionIdentity(token, issuer.replace(/\/$/, ''));
    return identity.owner + ':' + identity.session;
  } catch { return null; }
}

function createMediaLogoutFetch({ enabled, authUrl, getBackendUrl, storage, revokeMedia, stopMedia, getActiveSessionKey, fetch: fetcher, browserInventoryVersion = 1, beginGlobalLogout, completeGlobalLogout, hasPendingGlobalIntent }) {
  if (![1, 2].includes(browserInventoryVersion) || Boolean(beginGlobalLogout) !== Boolean(completeGlobalLogout)) throw new Error(FAILURE);
  const currentReceipt = value => validReceipt(value) && (value.cookie_inventory_version ?? 1) === browserInventoryVersion;
  const readyToClear = new Set();
  let activeSessionKey = null;
  let authMutation = null;
  const activeKey = () => getActiveSessionKey ? getActiveSessionKey() : activeSessionKey;
  let intent;
  let inFlight = null;
  let auth;
  if (enabled) {
    try {
      auth = new URL(authUrl.replace(/\/$/, ''));
      if (auth.protocol !== 'https:' || auth.username || auth.password || auth.search || auth.hash
          || !auth.pathname.endsWith('/auth/v1')) throw new Error(FAILURE);
    } catch { throw new Error(FAILURE); }
  }

  async function mediaFetch(input, init) {
    if (!enabled) return fetcher(input, init);
    let url;
    try {
      url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url);
    } catch {
      return fetcher(input, init);
    }
    const method = (init?.method || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
    if (url.origin === auth.origin && url.pathname === auth.pathname + '/user' && method === 'PUT') {
      const operation = authMutation;
      try {
        const headers = new Headers(init?.headers || (typeof input === 'object' ? input.headers : undefined));
        const authorization = headers.get('authorization');
        if (url.username || url.password || url.search || url.hash || !operation || !authorization
            || !/^Bearer [^\s]+$/.test(authorization)
            || getPrivateMediaSessionKey(authorization.slice(7), authUrl) !== operation.key
            || activeKey() !== operation.key) throw new Error(UPDATE_FAILURE);
        const response = await fetcher(input, init);
        if (authMutation !== operation || activeKey() !== operation.key) throw new Error(UPDATE_FAILURE);
        return response;
      } catch { throw new Error(UPDATE_FAILURE); }
    }
    if (url.origin !== auth.origin || url.pathname !== auth.pathname + '/logout') return fetcher(input, init);
    try {
      const method = init?.method || (typeof input === 'object' && input.method) || 'GET';
      const scopes = url.searchParams.getAll('scope');
      if (method.toUpperCase() !== 'POST' || scopes.length > 1 || (scopes.length && scopes[0] !== 'global')
          || [...url.searchParams.keys()].some((key) => key !== 'scope') || url.username || url.password || url.hash
          ) throw new Error(FAILURE);
      const headers = new Headers(init?.headers || (typeof input === 'object' ? input.headers : undefined));
      const authorization = headers.get('authorization');
      if (!authorization || !/^Bearer [^\s]+$/.test(authorization)) throw new Error(FAILURE);
      const token = authorization.slice(7);
      const identity = sessionIdentity(token, auth.href.replace(/\/$/, ''));
      if (intent !== undefined && intent !== identity.owner + ':' + identity.session) throw new Error(FAILURE);
      const backend = new URL(getBackendUrl());
      if (backend.protocol !== 'https:' || backend.username || backend.password || backend.search || backend.hash) throw new Error(FAILURE);
      const backendUrl = backend.href.replace(/\/$/, '');
      const key = `peso:media-logout:v2:${backendUrl}:${auth.href.replace(/\/$/, '')}:${identity.owner}:${identity.session}`;
      let providerAcknowledged = false;
      let receipt;
      const appPhase = async (globalIntent, retainedProviderReceipt = null) => {
        if (!beginGlobalLogout) await stopMedia();
        if (retainedProviderReceipt !== null && !validReceipt(retainedProviderReceipt)) throw new Error(FAILURE);
        const stored = await storage.getItem(key);
        let retained = retainedProviderReceipt;
        providerAcknowledged = retainedProviderReceipt !== null;
        if (stored !== null) {
          if (stored.length > 8192) throw new Error(FAILURE);
          const value = JSON.parse(stored);
          let storedReceipt = acknowledgedReceipt(value);
          providerAcknowledged = providerAcknowledged || storedReceipt !== null;
          if (!storedReceipt && validReceipt(value)) storedReceipt = value;
          if (!storedReceipt || retained && storedReceipt.completed_at !== retained.completed_at) throw new Error(FAILURE);
          retained = storedReceipt;
        }
        const progressKey = key + ':cookies';
        const rawProgress = await storage.getItem(progressKey);
        let progress = null;
        if (rawProgress !== null) {
          if (rawProgress.length > 8192) throw new Error(FAILURE);
          progress = JSON.parse(rawProgress);
          if (!validCookieProgress(progress, identity)) throw new Error(FAILURE);
        }
        if (retained && currentReceipt(retained) && (!progress || progress.cookie_cleanup_complete
            && (progress.cookie_inventory_version ?? 1) === browserInventoryVersion)) return retained;
        if (progress === null && retained) progress = {
          scope: 'global', owner_id: identity.owner, session_id: identity.session, completed_at: retained.completed_at,
          replayed: retained.replayed, next_cursor: null, cookie_cleanup_complete: true,
          ...(retained.cookie_inventory_version === 2 ? { cookie_inventory_version: 2 } : {}),
        };
        let wroteProgress = rawProgress !== null;
        const next = await revokeMedia(token, backendUrl, { progress, globalIntent, onProgress: async (page) => {
          if (!validCookieProgress(page, identity) || retained && page.completed_at !== retained.completed_at) throw new Error(FAILURE);
          await storage.setItem(progressKey, JSON.stringify(page)); wroteProgress = true;
        } });
        if (!currentReceipt(next) || retained && next.completed_at !== retained.completed_at) throw new Error(FAILURE);
        await storage.setItem(key, JSON.stringify({ ...next, ...(providerAcknowledged ? { provider_acknowledged: true } : {}) }));
        if (wroteProgress) await storage.removeItem(progressKey);
        return next;
      };
      receipt = beginGlobalLogout ? await beginGlobalLogout(token, backendUrl, appPhase) : await appPhase(undefined);
      if (providerAcknowledged) {
        // Repeating a completed global provider operation could revoke a later login.
        if (completeGlobalLogout) await completeGlobalLogout(token, backendUrl);
        readyToClear.add(key);
        return new Response(null, { status: 204 });
      }
      const response = await fetcher(input, init);
      // Persist provider completion before allowing the SDK to remove local credentials.
      if (response.ok || [401, 403, 404].includes(response.status)) {
        await storage.setItem(key, JSON.stringify({ ...receipt, provider_acknowledged: true }));
        if (completeGlobalLogout) await completeGlobalLogout(token, backendUrl);
        readyToClear.add(key);
      }
      return response;
    } catch {
      // Auth's fetch layer logs thrown errors. Never pass token/transport errors through.
      throw new Error(FAILURE);
    }
  }

  async function finishLocalSignOut() {
    // Call only after the SDK's SIGNED_OUT event confirms local session removal.
    const results = await Promise.allSettled([...readyToClear].map(async (key) => {
      await storage.removeItem(key);
      readyToClear.delete(key);
    }));
    // shortcut: crash-orphaned receipts need bounded cleanup before media rollout.
    // Cleanup failure retains noncredential confirmation, not access to media.
    return results.every((result) => result.status === 'fulfilled');
  }

  function signOut(expectedSessionKey, action) {
    if (inFlight) {
      return inFlight.key === expectedSessionKey ? inFlight.promise : Promise.reject(new Error(FAILURE));
    }
    intent = expectedSessionKey;
    const operation = { key: expectedSessionKey, promise: null };
    operation.promise = Promise.resolve().then(action).finally(() => {
      if (inFlight === operation) { inFlight = null; intent = undefined; }
    });
    inFlight = operation;
    return operation.promise;
  }

  function updateUser(expectedSessionKey, action) {
    if (!enabled) return Promise.resolve().then(action);
    if (authMutation || typeof expectedSessionKey !== 'string' || activeKey() !== expectedSessionKey
        || expectedSessionKey.split(':').length !== 2
        || expectedSessionKey.split(':').some((part) => !UUID.test(part) || part === NIL)) {
      return Promise.reject(new Error(UPDATE_FAILURE));
    }
    const operation = { key: expectedSessionKey };
    authMutation = operation;
    return Promise.resolve().then(action).finally(() => {
      if (authMutation === operation) authMutation = null;
    });
  }

  function getAuthMutationKey() { return authMutation?.key ?? null; }
  function getLogoutIntentKey() { return inFlight?.key; }

  async function getConfirmedGlobalReceipt(token, backendUrl) {
    if (!enabled) return null;
    try {
      const identity = sessionIdentity(token, authUrl.replace(/\/$/, ''));
      const actual = new URL(getBackendUrl()).href.replace(/\/$/, '');
      if (actual !== backendUrl) throw new Error(FAILURE);
      const key = `peso:media-logout:v2:${backendUrl}:${authUrl.replace(/\/$/, '')}:${identity.owner}:${identity.session}`;
      const stored = await storage.getItem(key);
      const receipt = stored === null ? null : JSON.parse(stored);
      const acknowledged = acknowledgedReceipt(receipt);
      return currentReceipt(acknowledged) ? acknowledged : null;
    } catch { throw new Error(FAILURE); }
  }

  async function hasPendingGlobalLogout(token, backendUrl) {
    if (!enabled) return false;
    if (hasPendingGlobalIntent && await hasPendingGlobalIntent(token, backendUrl)) return true;
    try {
      const identity = sessionIdentity(token, authUrl.replace(/\/$/, ''));
      const actual = new URL(getBackendUrl()).href.replace(/\/$/, '');
      if (actual !== backendUrl) throw new Error(FAILURE);
      const key = `peso:media-logout:v2:${backendUrl}:${authUrl.replace(/\/$/, '')}:${identity.owner}:${identity.session}`;
      const stored = await storage.getItem(key);
      if (stored !== null) {
        if (stored.length > 8192) throw new Error(FAILURE);
        const value = JSON.parse(stored);
        if (acknowledgedReceipt(value)) return !currentReceipt(acknowledgedReceipt(value));
        if (validReceipt(value)) return true;
        throw new Error(FAILURE);
      }
      const rawProgress = await storage.getItem(key + ':cookies');
      if (rawProgress === null) return false;
      if (rawProgress.length > 8192) throw new Error(FAILURE);
      return validCookieProgress(JSON.parse(rawProgress), identity);
    } catch { throw new Error(FAILURE); }
  }

  function authStateChanged(event, token) {
    const nextKey = getPrivateMediaSessionKey(token, authUrl);
    const changed = activeSessionKey !== null && activeSessionKey !== nextKey;
    activeSessionKey = nextKey;
    if (event === 'SIGNED_OUT' || changed) {
      void stopMedia().catch(() => { console.error('Unable to release private media after an auth change.'); });
    }
    if (event === 'SIGNED_OUT') void finishLocalSignOut();
  }

  return { fetch: mediaFetch, finishLocalSignOut, signOut, authStateChanged, getConfirmedGlobalReceipt, updateUser, getAuthMutationKey, getLogoutIntentKey, hasPendingGlobalLogout };
}

module.exports = { createMediaLogoutFetch, getPrivateMediaSessionKey };
