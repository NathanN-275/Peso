const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createMediaLogoutFetch, getPrivateMediaSessionKey } = require('../lib/privateMediaLogout');
const { registerPrivateMediaRelease, releasePrivateMedia, getPrivateMediaEpoch,
  releaseBrowserMedia, releaseNativeMedia, setActivePrivateMediaSessionKey, registerNativePrivateMedia } = require('../lib/privateMediaLifecycle');

const OWNER = '00000000-0000-0000-0000-000000000001';
const SID = '00000000-0000-0000-0000-000000000002';
const SID2 = '00000000-0000-0000-0000-000000000003';
const AUTH = 'https://auth-fixture.invalid/auth/v1';
const BACKEND = 'https://api.usepeso.com';
const RECEIPT = { scope: 'global', completed_at: '2026-10-26T19:00:00+00:00', replayed: false };
function jwt(changes = {}) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({ iss: AUTH, sub: OWNER, session_id: SID,
    exp: Math.floor(Date.now() / 1000) + 3600, aud: 'authenticated', role: 'authenticated', ...changes })}.c3ludGhldGlj`;
}
function fixture(options = {}) {
  const events = [];
  const values = options.values || new Map();
  const storage = {
    async getItem(key) { events.push('read'); return values.get(key) ?? null; },
    async setItem(key, value) { events.push('persist'); values.set(key, value); },
    async removeItem(key) { events.push('remove'); values.delete(key); },
  };
  const tokens = [];
  const backendUrls = [];
  const requests = [];
  const config = { enabled: true, authUrl: AUTH, getBackendUrl: () => BACKEND, storage,
    async stopMedia() { events.push('stop'); },
    async revokeMedia(token, backendUrl) { events.push('revoke'); tokens.push(token); backendUrls.push(backendUrl); return { ...RECEIPT }; },
    async fetch(input, init) { events.push('provider'); requests.push([input, init]); return new Response(null, { status: 200 }); },
    ...options.config };
  const transport = createMediaLogoutFetch(config);
  const logout = (token = jwt(), url = AUTH + '/logout?scope=global', init = {}) => transport.fetch(url, {
    method: 'POST', headers: { Authorization: 'Bearer ' + token }, ...init,
  });
  return { ...transport, logout, events, values, storage, config, tokens, backendUrls, requests };
}

function actualBackendApi({ platform = 'web', fetcher, backend = BACKEND, timers = {}, enabled = true } = {}) {
  const typescript = require('typescript');
  const filename = path.join(__dirname, '../lib/backendApi.ts');
  const code = typescript.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: typescript.ModuleKind.CommonJS, target: typescript.ScriptTarget.ES2022 },
  }).outputText;
  const calls = [];
  const module = { exports: {} };
  const request = fetcher || (async (url, init) => { calls.push([url, init]); return Response.json({ ...RECEIPT, owner_id: OWNER, session_id: SID, next_cursor: null, cookie_cleanup_complete: true, ...(platform === 'web' ? { cookie_inventory_version: 2 } : {}) }); });
  const load = (name) => {
    if (name === 'react-native') return { Platform: { OS: platform } };
    if (name === './backendConfig') return { getBackendApiUrl: () => typeof backend === 'function' ? backend() : backend,
      resolveBackendApiConfig: () => ({ url: backend, source: 'env override' }), getBackendConnectionDiagnostics: () => ({ url: backend }) };
    return require(name.startsWith('.') ? path.resolve(path.dirname(filename), name) : name);
  };
  const wrapper = vm.runInNewContext(`(function(exports, require, module) {${code}\n})`, {
    __DEV__: false, process: { env: { EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: String(enabled), EXPO_PUBLIC_SUPABASE_URL: 'https://auth-fixture.invalid' } },
    URL, URLSearchParams, AbortController, setTimeout: timers.setTimeout ?? setTimeout, clearTimeout: timers.clearTimeout ?? clearTimeout, console: { info() {}, warn() {}, error() {} }, fetch: request,
  }, { filename });
  wrapper(module.exports, load, module);
  setActivePrivateMediaSessionKey(OWNER + ':' + SID);
  return { api: module.exports, calls };
}

test('actual API logout adapter binds backend, transport and the captured account token', async () => {
  for (const platform of ['web', 'ios']) {
    const f = actualBackendApi({ platform }); const token = jwt();
    await f.api.revokeGlobalPrivateMediaSession(token, BACKEND);
    const [url, init] = f.calls[0];
    assert.equal(url, BACKEND + (platform === 'web' ? '/private-media/v2/logout' : '/private-media/logout')); assert.equal(init.headers.Authorization, 'Bearer ' + token);
    assert.equal(init.credentials, platform === 'web' ? 'include' : 'omit');
    assert.deepEqual(JSON.parse(init.body), { transport: platform === 'web' ? 'browser' : 'native' });
  }
  setActivePrivateMediaSessionKey(null);
});

test('actual API refuses backend drift and an old token after account replacement before fetch', async () => {
  const f = actualBackendApi();
  await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), 'https://other.invalid'), /Unable to confirm the previous media session ended/);
  setActivePrivateMediaSessionKey(OWNER + ':' + SID2);
  await assert.rejects(f.api.getSavedVideos(jwt()), /sign-in session changed/);
  assert.equal(f.calls.length, 0); setActivePrivateMediaSessionKey(null);
});

test('legacy playback response is rejected after logout and cannot repopulate cache', async () => {
  let finish; let started; let calls = 0;
  const entered = new Promise((resolve) => { started = resolve; });
  const f = actualBackendApi({ enabled: false, fetcher: async () => {
    calls += 1;
    if (calls === 1) { started(); return new Promise((resolve) => { finish = resolve; }); }
    return Response.json({ video_id: SID2, video_url: 'https://synthetic.invalid/new', expires_in: 120 });
  } });
  const pending = f.api.getVideoPlaybackUrl(SID2, jwt()); await entered; await releasePrivateMedia();
  finish(Response.json({ video_id: SID2, video_url: 'https://synthetic.invalid/old', expires_in: 120 }));
  await assert.rejects(pending, /sign-in session changed/);
  assert.equal((await f.api.getVideoPlaybackUrl(SID2, jwt())).video_url, 'https://synthetic.invalid/new');
  assert.equal(calls, 2); setActivePrivateMediaSessionKey(null);
});

test('actual playback cache clears when media lifecycle releases', async () => {
  let calls = 0;
  const f = actualBackendApi({ enabled: false, fetcher: async () => {
    calls += 1; return Response.json({ video_id: SID2, video_url: 'https://synthetic.invalid/video', expires_in: 120 });
  } });
  const token = jwt(); await f.api.getVideoPlaybackUrl(SID2, token); await f.api.getVideoPlaybackUrl(SID2, token);
  assert.equal(calls, 1); await releasePrivateMedia(); await f.api.getVideoPlaybackUrl(SID2, token);
  assert.equal(calls, 2); setActivePrivateMediaSessionKey(null);
});

test('app receipt is persisted before the exact provider request and cleared only after local completion', async () => {
  const f = fixture(); const token = jwt();
  const response = await f.logout(token);
  assert.equal(response.status, 200);
  assert.deepEqual(f.events, ['stop', 'read', 'read', 'revoke', 'persist', 'provider', 'persist']);
  assert.deepEqual(f.tokens, [token]); assert.deepEqual(f.backendUrls, [BACKEND]);
  assert.equal(f.requests[0][1].headers.Authorization, 'Bearer ' + token);
  assert.equal(f.values.size, 1);
  assert.equal(await f.finishLocalSignOut(), true); assert.equal(f.values.size, 0);
});

test('checkpoint persists no access/refresh/media token or raw JWT claims', async () => {
  const f = fixture(); const token = jwt({ email: 'synthetic-private@example.invalid', user_metadata: { name: '😀' } });
  await f.logout(token);
  const serialized = JSON.stringify([...f.values]);
  assert.ok(!serialized.includes(token)); assert.ok(!serialized.includes('synthetic-private@'));
  assert.ok(!serialized.includes('refresh_token')); assert.ok(!serialized.includes('media_grant'));
  assert.deepEqual(JSON.parse([...f.values.values()][0]), { ...RECEIPT, provider_acknowledged: true });
});

test('app revocation failure prevents provider logout and stores no false confirmation', async () => {
  const f = fixture({ config: { async revokeMedia() { throw new Error('synthetic-secret-raw-token'); } } });
  await assert.rejects(f.logout(), (error) => !error.message.includes('synthetic-secret') && !error.cause);
  assert.equal(f.values.size, 0); assert.equal(f.requests.length, 0);
});

test('persistent write failure after app commit prevents provider request', async () => {
  const f = fixture(); f.storage.setItem = async () => { throw new Error('synthetic-storage-secret'); };
  await assert.rejects(f.logout(), /Unable to complete sign out/);
  assert.deepEqual(f.events, ['stop', 'read', 'read', 'revoke']); assert.equal(f.requests.length, 0);
});

test('persistent read failure fails closed before app or provider calls', async () => {
  const f = fixture(); f.storage.getItem = async () => { throw new Error('synthetic-secret'); };
  await assert.rejects(f.logout(), /Unable to complete sign out/);
  assert.equal(f.tokens.length, 0); assert.equal(f.requests.length, 0);
});

test('lost provider response can retry after reload without another authenticated app call', async () => {
  const values = new Map();
  const first = fixture({ values, config: { async fetch() { throw new Error('synthetic-request-with-bearer-secret'); } } });
  await assert.rejects(first.logout(), /Unable to complete sign out/); assert.equal(values.size, 1);
  const second = fixture({ values, config: {
    async revokeMedia() { throw new Error('Provider now rejects getUser; app receipt must be reused.'); },
    async fetch() { return new Response('{}', { status: 401 }); },
  } });
  assert.equal((await second.logout()).status, 401);
  assert.deepEqual(second.events, ['stop', 'read', 'read', 'persist']);
  await second.finishLocalSignOut(); assert.equal(values.size, 0);
});

test('refreshed access token with same issuer/owner/session reuses committed app receipt', async () => {
  const f = fixture(); await f.logout(jwt()); await f.logout(jwt({ exp: 2000000000 }));
  assert.equal(f.tokens.length, 1); assert.equal(f.requests.length, 1);
});

test('new login never reuses an older session confirmation', async () => {
  const f = fixture(); await f.logout(); await f.logout(jwt({ session_id: SID2 }));
  assert.equal(f.tokens.length, 2); assert.equal(f.values.size, 2);
});

test('other owner and backend deployment do not reuse a confirmation', async () => {
  let backend = BACKEND;
  const f = fixture({ config: { getBackendUrl: () => backend } });
  await f.logout(); await f.logout(jwt({ sub: SID2 })); backend = 'https://api-staging.usepeso.com'; await f.logout();
  assert.equal(f.tokens.length, 3); assert.equal(f.values.size, 3);
});

test('provider 5xx retains receipt and is not mistaken for local completion', async () => {
  const f = fixture({ config: { async fetch() { return new Response('{}', { status: 503 }); } } });
  assert.equal((await f.logout()).status, 503); await f.finishLocalSignOut(); assert.equal(f.values.size, 1);
});

test('provider 401/403/404 are returned to SDK and retain proof until SDK local removal', async () => {
  for (const status of [401, 403, 404]) {
    const f = fixture({ config: { async fetch() { return new Response('{}', { status }); } } });
    assert.equal((await f.logout()).status, status); assert.equal(f.values.size, 1);
    await f.finishLocalSignOut(); assert.equal(f.values.size, 0);
  }
});

test('receipt cleanup failure does not erase confirmation and can retry', async () => {
  const f = fixture(); await f.logout();
  const remove = f.storage.removeItem; f.storage.removeItem = async () => { throw new Error('synthetic'); };
  assert.equal(await f.finishLocalSignOut(), false); assert.equal(f.values.size, 1);
  f.storage.removeItem = remove; assert.equal(await f.finishLocalSignOut(), true); assert.equal(f.values.size, 0);
});

test('corrupt local checkpoint cannot erase a potentially acknowledged provider operation', async () => {
  const f = fixture(); await f.logout(); const key = [...f.values.keys()][0]; f.values.set(key, '{broken');
  await assert.rejects(f.logout(), /Unable to complete/); assert.equal(f.tokens.length, 1); assert.equal(f.requests.length, 1); assert.equal(f.values.get(key), '{broken');
});

test('malformed/extra-field server receipts never persist or permit provider logout', async () => {
  for (const receipt of [null, {}, { ...RECEIPT, replayed: 1 }, { ...RECEIPT, scope: 'local' },
    { ...RECEIPT, completed_at: 'yesterday' }, { ...RECEIPT, access_token: 'synthetic-secret' }]) {
    const f = fixture({ config: { async revokeMedia() { return receipt; } } });
    await assert.rejects(f.logout(), /Unable to complete sign out/);
    assert.equal(f.values.size, 0); assert.equal(f.requests.length, 0);
  }
});

test('wrong project, nil/noncanonical/malformed identity never reaches app or provider', async () => {
  for (const changes of [{ iss: 'https://other.invalid/auth/v1' }, { sub: 'invalid' }, { session_id: null },
    { session_id: '00000000-0000-0000-0000-000000000000' }, { sub: '00000000-0000-0000-0000-00000000000A' }]) {
    const f = fixture(); await assert.rejects(f.logout(jwt(changes)), /Unable to complete sign out/);
    assert.equal(f.tokens.length, 0); assert.equal(f.requests.length, 0);
  }
});

test('malformed JWT and bearer framing fail closed with generic errors', async () => {
  for (const token of ['', 'invalid', 'a.b.c', 'a.A.c', 'a._w.c', 'A'.repeat(131073)]) {
    const f = fixture(); await assert.rejects(f.logout(token), /Unable to complete sign out/);
    assert.equal(f.requests.length, 0);
  }
  const f = fixture(); await assert.rejects(f.logout(jwt(), undefined, { headers: {} }), /Unable to complete sign out/);
});

test('global/default scope is explicit; local/others/duplicate/extra query and wrong methods deny', async () => {
  const allowed = fixture(); await allowed.logout(jwt(), AUTH + '/logout'); assert.equal(allowed.tokens.length, 1);
  for (const suffix of ['?scope=local', '?scope=others', '?scope=global&scope=global', '?scope=global&x=y', '#fragment']) {
    const f = fixture(); await assert.rejects(f.logout(jwt(), AUTH + '/logout' + suffix), /Unable to complete sign out/);
    assert.equal(f.requests.length, 0);
  }
  const f = fixture(); await assert.rejects(f.logout(jwt(), undefined, { method: 'GET' }), /Unable to complete sign out/);
});

test('feature off preserves provider fetch without touching backend or storage', async () => {
  const f = fixture({ config: { enabled: false, authUrl: 'invalid' } }); await f.logout('not-a-jwt');
  assert.deepEqual(f.events, ['provider']);
});

test('other endpoints and hosts pass through without revocation', async () => {
  for (const url of [AUTH + '/token', 'https://unrelated.invalid/auth/v1/logout', AUTH + '/logout-other']) {
    const f = fixture(); await f.fetch(url, { method: 'POST' }); assert.deepEqual(f.events, ['provider']);
  }
});

test('invalid enabled auth/backend configuration cannot bypass app revocation', async () => {
  for (const authUrl of ['invalid', 'http://auth-fixture.invalid/auth/v1', AUTH + '?token=secret', 'https://u:p@auth-fixture.invalid/auth/v1']) {
    assert.throws(() => fixture({ config: { authUrl } }), /Unable to complete sign out/);
  }
  for (const backend of ['http://api.usepeso.com', BACKEND + '?token=secret', 'https://u:p@api.usepeso.com']) {
    const f = fixture({ config: { getBackendUrl: () => backend } });
    await assert.rejects(f.logout(), /Unable to complete sign out/); assert.equal(f.requests.length, 0);
  }
});

test('Request input is supported without changing the request passed to provider', async () => {
  const f = fixture(); const request = new Request(AUTH + '/logout?scope=global', {
    method: 'POST', headers: { Authorization: 'Bearer ' + jwt() }, body: '{}',
  });
  await f.fetch(request); assert.equal(f.requests[0][0], request); assert.equal(await request.text(), '{}');
});

test('all registered media releases run synchronously and settle before confirmation', async () => {
  const events = []; let finish;
  const removeA = registerPrivateMediaRelease(() => { events.push('pause'); return new Promise((resolve) => { finish = resolve; }); });
  const removeB = registerPrivateMediaRelease(() => { events.push('clear-cache'); });
  try {
    const pending = releasePrivateMedia(); assert.deepEqual(events, ['pause', 'clear-cache']);
    let done = false; pending.then(() => { done = true; }); await Promise.resolve(); assert.equal(done, false);
    finish(); await pending;
  } finally { removeA(); removeB(); }
});

test('one failing media release still stops other media and blocks provider sign-out', async () => {
  const events = [];
  const removeA = registerPrivateMediaRelease(() => { throw new Error('synthetic-private-secret'); });
  const removeB = registerPrivateMediaRelease(() => { events.push('stopped'); });
  try {
    const f = fixture({ config: { stopMedia: releasePrivateMedia } }); await assert.rejects(f.logout(), /Unable to complete sign out/);
    assert.deepEqual(events, ['stopped']); assert.equal(f.tokens.length, 0); assert.equal(f.requests.length, 0);
  } finally { removeA(); removeB(); }
});

test('unregistered/unmounted media no longer participates in logout', async () => {
  let calls = 0; const remove = registerPrivateMediaRelease(() => { calls += 1; }); remove(); remove();
  await releasePrivateMedia(); assert.equal(calls, 0);
});

test('same-session double clicks share one operation; another session cannot inherit its success', async () => {
  const f = fixture(); let release;
  const wait = new Promise((resolve) => { release = resolve; });
  const action = async () => { await wait; return f.logout(); };
  const first = f.signOut(OWNER + ':' + SID, action);
  assert.equal(f.signOut(OWNER + ':' + SID, action), first);
  await assert.rejects(f.signOut(OWNER + ':' + SID2, action), /Unable to complete sign out/);
  release(); await first; assert.equal(f.requests.length, 1);
});

test('a changed provider token cannot perform logout under a stale UI session intent', async () => {
  const f = fixture();
  await assert.rejects(f.signOut(OWNER + ':' + SID, () => f.logout(jwt({ session_id: SID2 }))), /Unable to complete sign out/);
  assert.equal(f.tokens.length, 0); assert.equal(f.requests.length, 0);
  await f.signOut(OWNER + ':' + SID2, () => f.logout(jwt({ session_id: SID2 })));
  assert.equal(f.requests.length, 1);
});

test('auth changes release media for replaced sessions and sign-out, while refresh/focus preserve it', async () => {
  const f = fixture(); f.authStateChanged('INITIAL_SESSION', jwt());
  f.authStateChanged('TOKEN_REFRESHED', jwt({ exp: 2000000000 })); f.authStateChanged('SIGNED_IN', jwt());
  assert.deepEqual(f.events, []);
  f.authStateChanged('SIGNED_IN', jwt({ session_id: SID2 })); assert.deepEqual(f.events, ['stop']);
  f.authStateChanged('SIGNED_OUT'); assert.deepEqual(f.events, ['stop', 'stop']);
});

test('UI session key correlates owner/session without trusting it as authentication', () => {
  assert.equal(getPrivateMediaSessionKey(jwt(), AUTH), OWNER + ':' + SID);
  assert.equal(getPrivateMediaSessionKey(jwt({ exp: 0 }), AUTH), OWNER + ':' + SID);
  assert.equal(getPrivateMediaSessionKey(jwt({ iss: 'https://other.invalid/auth/v1' }), AUTH), null);
  assert.equal(getPrivateMediaSessionKey(undefined, AUTH), null);
});

test('lifecycle epoch changes synchronously to fence late private responses', async () => {
  const epoch = getPrivateMediaEpoch(); const pending = releasePrivateMedia();
  assert.equal(getPrivateMediaEpoch(), epoch + 1); await pending;
});

test('browser adapter clears video/poster sources before reloading the element', () => {
  const attributes = new Map([['src', 'https://synthetic.invalid/video'], ['poster', 'https://synthetic.invalid/poster']]);
  const events = [];
  releaseBrowserMedia({ pause() { events.push('pause'); }, removeAttribute(name) { attributes.delete(name); },
    load() { assert.equal(attributes.size, 0); events.push('load'); } });
  assert.deepEqual(events, ['pause', 'load']); releaseBrowserMedia(null);
});

test('native adapter pauses and awaits source replacement instead of releasing a hook-owned player', async () => {
  const events = []; let finish;
  const pending = releaseNativeMedia({ pause() { events.push('pause'); },
    replaceAsync(source) { assert.equal(source, null); return new Promise((resolve) => { finish = resolve; }); } });
  assert.deepEqual(events, ['pause']); let done = false; pending.then(() => { done = true; });
  await Promise.resolve(); assert.equal(done, false); finish(); await pending;
});

test('browser release attempts every source-removal step after any individual failure', () => {
  for (const failure of ['pause', 'src', 'poster', 'load']) {
    const events = [];
    const step = (name) => { events.push(name); if (name === failure) throw new Error('synthetic-private-secret'); };
    assert.throws(() => releaseBrowserMedia({ pause() { step('pause'); },
      removeAttribute(name) { step(name); }, load() { step('load'); } }),
    (error) => error.message === 'Unable to release private media. Please try signing out again.' && !error.cause);
    assert.deepEqual(events, ['pause', 'src', 'poster', 'load']);
  }
});

test('native pause failure still awaits source removal and returns a sanitized failure', async () => {
  let finish;
  const pending = releaseNativeMedia({ pause() { throw new Error('synthetic-native-secret'); },
    replaceAsync(source) { assert.equal(source, null); return new Promise((resolve) => { finish = resolve; }); } });
  const rejected = assert.rejects(pending,
    (error) => error.message === 'Unable to release private media. Please try signing out again.' && !error.cause);
  assert.equal(typeof finish, 'function');
  let settled = false; pending.then(() => { settled = true; }, () => { settled = true; });
  await Promise.resolve(); assert.equal(settled, false);
  finish(); await rejected;
});

test('native source-removal failures remain sanitized even when pause also fails', async () => {
  for (const pauseFails of [false, true]) {
    let replacements = 0;
    await assert.rejects(releaseNativeMedia({ pause() { if (pauseFails) throw new Error('synthetic-pause-secret'); },
      async replaceAsync() { replacements += 1; throw new Error('synthetic-source-secret'); } }),
    (error) => error.message === 'Unable to release private media. Please try signing out again.' && !error.cause);
    assert.equal(replacements, 1);
  }
});

test('failed browser pause removes sources but blocks logout until the complete release succeeds', async () => {
  const attributes = new Map([['src', 'synthetic-video'], ['poster', 'synthetic-poster']]);
  let failPause = true; let loads = 0;
  const unregister = registerPrivateMediaRelease(() => releaseBrowserMedia({
    pause() { if (failPause) throw new Error('synthetic-player-secret'); },
    removeAttribute(name) { attributes.delete(name); }, load() { loads += 1; },
  }));
  try {
    const f = fixture({ config: { stopMedia: releasePrivateMedia } });
    await assert.rejects(f.logout(), /Unable to complete sign out/);
    assert.equal(attributes.size, 0); assert.equal(loads, 1);
    assert.equal(f.tokens.length, 0); assert.equal(f.requests.length, 0); assert.equal(f.values.size, 0);
    failPause = false;
    assert.equal((await f.logout()).status, 200); assert.equal(loads, 2);
    assert.equal(f.tokens.length, 1); assert.equal(f.requests.length, 1);
  } finally { unregister(); }
});

test('native hook disposal during pending source replacement does not produce a false logout failure', async () => {
  let fail; let calls = 0;
  const unmount = registerNativePrivateMedia({ pause() { calls += 1; },
    replaceAsync() { return new Promise((resolve, reject) => { fail = reject; }); } });
  const pending = releasePrivateMedia(); assert.equal(calls, 1);
  unmount(); fail(new Error('Synthetic object already disposed by hook')); await pending;
  await releasePrivateMedia(); assert.equal(calls, 1);
});

test('native replacement failure while still mounted remains a blocking release error', async () => {
  const unmount = registerNativePrivateMedia({ pause() {}, async replaceAsync() { throw new Error('synthetic-native-secret'); } });
  try { await assert.rejects(releasePrivateMedia(), /Unable to release private media/); }
  finally { unmount(); }
});

test('real installed Auth SDK serializes logout and a later account session under its process lock', async () => {
  const { createClient, processLock } = require('@supabase/supabase-js');
  const authValues = new Map(); const receipts = new Map(); const events = []; let releaseRevoke; let entered;
  const inRevoke = new Promise((resolve) => { entered = resolve; });
  const revokeWait = new Promise((resolve) => { releaseRevoke = resolve; });
  const storage = { async getItem(key) { return authValues.get(key) ?? null; },
    async setItem(key, value) { authValues.set(key, value); }, async removeItem(key) { authValues.delete(key); } };
  const receiptStorage = { async getItem(key) { return receipts.get(key) ?? null; },
    async setItem(key, value) { receipts.set(key, value); }, async removeItem(key) { receipts.delete(key); } };
  const tokenA = jwt(); const tokenB = jwt({ sub: SID2, session_id: SID2 });
  const transport = createMediaLogoutFetch({ enabled: true, authUrl: AUTH, getBackendUrl: () => BACKEND, storage: receiptStorage,
    async stopMedia() { events.push('stop'); }, async revokeMedia(token) {
      assert.equal(token, tokenA); events.push('app'); entered(); await revokeWait; return RECEIPT;
    }, async fetch(input, init) {
      const url = new URL(input); const token = new Headers(init.headers).get('authorization').slice(7);
      if (url.pathname.endsWith('/user')) return Response.json({ id: token === tokenA ? OWNER : SID2, aud: 'authenticated' });
      if (url.pathname.endsWith('/logout')) { assert.equal(token, tokenA); events.push('provider'); return new Response(null, { status: 204 }); }
      throw new Error('Unexpected fixture request');
    } });
  const client = createClient('https://auth-fixture.invalid', 'synthetic-public-key', {
    auth: { storage, storageKey: 'synthetic-lock-test', persistSession: true, autoRefreshToken: false, detectSessionInUrl: false, lock: processLock },
    global: { fetch: transport.fetch },
  });
  const subscription = client.auth.onAuthStateChange((event, session) => {
    transport.authStateChanged(event, session?.access_token);
  }).data.subscription;
  try {
    assert.equal((await client.auth.setSession({ access_token: tokenA, refresh_token: 'synthetic-refresh-A' })).error, null);
    const logout = transport.signOut(OWNER + ':' + SID, async () => {
      await releasePrivateMedia();
      return client.auth.signOut();
    }); await inRevoke;
    let switched = false;
    const switchAccount = client.auth.setSession({ access_token: tokenB, refresh_token: 'synthetic-refresh-B' }).then((result) => { switched = true; return result; });
    await new Promise((resolve) => setImmediate(resolve)); assert.equal(switched, false);
    releaseRevoke(); assert.equal((await logout).error, null); assert.equal((await switchAccount).error, null);
    assert.equal((await client.auth.getSession()).data.session.user.id, SID2);
    assert.deepEqual(events, ['stop', 'app', 'provider', 'stop']);
    assert.equal(receipts.size, 0);
    const logged = []; const previousError = console.error;
    try {
      console.error = (...args) => { logged.push(args); };
      const stale = await transport.signOut(OWNER + ':' + SID, () => client.auth.signOut());
      assert.ok(stale.error);
      assert.equal((await client.auth.getSession()).data.session.user.id, SID2);
      assert.deepEqual(events, ['stop', 'app', 'provider', 'stop']);
      assert.ok(!JSON.stringify(logged).includes(tokenA)); assert.ok(!JSON.stringify(logged).includes(tokenB));
    } finally { console.error = previousError; }
  } finally { releaseRevoke(); subscription.unsubscribe(); await client.auth.stopAutoRefresh(); }
});

const localPage = (changes = {}) => ({ scope: 'local', owner_id: OWNER, session_id: SID,
  completed_at: RECEIPT.completed_at, replayed: false, next_cursor: null, cookie_cleanup_complete: true, cookie_inventory_version: 2, ...changes });

test('captured outgoing revocation is a dedicated fixed endpoint while ordinary stale requests stay denied', async () => {
  const calls = [];
  const f = actualBackendApi({ fetcher: async (url, init) => { calls.push([url, init]); return Response.json(localPage()); } });
  setActivePrivateMediaSessionKey(null);
  const receipt = await f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND);
  assert.equal(receipt.scope, 'local'); assert.equal(calls.length, 1);
  assert.equal(calls[0][0], BACKEND + '/private-media/v2/session-replacement');
  assert.deepEqual(JSON.parse(calls[0][1].body), { transport: 'browser' });
  assert.equal(calls[0][1].credentials, 'include'); assert.equal(calls[0][1].redirect, 'error');
  assert.equal(calls[0][1].headers.Authorization, 'Bearer ' + jwt());
  await assert.rejects(f.api.getSavedVideos(jwt()), /sign-in session changed/);
  await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND), /Unable to confirm/);
  assert.equal(calls.length, 1);
});

test('cookie pagination waits for durable progress before any next page and persists no bearer', async () => {
  const calls = []; let entered; let resume;
  const writing = new Promise((resolve) => { entered = resolve; });
  const durable = new Promise((resolve) => { resume = resolve; });
  const cursor = 'video:' + SID2 + ':' + SID;
  const f = actualBackendApi({ fetcher: async (url, init) => {
    calls.push([url, init]); return Response.json(localPage(calls.length === 1
      ? { next_cursor: cursor, cookie_cleanup_complete: false } : { replayed: true }));
  } });
  let progress;
  const operation = f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, {
    onProgress: async (page) => { progress = page; entered(); await durable; },
  });
  await writing; assert.equal(calls.length, 1); assert.ok(!JSON.stringify(progress).includes(jwt()));
  resume(); const receipt = await operation; assert.equal(receipt.cookie_cleanup_complete, true);
  assert.deepEqual(JSON.parse(calls[1][1].body), { transport: 'browser', cursor });
  setActivePrivateMediaSessionKey(null);
});

test('lost page reply retains resumable progress and retries the same exact session cursor', async () => {
  let progress; const bodies = []; const cursor = 'archive:' + SID2 + ':' + SID;
  const first = actualBackendApi({ fetcher: async (_url, init) => {
    bodies.push(JSON.parse(init.body));
    if (bodies.length === 2) throw new Error('synthetic bearer and provider-secret');
    return Response.json(localPage({ next_cursor: cursor, cookie_cleanup_complete: false }));
  } });
  await assert.rejects(first.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND,
    { onProgress: async (page) => { progress = page; } }), (error) => error.message.startsWith('Unable to confirm') && !error.cause);
  assert.equal(progress.next_cursor, cursor); assert.equal(bodies.length, 2);
  const retry = actualBackendApi({ fetcher: async (_url, init) => {
    bodies.push(JSON.parse(init.body)); return Response.json(localPage({ replayed: true }));
  } });
  const done = await retry.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress });
  assert.equal(done.cookie_cleanup_complete, true); assert.equal(bodies.length, 3); assert.equal(bodies[2].cursor, cursor);
  setActivePrivateMediaSessionKey(null);
});

test('scope identity shape cursor and completion mismatches cannot confirm replacement', async () => {
  for (const changes of [{ scope: 'global' }, { owner_id: SID2 }, { session_id: SID2 }, { replayed: 1 },
    { completed_at: 'yesterday' }, { next_cursor: 'video:00000000-0000-0000-0000-000000000000', cookie_cleanup_complete: false },
    { next_cursor: 'video:' + SID2 + ':' + SID }, { cookie_cleanup_complete: false }, { extra: 'not-allowed' }]) {
    let calls = 0;
    const f = actualBackendApi({ fetcher: async () => { calls += 1; return Response.json(localPage(changes)); } });
    await assert.rejects(f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND), /Unable to confirm/); assert.equal(calls, 1);
  }
  setActivePrivateMediaSessionKey(null);
});

test('progress receipt drift repeated cursor or persistence failure prevents further dispatch', async () => {
  const progress = localPage({ next_cursor: 'archive:' + SID2 + ':' + SID, cookie_cleanup_complete: false });
  for (const page of [localPage({ completed_at: '2026-10-27T19:00:00Z' }), progress,
    localPage({ next_cursor: 'archive:' + SID + ':' + SID, cookie_cleanup_complete: false })]) {
    let calls = 0;
    const f = actualBackendApi({ fetcher: async () => { calls += 1; return Response.json(page); } });
    await assert.rejects(f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress }), /Unable to confirm/);
    assert.equal(calls, 1);
  }
  let calls = 0;
  const f = actualBackendApi({ fetcher: async () => { calls += 1; return Response.json(progress); } });
  await assert.rejects(f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, {
    onProgress: async () => { throw new Error('synthetic-storage-secret'); },
  }), /Unable to confirm/); assert.equal(calls, 1);
  setActivePrivateMediaSessionKey(null);
});

test('native revocation omits cookies and rejects a browser pagination response', async () => {
  for (const scope of ['local', 'global']) {
    const calls = [];
    const f = actualBackendApi({ platform: 'ios', fetcher: async (url, init) => {
      calls.push([url, init]); return Response.json(localPage({ scope, next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false }));
    } });
    const action = scope === 'local' ? f.api.revokeReplacementPrivateMediaSession : f.api.revokeGlobalPrivateMediaSession;
    await assert.rejects(action(jwt(), BACKEND), /Unable to confirm/);
    assert.equal(calls[0][1].credentials, 'omit'); assert.deepEqual(JSON.parse(calls[0][1].body), { transport: 'native' });
    assert.equal(calls.length, 1);
  }
  setActivePrivateMediaSessionKey(null);
});

test('unsafe backend malformed progress provider denial and oversized bodies fail with sanitized errors', async () => {
  let calls = 0;
  const f = actualBackendApi({ fetcher: async () => { calls += 1; return Response.json(localPage()); } });
  for (const backend of ['http://api.usepeso.com', BACKEND + '?secret=x', 'https://u:p@api.usepeso.com', 'https://other.invalid']) {
    await assert.rejects(f.api.revokeReplacementPrivateMediaSession(jwt(), backend), /Unable to confirm/);
  }
  await assert.rejects(f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress: { ...localPage(), session_id: SID2 } }), /Unable to confirm/);
  assert.equal(calls, 0);
  for (const response of [new Response('synthetic-private-provider-text', { status: 401 }),
    new Response('{broken'), new Response('x'.repeat(8193))]) {
    const g = actualBackendApi({ fetcher: async () => response });
    await assert.rejects(g.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND),
      (error) => error.message.startsWith('Unable to confirm') && !error.message.includes('synthetic') && !error.cause);
  }
  setActivePrivateMediaSessionKey(null);
});

test('network deadline rejects without waiting for an uncooperative mocked response', async () => {
  let expire;
  const f = actualBackendApi({ fetcher: async () => new Promise(() => {}), timers: {
    setTimeout(callback, delay) { assert.equal(delay, 60000); expire = callback; return 1; }, clearTimeout() {},
  } });
  const operation = f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND); expire();
  await assert.rejects(operation, /Unable to confirm/); setActivePrivateMediaSessionKey(null);
});

test('deadline never abandons a pending journal write or dispatches its next page', async () => {
  let expire; let entered; let persist; let calls = 0;
  const writing = new Promise((resolve) => { entered = resolve; });
  const durable = new Promise((resolve) => { persist = resolve; });
  const f = actualBackendApi({ enabled: false, fetcher: async () => {
    calls += 1; return Response.json(localPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false }));
  }, timers: { setTimeout(callback) { expire = callback; return 1; }, clearTimeout() {} } });
  let settled = false;
  const operation = f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, {
    onProgress: async () => { entered(); await durable; },
  });
  operation.then(() => { settled = true; }, () => { settled = true; });
  await writing; expire(); await Promise.resolve(); assert.equal(settled, false);
  persist(); await assert.rejects(operation, /Unable to confirm/); assert.equal(calls, 1);
  setActivePrivateMediaSessionKey(null);
});

test('global cookie progress survives a lost response and is not a completion checkpoint', async () => {
  const values = new Map(); const page = localPage({ scope: 'global', next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false });
  const first = fixture({ values, config: { async revokeMedia(_token, _backend, options) {
    await options.onProgress(page); throw new Error('synthetic lost page response');
  } } });
  await assert.rejects(first.logout(), /Unable to complete sign out/);
  assert.equal(first.requests.length, 0); assert.equal(values.size, 1); assert.ok([...values.keys()][0].endsWith(':cookies'));
  assert.equal(await first.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  const second = fixture({ values, config: { async revokeMedia(_token, _backend, options) {
    assert.deepEqual(options.progress, page); return RECEIPT;
  } } });
  await second.logout(); assert.equal(second.requests.length, 1); assert.equal(values.size, 1);
  assert.deepEqual(await second.getConfirmedGlobalReceipt(jwt(), BACKEND), RECEIPT);
});

test('legacy logout receipts cannot stand in for new cookie-complete confirmation', async () => {
  const values = new Map([[`peso:media-logout:v1:${BACKEND}:${AUTH}:${OWNER}:${SID}`, JSON.stringify(RECEIPT)]]);
  const f = fixture({ values }); assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  await f.logout(); assert.equal(f.tokens.length, 1); assert.equal(values.size, 2);
});


test('backend drift between confirmed pages cannot send the captured token to another host', async () => {
  let backend = BACKEND; const urls = [];
  const f = actualBackendApi({ backend: () => backend, fetcher: async (url) => {
    urls.push(url); return Response.json(localPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false }));
  } });
  await assert.rejects(f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, {
    onProgress: async () => { backend = 'https://other.invalid'; },
  }), /Unable to confirm/);
  assert.deepEqual(urls, [BACKEND + '/private-media/v2/session-replacement']); setActivePrivateMediaSessionKey(null);
});

test('account mutation binds the expected accepted identity to the actual user PUT bearer', async () => {
  let active = OWNER + ':' + SID;
  const f = fixture({ config: { getActiveSessionKey: () => active } });
  const update = (token = jwt()) => f.fetch(AUTH + '/user', { method: 'PUT', headers: { Authorization: 'Bearer ' + token }, body: '{}' });
  await assert.rejects(update(), /Unable to update your account/); assert.equal(f.requests.length, 0);
  await f.updateUser(active, () => update()); assert.equal(f.requests.length, 1); assert.equal(f.getAuthMutationKey(), null);
  const old = active; active = OWNER + ':' + SID2;
  await assert.rejects(f.updateUser(old, () => update()), /Unable to update your account/); assert.equal(f.requests.length, 1);
  active = old;
  await assert.rejects(f.updateUser(old, () => update(jwt({ session_id: SID2 }))), /Unable to update your account/);
  assert.equal(f.requests.length, 1);
});

test('a queued mutation cannot dispatch under a different account after its intent is captured', async () => {
  let active = OWNER + ':' + SID; let enter; let proceed;
  const entered = new Promise((resolve) => { enter = resolve; });
  const wait = new Promise((resolve) => { proceed = resolve; });
  const f = fixture({ config: { getActiveSessionKey: () => active } });
  const operation = f.updateUser(active, async () => {
    enter(); await wait;
    return f.fetch(AUTH + '/user', { method: 'PUT', headers: { Authorization: 'Bearer ' + jwt({ session_id: SID2 }) } });
  });
  await entered; active = OWNER + ':' + SID2; proceed();
  await assert.rejects(operation, /Unable to update your account/); assert.equal(f.requests.length, 0);
});

test('a superseded account update response cannot reach SDK session save', async () => {
  let active = OWNER + ':' + SID; let enter; let finish;
  const entered = new Promise((resolve) => { enter = resolve; });
  const wait = new Promise((resolve) => { finish = resolve; });
  const f = fixture({ config: { getActiveSessionKey: () => active, async fetch() { enter(); await wait; return Response.json({ user: {} }); } } });
  const operation = f.updateUser(active, () => f.fetch(AUTH + '/user', { method: 'PUT', headers: { Authorization: 'Bearer ' + jwt() } }));
  await entered; active = OWNER + ':' + SID2; finish();
  await assert.rejects(operation, /Unable to update your account/); assert.equal(f.getAuthMutationKey(), null);
});

test('concurrent credential changes reject rather than inherit another request intent', async () => {
  let finish; const wait = new Promise((resolve) => { finish = resolve; });
  const key = OWNER + ':' + SID;
  const f = fixture({ config: { getActiveSessionKey: () => key } });
  const first = f.updateUser(key, () => wait); assert.equal(f.getAuthMutationKey(), key);
  let ran = false;
  await assert.rejects(f.updateUser(key, async () => { ran = true; }), /Unable to update your account/);
  assert.equal(ran, false); finish('done'); assert.equal(await first, 'done'); assert.equal(f.getAuthMutationKey(), null);
});

test('disabled credential update preserves the original provider action', async () => {
  const f = fixture({ config: { enabled: false, authUrl: 'invalid' } }); let ran = false;
  assert.equal(await f.updateUser(null, async () => { ran = true; return 'unchanged'; }), 'unchanged'); assert.equal(ran, true);
});

test('app-only global completion is unavailable to replacement until provider acknowledgement is durable', async () => {
  let entered; let finish;
  const waiting = new Promise((resolve) => { entered = resolve; });
  const provider = new Promise((resolve) => { finish = resolve; });
  const f = fixture({ config: { async fetch() { entered(); await provider; return new Response(null, { status: 204 }); } } });
  const operation = f.logout(); await waiting;
  assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  assert.deepEqual(JSON.parse([...f.values.values()][0]), RECEIPT);
  finish(); await operation;
  assert.deepEqual(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), RECEIPT);
});

test('provider acknowledgement write failure remains unconfirmed and can retry without a backend replay', async () => {
  const values = new Map(); const f = fixture({ values });
  const persist = f.storage.setItem;
  f.storage.setItem = async (key, value) => {
    if (JSON.parse(value).provider_acknowledged) throw new Error('synthetic-storage-failure');
    return persist(key, value);
  };
  await assert.rejects(f.logout(), /Unable to complete sign out/);
  assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  const retry = fixture({ values }); await retry.logout(); assert.equal(retry.tokens.length, 0);
  assert.deepEqual(await retry.getConfirmedGlobalReceipt(jwt(), BACKEND), RECEIPT);
});

test('a durable acknowledged global operation never sends provider logout again after a retry or reload', async () => {
  const values = new Map(); const first = fixture({ values }); await first.logout();
  const retry = fixture({ values, config: { async fetch() { throw new Error('Must not revoke a later provider login.'); } } });
  assert.equal((await retry.logout()).status, 204); assert.equal(retry.tokens.length, 0);
  assert.deepEqual(await retry.getConfirmedGlobalReceipt(jwt(), BACKEND), RECEIPT);
});

test('global removal intent remains captured through the full action and distinguishes anonymous from absent', async () => {
  const f = fixture(); let finish;
  const wait = new Promise((resolve) => { finish = resolve; });
  assert.equal(f.getLogoutIntentKey(), undefined);
  const operation = f.signOut(OWNER + ':' + SID, () => wait);
  assert.equal(f.getLogoutIntentKey(), OWNER + ':' + SID); finish(); await operation;
  assert.equal(f.getLogoutIntentKey(), undefined);
  const anonymous = f.signOut(null, async () => { assert.equal(f.getLogoutIntentKey(), null); });
  await anonymous; assert.equal(f.getLogoutIntentKey(), undefined);
});

test('incoming acceptance uses only captured candidate credentials and exact read-only session decision', async () => {
  for (const platform of ['web', 'ios']) {
    const calls = [];
    const f = actualBackendApi({ platform, fetcher: async (url, init) => { calls.push([url, init]);
      return Response.json({ owner_id: OWNER, session_id: SID2, accepted: true }); } });
    setActivePrivateMediaSessionKey(OWNER + ':' + SID);
    const candidate = jwt({ session_id: SID2 });
    const decision = await f.api.verifyIncomingPrivateMediaSession(candidate, BACKEND);
    assert.equal(decision.accepted, true); assert.equal(calls[0][0], BACKEND + '/private-media/session-acceptance');
    assert.equal(calls[0][1].headers.Authorization, 'Bearer ' + candidate);
    assert.deepEqual(JSON.parse(calls[0][1].body), { transport: platform === 'web' ? 'browser' : 'native' });
    assert.equal(calls[0][1].credentials, platform === 'web' ? 'include' : 'omit');
    assert.equal(calls[0][1].redirect, 'error');
  }
  setActivePrivateMediaSessionKey(null);
});

test('incoming acceptance rejects absent false wrong-account wrong-session extra or malformed decisions', async () => {
  for (const value of [null, {}, { owner_id: OWNER, session_id: SID, accepted: false },
    { owner_id: SID2, session_id: SID, accepted: true }, { owner_id: OWNER, session_id: SID2, accepted: true },
    { owner_id: OWNER, session_id: SID, accepted: true, token: 'untrusted' }]) {
    const f = actualBackendApi({ fetcher: async () => Response.json(value) });
    await assert.rejects(f.api.verifyIncomingPrivateMediaSession(jwt(), BACKEND), /Unable to confirm/);
  }
  setActivePrivateMediaSessionKey(null);
});

test('incoming acceptance failure drift and timeout never fall back to another identity or endpoint', async () => {
  let backend = BACKEND; const calls = [];
  const f = actualBackendApi({ backend: () => backend, fetcher: async (url) => { calls.push(url); backend = 'https://other.invalid';
    return Response.json({ owner_id: OWNER, session_id: SID, accepted: true }); } });
  await assert.rejects(f.api.verifyIncomingPrivateMediaSession(jwt(), BACKEND), /Unable to confirm/);
  assert.deepEqual(calls, [BACKEND + '/private-media/session-acceptance']);
  let expire; let captured;
  const stalled = actualBackendApi({ fetcher: async (_url, init) => { captured = init.signal; return new Promise(() => {}); },
    timers: { setTimeout(fn, ms) { assert.equal(ms, 30000); expire = fn; return 1; }, clearTimeout() {} } });
  const operation = stalled.api.verifyIncomingPrivateMediaSession(jwt(), BACKEND); expire();
  await assert.rejects(operation, /Unable to confirm/); assert.equal(captured.aborted, true);
  setActivePrivateMediaSessionKey(null);
});

test('pending global-provider retry is distinguished from confirmed local completion and another session', async () => {
  const f = fixture({ config: { async fetch() { throw new Error('synthetic provider response lost'); } } });
  await assert.rejects(f.logout(), /Unable to complete sign out/);
  assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), true);
  assert.equal(await f.hasPendingGlobalLogout(jwt({ session_id: SID2 }), BACKEND), false);
  assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  const retry = fixture({ values: f.values }); await retry.logout();
  assert.equal(await retry.hasPendingGlobalLogout(jwt(), BACKEND), false);
  assert.deepEqual(await retry.getConfirmedGlobalReceipt(jwt(), BACKEND), RECEIPT);
});

const globalPage = (changes = {}) => localPage({ scope: 'global', ...changes });
const globalProgressKey = `peso:media-logout:v2:${BACKEND}:${AUTH}:${OWNER}:${SID}:cookies`;

test('mixed archive avatar video cookie pages remain strictly ordered and avatar progress selects global retry', async () => {
  const cursors = ['archive:' + SID2 + ':' + SID, 'avatar:' + SID2 + ':' + SID, 'video:' + SID2 + ':' + SID];
  const bodies = []; let index = 0; let progress;
  const f = actualBackendApi({ fetcher: async (_url, init) => {
    bodies.push(JSON.parse(init.body));
    const cursor = cursors[index++];
    return Response.json(localPage(cursor ? { next_cursor: cursor, cookie_cleanup_complete: false } : {}));
  } });
  await f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { onProgress: async page => { progress = page; } });
  assert.deepEqual(bodies.map(body => body.cursor ?? null), [null, ...cursors]);
  assert.equal(progress.next_cursor, 'video:' + SID2 + ':' + SID);
  const stored = fixture({ values: new Map([[globalProgressKey, JSON.stringify(globalPage({
    next_cursor: 'avatar:' + SID2 + ':' + SID, cookie_cleanup_complete: false }))]]) });
  assert.equal(await stored.hasPendingGlobalLogout(jwt(), BACKEND), true);
  assert.equal(await stored.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  const regression = actualBackendApi({ fetcher: async () => Response.json(localPage({ next_cursor: 'archive:' + SID2 + ':' + SID, cookie_cleanup_complete: false })) });
  await assert.rejects(regression.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, {
    progress: localPage({ next_cursor: 'avatar:' + SID2 + ':' + SID, cookie_cleanup_complete: false }) }), /Unable to confirm/);
  setActivePrivateMediaSessionKey(null);
});

test('partial and final cookie pages select pending global continuation without certifying completion', async () => {
  for (const page of [globalPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false }), globalPage()]) {
    const f = fixture({ values: new Map([[globalProgressKey, JSON.stringify(page)]]) });
    assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), true);
    assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
    assert.equal(await f.hasPendingGlobalLogout(jwt({ session_id: SID2 }), BACKEND), false);
    assert.equal(await f.hasPendingGlobalLogout(jwt({ sub: SID2 }), BACKEND), false);
    await assert.rejects(f.hasPendingGlobalLogout(jwt({ iss: 'https://other.invalid/auth/v1' }), BACKEND), /Unable to complete/);
    await assert.rejects(f.hasPendingGlobalLogout(jwt(), 'https://other.invalid'), /Unable to complete/);
  }
  const acknowledged = fixture({ values: new Map([[globalProgressKey, JSON.stringify(globalPage())],
    [globalProgressKey.slice(0, -8), JSON.stringify({ ...RECEIPT, provider_acknowledged: true })]]) });
  assert.equal(await acknowledged.hasPendingGlobalLogout(jwt(), BACKEND), false);
});

test('pending global cookie detection rejects malformed unbound and oversized progress', async () => {
  for (const value of [null, [], {}, globalPage({ scope: 'local' }), globalPage({ owner_id: SID2 }),
    globalPage({ session_id: SID2 }), globalPage({ extra: true }), globalPage({ replayed: 1 }),
    globalPage({ completed_at: 'yesterday' }), globalPage({ completed_at: '2'.repeat(65) }),
    globalPage({ next_cursor: 'video:' + SID2 + ':' + SID }), globalPage({ cookie_cleanup_complete: false }),
    globalPage({ next_cursor: 'video:00000000-0000-0000-0000-000000000000', cookie_cleanup_complete: false }),
    globalPage({ next_cursor: 'video:' + SID2.toUpperCase().replace('000000000003', 'ABCDEFABCDEF'), cookie_cleanup_complete: false })]) {
    const f = fixture({ values: new Map([[globalProgressKey, JSON.stringify(value)]]) });
    assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), false);
    await assert.rejects(f.logout(), /Unable to complete/); assert.equal(f.tokens.length, 0); assert.equal(f.requests.length, 0);
  }
  for (const raw of ['{broken', ' '.repeat(8193)]) {
    const f = fixture({ values: new Map([[globalProgressKey, raw]]) });
    await assert.rejects(f.hasPendingGlobalLogout(jwt(), BACKEND), /Unable to complete/);
    await assert.rejects(f.logout(), /Unable to complete/); assert.equal(f.tokens.length, 0); assert.equal(f.requests.length, 0);
  }
});

test('fixed global transport resumes bound cookie progress from blocked null but denies an active other session', async () => {
  const progress = globalPage({ next_cursor: 'archive:' + SID2 + ':' + SID, cookie_cleanup_complete: false }); const calls = [];
  const f = actualBackendApi({ fetcher: async (url, init) => { calls.push([url, init]); return Response.json(globalPage({ replayed: true })); } });
  setActivePrivateMediaSessionKey(null);
  assert.deepEqual(JSON.parse(JSON.stringify(await f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { progress }))), { ...RECEIPT, replayed: true, cookie_inventory_version: 2 });
  assert.equal(calls.length, 1); assert.equal(calls[0][0], BACKEND + '/private-media/v2/logout');
  assert.equal(calls[0][1].headers.Authorization, 'Bearer ' + jwt());
  assert.deepEqual(JSON.parse(calls[0][1].body), { transport: 'browser', cursor: progress.next_cursor });
  await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND), /Unable to confirm/);
  const done = await f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { progress: globalPage() });
  assert.equal(done.scope, 'global'); assert.equal(calls.length, 1);
  setActivePrivateMediaSessionKey(OWNER + ':' + SID2);
  for (const page of [progress, globalPage()]) await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { progress: page }), /Unable to confirm/);
  assert.equal(calls.length, 1); setActivePrivateMediaSessionKey(null);
});

test('global transport validates supplied progress before allowing any blocked continuation', async () => {
  const f = actualBackendApi(); setActivePrivateMediaSessionKey(null);
  for (const progress of [false, {}, globalPage({ scope: 'local' }), globalPage({ owner_id: SID2 }),
    globalPage({ session_id: SID2 }), globalPage({ next_cursor: 'invalid', cookie_cleanup_complete: false }), globalPage({ extra: true })]) {
    await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { progress }), /Unable to confirm/);
  }
  await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt({ iss: 'https://other.invalid/auth/v1' }), BACKEND, { progress: globalPage() }), /Unable to confirm/);
  await assert.rejects(f.api.revokeGlobalPrivateMediaSession('', BACKEND, { progress: globalPage() }), /Unable to confirm/);
  await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), 'https://other.invalid', { progress: globalPage() }), /Unable to confirm/);
  assert.equal(f.calls.length, 0);
});

test('a fresh global attempt may continue while blocked only after its first page is durably persisted', async () => {
  const calls = []; let entered; let persist;
  const writing = new Promise((resolve) => { entered = resolve; }); const durable = new Promise((resolve) => { persist = resolve; });
  const f = actualBackendApi({ fetcher: async (_url, init) => {
    calls.push(JSON.parse(init.body)); setActivePrivateMediaSessionKey(null);
    return Response.json(calls.length === 1 ? globalPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false }) : globalPage());
  } });
  let writes = 0;
  const operation = f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { onProgress: async () => {
    writes += 1; if (writes === 1) { entered(); await durable; }
  } });
  await writing; assert.equal(calls.length, 1); persist();
  assert.equal((await operation).scope, 'global'); assert.equal(calls.length, 2); assert.equal(writes, 2);
  assert.equal(calls[1].cursor, 'video:' + SID2 + ':' + SID); setActivePrivateMediaSessionKey(null);
});

test('missing or failed progress persistence cannot relax a fresh global active-session guard', async () => {
  for (const complete of [false, true]) {
    let calls = 0;
    const f = actualBackendApi({ fetcher: async () => { calls += 1; setActivePrivateMediaSessionKey(null);
      return Response.json(complete ? globalPage() : globalPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false })); } });
    await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND), /Unable to confirm/); assert.equal(calls, 1);
  }
  let calls = 0;
  const failed = actualBackendApi({ fetcher: async () => { calls += 1; setActivePrivateMediaSessionKey(null);
    return Response.json(globalPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false })); } });
  await assert.rejects(failed.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { onProgress: async () => { throw new Error('synthetic persistence failure'); } }), /Unable to confirm/);
  assert.equal(calls, 1); setActivePrivateMediaSessionKey(null);
});

test('another active session blocks global page continuation and final acceptance even after persistence', async () => {
  for (const complete of [false, true]) {
    let calls = 0; let writes = 0;
    const f = actualBackendApi({ fetcher: async () => { calls += 1;
      return Response.json(complete ? globalPage() : globalPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false })); } });
    await assert.rejects(f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { onProgress: async () => {
      writes += 1; setActivePrivateMediaSessionKey(OWNER + ':' + SID2);
    } }), /Unable to confirm/);
    assert.equal(calls, 1); assert.equal(writes, 1);
  }
  setActivePrivateMediaSessionKey(null);
});

test('actual global cookie continuation recovers a partial-page failure after replacement blocks the UI', async () => {
  const calls = []; let failSecond = true;
  const api = actualBackendApi({ fetcher: async (url, init) => {
    calls.push([url, JSON.parse(init.body)]);
    if (calls.length === 1) return Response.json(globalPage({ next_cursor: 'video:' + SID2 + ':' + SID, cookie_cleanup_complete: false }));
    if (failSecond) throw new Error('synthetic second page response lost');
    return Response.json(globalPage({ replayed: true }));
  } });
  const f = fixture({ config: { browserInventoryVersion: 2, revokeMedia: api.api.revokeGlobalPrivateMediaSession } });
  await assert.rejects(f.logout(), /Unable to complete/); assert.equal(calls.length, 2); assert.equal(f.requests.length, 0);
  assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), true); assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  setActivePrivateMediaSessionKey(null); failSecond = false; await f.logout();
  assert.equal(calls.length, 3); assert.equal(calls[2][0], BACKEND + '/private-media/v2/logout');
  assert.equal(calls[2][1].cursor, 'video:' + SID2 + ':' + SID); assert.equal(f.requests.length, 1);
  assert.deepEqual(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), { ...RECEIPT, replayed: true, cookie_inventory_version: 2 });
  assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), false); setActivePrivateMediaSessionKey(null);
});

test('a durable final global page survives compact-receipt persistence failure without another API request', async () => {
  const api = actualBackendApi(); const f = fixture({ config: { browserInventoryVersion: 2, revokeMedia: api.api.revokeGlobalPrivateMediaSession } });
  const persist = f.storage.setItem; let rejectReceipt = true;
  f.storage.setItem = async (key, value) => {
    if (rejectReceipt && key === globalProgressKey.slice(0, -8)) throw new Error('synthetic compact receipt write failure');
    return persist(key, value);
  };
  await assert.rejects(f.logout(), /Unable to complete/); assert.equal(api.calls.length, 1); assert.equal(f.requests.length, 0);
  assert.deepEqual(JSON.parse(f.values.get(globalProgressKey)), globalPage());
  assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), true); assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  rejectReceipt = false; setActivePrivateMediaSessionKey(null); await f.logout();
  assert.equal(api.calls.length, 1); assert.equal(f.requests.length, 1); assert.equal(f.values.has(globalProgressKey), false);
  assert.deepEqual(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), { ...RECEIPT, cookie_inventory_version: 2 });
  assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), false); setActivePrivateMediaSessionKey(null);
});

test('browser inventory upgrades finish v1 first then restart v2 from null with the same app receipt time', async () => {
  const legacy = { ...localPage({ next_cursor: 'avatar:' + SID2, cookie_cleanup_complete: false }) }; delete legacy.cookie_inventory_version;
  const bodies = []; const urls = []; const progress = [];
  const f = actualBackendApi({ fetcher: async (url, init) => {
    urls.push(url); bodies.push(JSON.parse(init.body));
    if (url.endsWith('/v2/session-replacement')) return Response.json(localPage());
    const done = { ...localPage() }; delete done.cookie_inventory_version; return Response.json(done);
  } });
  const result = await f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress: legacy, onProgress: async p => { progress.push(p); } });
  assert.deepEqual(urls, [BACKEND + '/private-media/session-replacement', BACKEND + '/private-media/v2/session-replacement']);
  assert.deepEqual(bodies.map(b => b.cursor ?? null), [legacy.next_cursor, null]);
  assert.equal(result.cookie_inventory_version, 2); assert.equal(result.completed_at, legacy.completed_at);
  assert.equal(progress[0].cookie_inventory_version, undefined);
  for (const malformed of [localPage({ cookie_inventory_version: 1 }), localPage({ cookie_inventory_version: 3 }),
    localPage({ next_cursor: 'video:00000000-0000-0000-0000-000000000000:' + SID, cookie_cleanup_complete: false }),
    localPage({ next_cursor: 'avatar:' + SID2 + ':not-a-session', cookie_cleanup_complete: false })]) {
    await assert.rejects(f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress: malformed }), /Unable to confirm/);
  }
  setActivePrivateMediaSessionKey(null);
});

test('v2 complete null progress does not replay while v1 complete null explicitly upgrades, and NIL is only the final path sentinel', async () => {
  const calls = [];
  const f = actualBackendApi({ fetcher: async (url, init) => { calls.push([url, JSON.parse(init.body)]); return Response.json(localPage()); } });
  const legacy = { ...localPage() }; delete legacy.cookie_inventory_version;
  await f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress: legacy }); assert.equal(calls.length, 1);
  await f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress: localPage() }); assert.equal(calls.length, 1);
  const sentinel = localPage({ next_cursor: 'avatar:' + SID2 + ':00000000-0000-0000-0000-000000000000', cookie_cleanup_complete: false });
  await f.api.revokeReplacementPrivateMediaSession(jwt(), BACKEND, { progress: sentinel });
  assert.equal(calls[1][1].cursor, sentinel.next_cursor); setActivePrivateMediaSessionKey(null);
});

test('already acknowledged v1 global provider operation upgrades inventory without repeating provider logout', async () => {
  const key = globalProgressKey.slice(0, -8);
  const values = new Map([[key, JSON.stringify({ ...RECEIPT, provider_acknowledged: true })]]);
  let requests = 0;
  const f = fixture({ values, config: { browserInventoryVersion: 2,
    async revokeMedia(_token, _backend, options) {
      assert.equal(options.progress.cookie_inventory_version, undefined); assert.equal(options.progress.next_cursor, null);
      await options.onProgress(globalPage()); return { ...RECEIPT, cookie_inventory_version: 2 };
    }, async fetch() { requests += 1; throw new Error('Provider operation must not replay'); },
  } });
  assert.equal(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), null);
  assert.equal(await f.hasPendingGlobalLogout(jwt(), BACKEND), true);
  assert.equal((await f.logout()).status, 204); assert.equal(requests, 0);
  assert.deepEqual(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), { ...RECEIPT, cookie_inventory_version: 2 });
  assert.equal(JSON.parse(values.get(key)).provider_acknowledged, true);
});

test('actual project modules release exclusive coordination before provider fetch and SDK storage removal', async () => {
  const { createPrivateMediaSessionController } = require('../lib/privateMediaSession');
  const data = new Map(); const main = 'fixture-auth'; const journal = main + ':peso-private-media-transition:v1';
  const current = { access_token: jwt(), user: { id: OWNER }, refresh_token: 'synthetic-refresh' };
  data.set(main, JSON.stringify(current)); let held = false; let tail = Promise.resolve(); let active = OWNER + ':' + SID;
  const lock = action => { const next = tail.then(async () => { assert.equal(held, false); held = true; try { return await action(); } finally { held = false; } }); tail = next.catch(() => {}); return next; };
  const storage = { async getItem(k) { return data.get(k) ?? null; }, async setItem(k, v) { data.set(k, v); }, async removeItem(k) { data.delete(k); } };
  let controller; let localCalls = 0; let appCalls = 0; let providerCalls = 0;
  const delay = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
  const provider = delay(); const entered = delay();
  const media = createMediaLogoutFetch({ enabled: true, browserInventoryVersion: 2, authUrl: AUTH, getBackendUrl: () => BACKEND, storage,
    getActiveSessionKey: () => active, stopMedia: async () => {},
    beginGlobalLogout: (...args) => controller.beginGlobalLogout(...args), completeGlobalLogout: (...args) => controller.completeGlobalLogout(...args),
    hasPendingGlobalIntent: (...args) => controller.hasPendingGlobalIntent(...args),
    async revokeMedia(_token, _backend, options) {
      assert.equal(held, true); assert.equal(options.globalIntent.mode, 'global'); assert.equal(active, null);
      assert.equal(JSON.parse(data.get(journal)).stage, 'pending'); appCalls += 1;
      await options.onProgress(globalPage()); return { ...RECEIPT, cookie_inventory_version: 2 };
    },
    async fetch() { assert.equal(held, false); providerCalls += 1; entered.resolve(); await provider.promise; return new Response(null, { status: 204 }); },
  });
  controller = createPrivateMediaSessionController({ enabled: true, browserInventoryVersion: 2, storage, storageKey: main, authUrl: AUTH,
    getBackendUrl: () => BACKEND, runExclusive: lock, stopMedia: async () => {}, onActiveKey: key => { active = key; },
    validateIncomingSession: async () => ({ owner_id: OWNER, session_id: SID, accepted: true }),
    getGlobalReceipt: (...args) => media.getConfirmedGlobalReceipt(...args),
    revokeSession: async () => { localCalls += 1; throw new Error('Cannot substitute local revocation for global'); },
  });
  await controller.initialize();
  const work = media.signOut(OWNER + ':' + SID, () => media.fetch(AUTH + '/logout?scope=global', { method: 'POST', headers: { Authorization: 'Bearer ' + jwt() } }));
  await entered.promise; assert.equal(JSON.parse(data.get(journal)).stage, 'provider-pending');
  assert.equal(await media.hasPendingGlobalLogout(jwt(), BACKEND), true);
  const other = { access_token: jwt({ session_id: SID2 }), user: { id: OWNER } };
  await assert.rejects(controller.storage.setItem(main, JSON.stringify(other)), /Unable to complete/);
  await controller.retry(); assert.equal(localCalls, 0); assert.equal(active, null);
  provider.resolve(); await work; assert.equal(held, false); assert.equal(JSON.parse(data.get(journal)).stage, 'revoked');
  await controller.storage.removeItem(main); assert.equal(data.has(main), false); assert.equal(held, false);
  assert.equal(appCalls, 1); assert.equal(providerCalls, 1); assert.equal(localCalls, 0);
});

test('durable provider ACK survives final controller journal failure and inventory retry never repeats provider logout', async () => {
  const key = globalProgressKey.slice(0, -8); let finishFails = true; let providerCalls = 0; let begins = 0; let completes = 0;
  const f = fixture({ config: { browserInventoryVersion: 2,
    async beginGlobalLogout(_token, _backend, action) { begins += 1; return action({ version: 2, mode: 'global', inventory_version: 2, owner_id: OWNER, session_id: SID, backend: BACKEND }); },
    async completeGlobalLogout() { completes += 1; if (finishFails) throw new Error('synthetic final journal write failure'); },
    async revokeMedia(_token, _backend, options) { await options.onProgress(globalPage()); return { ...RECEIPT, cookie_inventory_version: 2 }; },
    async fetch() { providerCalls += 1; return new Response(null, { status: 204 }); },
  } });
  await assert.rejects(f.logout(), /Unable to complete/); assert.equal(providerCalls, 1);
  assert.equal(JSON.parse(f.values.get(key)).provider_acknowledged, true);
  finishFails = false; await f.logout();
  assert.equal(providerCalls, 1); assert.equal(begins, 2); assert.equal(completes, 2);
  assert.deepEqual(await f.getConfirmedGlobalReceipt(jwt(), BACKEND), { ...RECEIPT, cookie_inventory_version: 2 });
});

test('blocked legacy global progress retains its bound intent while switching from v1 final to v2 inventory', async () => {
  const legacy = { ...globalPage({ next_cursor: 'archive:' + SID2, cookie_cleanup_complete: false }) }; delete legacy.cookie_inventory_version;
  const calls = []; const pages = [];
  const f = actualBackendApi({ fetcher: async (url, init) => {
    calls.push([url, JSON.parse(init.body)]);
    const value = globalPage({ replayed: true });
    if (!url.includes('/v2/')) delete value.cookie_inventory_version;
    return Response.json(value);
  } });
  setActivePrivateMediaSessionKey(null);
  const result = await f.api.revokeGlobalPrivateMediaSession(jwt(), BACKEND, { progress: legacy, onProgress: async p => { pages.push(p); } });
  assert.equal(result.cookie_inventory_version, 2); assert.equal(result.completed_at, legacy.completed_at);
  assert.deepEqual(calls.map(([url]) => url), [BACKEND + '/private-media/logout', BACKEND + '/private-media/v2/logout']);
  assert.deepEqual(calls.map(([, body]) => body.cursor ?? null), [legacy.next_cursor, null]);
  assert.equal(pages[0].cookie_inventory_version, undefined); assert.equal(pages[1].cookie_inventory_version, 2);
});

test('actual controller legacy global ACK survives missing separate logout key and failed inventory upgrade without provider replay', async () => {
  const { createPrivateMediaSessionController } = require('../lib/privateMediaSession');
  for (const location of ['completion', 'journal']) {
    const main = 'legacy-ack-fixture'; const key = OWNER + ':' + SID;
    const current = { access_token: jwt(), user: { id: OWNER } }; const data = new Map([[main, JSON.stringify(current)]]);
    if (location === 'completion') data.set(main + ':peso-private-media-completions:v1', JSON.stringify({
      version: 1, backend: BACKEND, issuer: AUTH, entries: [{ key, receipt: RECEIPT }],
    }));
    else data.set(main + ':peso-private-media-transition:v1', JSON.stringify({
      version: 1, backend: BACKEND, issuer: AUTH, from: key, to: null, revision: 1, stage: 'revoked', receipt: RECEIPT,
    }));
    const storage = { async getItem(k) { return data.get(k) ?? null; }, async setItem(k, v) { data.set(k, v); }, async removeItem(k) { data.delete(k); } };
    let controller; let active = null; let providerCalls = 0; let appCalls = 0; let failUpgrade = true;
    const media = createMediaLogoutFetch({ enabled: true, browserInventoryVersion: 2, authUrl: AUTH, getBackendUrl: () => BACKEND, storage,
      getActiveSessionKey: () => active, stopMedia: async () => {},
      beginGlobalLogout: (...args) => controller.beginGlobalLogout(...args), completeGlobalLogout: (...args) => controller.completeGlobalLogout(...args),
      hasPendingGlobalIntent: (...args) => controller.hasPendingGlobalIntent(...args),
      async revokeMedia(_token, _backend, options) {
        appCalls += 1; assert.equal(options.progress.completed_at, RECEIPT.completed_at);
        const page = globalPage(); await options.onProgress(page);
        if (failUpgrade) throw new Error('synthetic upgrade response failure');
        return { ...RECEIPT, cookie_inventory_version: 2 };
      },
      async fetch() { providerCalls += 1; throw new Error('Historical acknowledged provider operation must not replay'); },
    });
    controller = createPrivateMediaSessionController({ enabled: true, browserInventoryVersion: 2, storage, storageKey: main, authUrl: AUTH,
      getBackendUrl: () => BACKEND, runExclusive: async action => action(), stopMedia: async () => {}, onActiveKey: k => { active = k; },
      getGlobalReceipt: (...args) => media.getConfirmedGlobalReceipt(...args),
      validateIncomingSession: async () => ({ owner_id: OWNER, session_id: SID, accepted: true }),
      revokeSession: async () => { throw new Error('Global proof cannot use local cleanup'); },
    });
    await controller.initialize(); assert.equal(controller.getSnapshot().status, 'blocked');
    const dispatch = () => media.signOut(key, () => media.fetch(AUTH + '/logout?scope=global', { method: 'POST', headers: { Authorization: 'Bearer ' + jwt() } }));
    await assert.rejects(dispatch(), /Unable to complete/);
    const pending = JSON.parse(data.get(main + ':peso-private-media-transition:v1'));
    assert.deepEqual(pending.provider_receipt, RECEIPT); assert.equal(await media.hasPendingGlobalLogout(jwt(), BACKEND), true);
    failUpgrade = false; await dispatch();
    assert.equal(providerCalls, 0); assert.equal(appCalls, 2);
    assert.deepEqual(await media.getConfirmedGlobalReceipt(jwt(), BACKEND), { ...RECEIPT, cookie_inventory_version: 2 });
    assert.equal(JSON.parse(data.get(main + ':peso-private-media-transition:v1')).stage, 'revoked');
  }
});
