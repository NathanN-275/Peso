const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const OWNER = '11111111-1111-4111-8111-111111111111';
const SID = '22222222-2222-4222-8222-222222222222';
const REV = '33333333-3333-4333-8333-333333333333';
const NEXT = '44444444-4444-4444-8444-444444444444';
const KEY = OWNER + ':' + SID;
const BACKEND = 'https://api.usepeso.com';
const ROOT = BACKEND + '/private-media/avatar/' + REV + '/';
const GRANT = Buffer.alloc(32, 1).toString('base64url');
const JPEG = new Uint8Array([255, 216, 1, 2, 255, 217]);
const CACHE = 'private, no-store, max-age=0';
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
function load(relative, imports, globals = {}) {
  const filename = path.join(__dirname, relative);
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
  assert.deepEqual(compiled.diagnostics, []);
  const module = { exports: {} };
  new Function('require', 'module', 'exports', ...Object.keys(globals), compiled.outputText)(name => {
    assert.ok(Object.hasOwn(imports, name), 'Unexpected import ' + name); return imports[name];
  }, module, module.exports, ...Object.values(globals));
  return module.exports;
}
function issuance(changes = {}) {
  return { resource_kind: 'avatar', resource_id: REV, urls: { avatar: ROOT + 'avatar' },
    expires_in: 120, expires_at: new Date(Date.now() + 120000).toISOString(), media_grant: GRANT, ...changes };
}
function jsonResponse(value = issuance(), status = 200, headers = {}) {
  return Response.json(value, { status, headers: { 'Cache-Control': CACHE, ...headers } });
}
function imageResponse(bytes = JPEG, headers = {}, status = 200) {
  return new Response(bytes, { status, headers: { 'Content-Type': 'image/jpeg', 'Content-Length': '' + bytes.length,
    'Cache-Control': CACHE, ...headers } });
}
function harness(options = {}) {
  let epoch = 0, active = KEY, backend = BACKEND, release;
  const calls = []; const timers = [];
  const fetcher = options.fetcher || (async (_url, _init, at) => at === 0 ? jsonResponse() : imageResponse());
  const module = load('../lib/avatarReader.ts', {
    'expo/fetch': { fetch: async (url, init) => { calls.push([url, init]); return fetcher(url, init, calls.length - 1); } },
    'react-native': { Platform: { OS: options.platform || 'ios' } },
    './backendConfig': { getBackendApiUrl: () => backend },
    './backendUrlPolicy': require('../lib/backendUrlPolicy'),
    './privateMediaLifecycle': { getPrivateMediaEpoch: () => epoch, getActivePrivateMediaSessionKey: () => active,
      registerPrivateMediaRelease: fn => { release = fn; return () => {}; } },
    './privateMediaLogout': { getPrivateMediaSessionKey: token => token === 'original-token' ? KEY : null },
    './supabase': { supabaseAuthUrl: 'https://auth.invalid/auth/v1' },
    './profilePolicy': require('../lib/profilePolicy'),
  }, { process: { env: { EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: options.enabled === false ? 'false' : 'true' } },
    setTimeout: options.fakeTimer ? fn => { timers.push(fn); return timers.length; } : setTimeout,
    clearTimeout: options.fakeTimer ? () => {} : clearTimeout,
  });
  return { module, calls, timers, release: () => release(), bumpEpoch: () => { epoch++; },
    changeSession: () => { active = OWNER + ':' + NEXT; }, changeBackend: value => { backend = value; },
    read: (revision = REV, check = () => {}) => module.readProfileAvatar('original-token', revision, check) };
}

test('native reader separates original account credential from media-only byte credential and renders bounded data', async () => {
  const h = harness(); const value = await h.read();
  assert.equal(value.avatar_data_uri, 'data:image/jpeg;base64,' + Buffer.from(JPEG).toString('base64'));
  assert.equal(value.avatar_error, null); assert.equal(value.avatar_reupload_required, false);
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[0][0], ROOT + 'session'); assert.equal(h.calls[0][1].headers.Authorization, 'Bearer original-token');
  assert.deepEqual(JSON.parse(h.calls[0][1].body), { transport: 'native', asset_kinds: ['avatar'] });
  assert.deepEqual(h.calls[1][1].headers, { 'X-Peso-Media-Grant': GRANT, Accept: 'image/jpeg', 'Cache-Control': 'no-store' });
  for (const [, init] of h.calls) { assert.equal(init.credentials, 'omit'); assert.equal(init.redirect, 'error'); assert.equal(init.signal.aborted, true); }
});

for (const options of [{ enabled: false }, { platform: 'web' }]) {
  test('disabled or existing initials-only web surface issues no avatar capability ' + JSON.stringify(options), async () => {
    const h = harness(options); assert.deepEqual(await h.read(), { avatar_data_uri: null, avatar_reupload_required: false, avatar_error: null });
    assert.deepEqual(h.calls, []);
  });
}

test('only exact legacy error preserves metadata reupload classification', async () => {
  const h = harness({ fetcher: async () => jsonResponse({ detail: 'Re-upload your profile picture to finish the security update.' }, 409) });
  assert.deepEqual(await h.read(), { avatar_data_uri: null, avatar_reupload_required: true, avatar_error: null });
  assert.equal(h.calls.length, 1);
  for (const response of [jsonResponse({ detail: 'Other conflict' }, 409), jsonResponse({ detail: 'Re-upload your profile picture to finish the security update.', token: 'secret' }, 409),
    jsonResponse({ detail: 'Re-upload your profile picture to finish the security update.' }, 409, { 'Cache-Control': 'public, max-age=300' })]) {
    const f = harness({ fetcher: async () => response }); const value = await f.read();
    assert.equal(value.avatar_reupload_required, false); assert.ok(value.avatar_error); assert.equal(value.avatar_data_uri, null);
  }
});

test('malformed issuance identity, URL, expiry, token and exact fields never reach bytes', async () => {
  for (const changes of [{ resource_kind: 'video' }, { resource_id: NEXT }, { urls: { avatar: 'https://evil.invalid/avatar' } },
    { urls: { avatar: ROOT + 'avatar?token=secret' } }, { expires_in: 301 }, { expires_in: 1 },
    { expires_at: 'yesterday' }, { expires_at: new Date(Date.now() - 1).toISOString() },
    { media_grant: GRANT.slice(0, -1) + 'B' }, { media_grant: 'short' }, { unknown: true }]) {
    const h = harness({ fetcher: async () => jsonResponse(issuance(changes)) });
    const value = await h.read(); assert.equal(value.avatar_data_uri, null); assert.ok(value.avatar_error); assert.equal(h.calls.length, 1);
  }
});

test('issuance headers, redirects, oversize bodies, missing stream and JSON failures deny', async () => {
  const redirected = jsonResponse(); Object.defineProperty(redirected, 'redirected', { value: true });
  for (const response of [redirected, jsonResponse(issuance(), 200, { 'Content-Type': 'text/plain' }),
    jsonResponse(issuance(), 200, { 'Cache-Control': 'no-store' }), new Response('x'.repeat(8193), { headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } }),
    new Response('{', { headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } }),
    new Response(null, { headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } })]) {
    const h = harness({ fetcher: async () => response }); const value = await h.read();
    assert.equal(value.avatar_data_uri, null); assert.ok(value.avatar_error); assert.equal(h.calls.length, 1);
  }
});

test('byte type, size, no-store/private policy and JPEG framing failures deny data-image delivery', async () => {
  const redirected = imageResponse(); Object.defineProperty(redirected, 'redirected', { value: true });
  for (const response of [redirected, imageResponse(JPEG, { 'Content-Type': 'image/png' }), imageResponse(JPEG, { 'Content-Length': '524289' }),
    imageResponse(JPEG, { 'Content-Length': '5' }), imageResponse(JPEG, { 'Content-Length': '7' }), imageResponse(JPEG, { 'Cache-Control': 'public,no-store' }),
    imageResponse(JPEG, { 'Cache-Control': 'private,max-age=60' }), imageResponse(new Uint8Array([1, 2, 3, 4])), imageResponse(JPEG, {}, 206)]) {
    const h = harness({ fetcher: async (_url, _init, at) => at === 0 ? jsonResponse() : response });
    const value = await h.read(); assert.equal(value.avatar_data_uri, null); assert.ok(value.avatar_error);
  }
});

test('configured backend drift and private/plaintext targets never leak credentials', async () => {
  for (const backend of ['http://api.usepeso.com', 'https://localhost', 'https://127.0.0.1', 'https://api.usepeso.com/?query=secret', 'https://user:password@api.usepeso.com']) {
    const h = harness(); h.changeBackend(backend); const value = await h.read(); assert.ok(value.avatar_error); assert.deepEqual(h.calls, []);
  }
  let h; h = harness({ fetcher: async () => { h.changeBackend('https://other.invalid'); return jsonResponse(); } });
  assert.ok((await h.read()).avatar_error); assert.equal(h.calls.length, 1);
});

for (const phase of ['issue', 'bytes']) {
  test('session release aborts and rejects late ' + phase + ' results', async () => {
    const waiting = deferred(); const h = harness({ fetcher: async (_u, _i, at) => phase === 'issue' || at === 1 ? waiting.promise : jsonResponse() });
    const op = h.module.beginProfileAvatarOperation(); const work = h.read(REV, op.assertCurrent);
    await new Promise(setImmediate); h.release();
    waiting.resolve(phase === 'issue' ? jsonResponse() : imageResponse());
    await assert.rejects(work, /profile changed/); assert.ok(h.calls.every(([, init]) => init.signal.aborted));
  });
}

test('deadline settles stalled headers and stalled body even when transport ignores abort', async () => {
  for (const phase of ['headers', 'body']) {
    const waiting = deferred();
    const hanging = new Response(new ReadableStream({ pull: () => waiting.promise }), { headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } });
    const h = harness({ fakeTimer: true, fetcher: async () => phase === 'headers' ? waiting.promise : hanging });
    const work = h.read(); await new Promise(setImmediate); h.timers[0]();
    const value = await work; assert.equal(value.avatar_data_uri, null); assert.ok(value.avatar_error);
    assert.ok(h.calls[0][1].signal.aborted); waiting.resolve();
  }
});

test('local mutation and observed metadata revisions invalidate older readers and clear subscribers', () => {
  const h = harness(); let cleared = 0; h.module.subscribeProfileAvatarRelease(() => cleared++);
  const old = h.module.beginProfileAvatarOperation(); old.observe(KEY, REV);
  const loadBeforeMutation = h.module.beginProfileAvatarOperation();
  const write = h.module.beginProfileAvatarOperation(true); assert.throws(loadBeforeMutation.assertCurrent, /changed/);
  assert.throws(() => h.module.beginProfileAvatarOperation(true), /in progress/);
  const loadDuringMutation = h.module.beginProfileAvatarOperation(); assert.throws(loadDuringMutation.assertCurrent, /changed/);
  write.observe(KEY, NEXT); write.assertCurrent(); write.finish();
  assert.throws(loadDuringMutation.assertCurrent, /changed/);
  const first = h.module.beginProfileAvatarOperation(); const second = h.module.beginProfileAvatarOperation();
  second.observe(KEY, NEXT); assert.throws(() => first.observe(KEY, REV), /changed/);
  const changing = h.module.beginProfileAvatarOperation(); changing.observe(KEY, REV);
  assert.throws(second.assertCurrent, /changed/); assert.equal(cleared, 4);
});

test('caller cancellation settles a stuck body without waiting for a late network completion', async () => {
  const waiting = deferred(); const h = harness({ fetcher: async () => waiting.promise });
  const controller = new AbortController();
  const work = h.module.readProfileAvatar('original-token', REV, () => {}, controller.signal);
  await new Promise(setImmediate); controller.abort();
  await assert.rejects(work, /cancelled/); assert.ok(h.calls[0][1].signal.aborted);
  waiting.resolve(jsonResponse());
});

const ATTEMPT = '55555555-5555-4555-8555-555555555555';
const DETAILS = { username: 'nathan', display_name: 'Nathan' };
const USER = { id: OWNER, email: 'nathan@example.invalid', user_metadata: {} };
function profileRecord(revision = REV) {
  return { id: OWNER, ...DETAILS, avatar_path: OWNER + '/avatar-' + ATTEMPT + '.jpg',
    created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-01T10:01:00Z', profile_revision: revision };
}
function profileModule(h, api = {}) {
  return load('../lib/profile.ts', {
    'expo-constants': { appOwnership: 'expo', AppOwnership: { Expo: 'expo' } },
    'react-native': { Platform: { OS: 'ios' } },
    './supabase': { supabaseAuthUrl: 'https://auth.invalid/auth/v1' },
    './avatarReader': h.module,
    './privateMediaLifecycle': { getPrivateMediaEpoch: () => 0, getActivePrivateMediaSessionKey: () => KEY },
    './privateMediaLogout': { getPrivateMediaSessionKey: token => token === 'original-token' ? KEY : null },
    './profilePolicy': require('../lib/profilePolicy'),
    './backendApi': { BackendHttpError: class extends Error {}, fetchOwnProfileMetadata: async () => ({ profile: profileRecord() }),
      updateOwnProfileMetadata: async () => profileRecord(NEXT), ...api },
  });
}

test('actual profile and reader modules discard metadata loaded before a confirmed local profile mutation', async () => {
  const waiting = deferred(); const h = harness({ enabled: false });
  const profile = profileModule(h, { fetchOwnProfileMetadata: () => waiting.promise });
  const stale = profile.loadOwnProfile(USER, 'original-token');
  await new Promise(setImmediate);
  const saved = await profile.saveOwnProfile(USER, 'original-token', REV, DETAILS);
  assert.equal(saved.profile_revision, NEXT); assert.equal(saved.avatar_data_uri, null);
  waiting.resolve({ profile: profileRecord() });
  await assert.rejects(stale, /profile changed/); assert.deepEqual(h.calls, []);
});

test('actual profile module preserves committed metadata when image transport is unavailable, and does not retry writes', async () => {
  let writes = 0;
  const h = harness({ fetcher: async () => { throw new Error('Synthetic bearer-token-secret'); } });
  const profile = profileModule(h, { updateOwnProfileMetadata: async () => { writes++; return profileRecord(NEXT); } });
  const saved = await profile.saveOwnProfile(USER, 'original-token', REV, DETAILS);
  assert.equal(writes, 1); assert.equal(saved.profile_revision, NEXT);
  assert.equal(saved.avatar_data_uri, null); assert.equal(saved.avatar_reupload_required, false);
  assert.ok(saved.avatar_error); assert.ok(!saved.avatar_error.includes('secret'));
});

test('actual profile module classifies exact legacy avatar without hiding editable metadata', async () => {
  const h = harness({ fetcher: async () => jsonResponse({ detail: 'Re-upload your profile picture to finish the security update.' }, 409) });
  const profile = profileModule(h);
  const loaded = await profile.loadOwnProfile(USER, 'original-token');
  assert.equal(loaded.username, DETAILS.username); assert.equal(loaded.profile_revision, REV);
  assert.equal(loaded.avatar_reupload_required, true); assert.equal(loaded.avatar_data_uri, null);
});

test('a newly observed metadata revision clears another mounted image without a whole-session release', async () => {
  const h = harness({ enabled: false }); let clears = 0;
  h.module.subscribeProfileAvatarRelease(() => clears++);
  let revision = REV;
  const profile = profileModule(h, { fetchOwnProfileMetadata: async () => ({ profile: profileRecord(revision) }) });
  await profile.loadOwnProfile(USER, 'original-token'); const first = clears;
  await profile.loadOwnProfile(USER, 'original-token'); assert.equal(clears, first);
  revision = NEXT; const current = await profile.loadOwnProfile(USER, 'original-token');
  assert.equal(clears, first + 1); assert.equal(current.profile_revision, NEXT); assert.deepEqual(h.calls, []);
});


test('empty byte chunks cannot create an unbounded retained chunk list, and one-byte chunks still reconstruct the bounded image', async () => {
  for (const empty of [true, false]) {
    let index = 0;
    const body = new ReadableStream({ pull(controller) {
      if (empty) { controller.enqueue(new Uint8Array()); return; }
      if (index === JPEG.length) controller.close();
      else controller.enqueue(JPEG.subarray(index, ++index));
    } });
    const streamed = new Response(body, { headers: { 'Content-Type': 'image/jpeg', 'Content-Length': '' + JPEG.length, 'Cache-Control': CACHE } });
    const h = harness({ fetcher: async (_u, _i, at) => at === 0 ? jsonResponse() : streamed });
    const value = await h.read();
    if (empty) { assert.equal(value.avatar_data_uri, null); assert.ok(value.avatar_error); }
    else assert.equal(value.avatar_data_uri, 'data:image/jpeg;base64,' + Buffer.from(JPEG).toString('base64'));
  }
});

test('each incoming chunk is copied before a later native read can reuse its buffer', async () => {
  let index = 0; const reused = new Uint8Array(1);
  const response = { status: 200, redirected: false,
    headers: new Headers({ 'Content-Type': 'image/jpeg', 'Content-Length': '' + JPEG.length, 'Cache-Control': CACHE }),
    body: { getReader: () => ({
      async read() {
        if (index === JPEG.length) { reused[0] = 0; return { done: true }; }
        reused[0] = JPEG[index++]; return { done: false, value: reused };
      },
      async cancel() {}, releaseLock() {},
    }) },
  };
  const h = harness({ fetcher: async (_u, _i, at) => at === 0 ? jsonResponse() : response });
  const value = await h.read();
  assert.equal(value.avatar_data_uri, 'data:image/jpeg;base64,' + Buffer.from(JPEG).toString('base64'));
});
