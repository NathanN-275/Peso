const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const OWNER = '11111111-1111-4111-8111-111111111111';
const SID = '22222222-2222-4222-8222-222222222222';
const VIDEO = '33333333-3333-4333-8333-333333333333';
const OTHER = '44444444-4444-4444-8444-444444444444';
const KEY = OWNER + ':' + SID;
const BACKEND = 'https://api.usepeso.com';
const GRANT = Buffer.alloc(32, 7).toString('base64url');
const ASSETS = ['export:barbell', 'export:clean', 'export:pose', 'export:pose-barbell', 'playback', 'thumbnail'];
const CACHE = 'private, no-store, max-age=0';
const NOW = Date.parse('2026-08-05T12:00:00.000Z');
const tick = () => new Promise(setImmediate);
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
// Only Peso source executes. These fixtures never import an Auth SDK or contact a provider.
function load(relative, imports, globals = {}) {
  const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', relative), 'utf8'), {
    reportDiagnostics: true, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  assert.deepEqual(compiled.diagnostics, []);
  const module = { exports: {} };
  new Function('require', 'module', 'exports', ...Object.keys(globals), compiled.outputText)(name => {
    assert.ok(Object.hasOwn(imports, name), 'Unexpected import ' + name); return imports[name];
  }, module, module.exports, ...Object.values(globals));
  return module.exports;
}
function issuerFixture({ browser = false, fetcher, fakeTimers = false, enabled = true, elapsedSeconds = 0 } = {}) {
  let epoch = 0, active = KEY, backend = BACKEND;
  const releases = new Set(), timers = [], calls = [];
  const root = BACKEND + '/private-media/' + (browser ? 'session/' + SID + '/' : '') + 'video/' + VIDEO + '/';
  const value = changes => ({ resource_kind: 'video', resource_id: VIDEO,
    urls: Object.fromEntries((browser ? ASSETS : ['playback']).map(asset => [asset, root + encodeURIComponent(asset)])),
    expires_in: 120, expires_at: new Date(NOW + 120000).toISOString(), ...(!browser ? { media_grant: GRANT } : {}), ...changes });
  const response = (changes, options = {}) => Response.json(value(changes), { headers: { 'Cache-Control': CACHE }, ...options });
  const api = load('lib/privateVideoPlayback.ts', {
    'expo/fetch': { fetch: async (url, init) => { calls.push([url, init]); return fetcher ? fetcher(url, init, response, value) : response(); } },
    'react-native': { Platform: { OS: browser ? 'web' : 'ios' } },
    './backendConfig': { getBackendApiUrl: () => backend }, './backendUrlPolicy': require('../lib/backendUrlPolicy'),
    './privateMediaLifecycle': { getPrivateMediaEpoch: () => epoch, getActivePrivateMediaSessionKey: () => active,
      registerPrivateMediaRelease: fn => { releases.add(fn); return () => releases.delete(fn); } },
    './privateMediaLogout': { getPrivateMediaSessionKey: token => token === 'original-token' ? KEY : null },
    './profilePolicy': require('../lib/profilePolicy'), './supabase': { supabaseAuthUrl: 'https://auth-fixture.invalid/auth/v1' },
  }, { Date: { now: () => NOW + elapsedSeconds * 1000, parse: Date.parse }, process: { env: { EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: String(enabled) } },
    setTimeout: fakeTimers ? fn => { timers.push(fn); return timers.length; } : setTimeout,
    clearTimeout: fakeTimers ? () => {} : clearTimeout });
  return { api, calls, root, timers, value, response,
    issue: (id = VIDEO, token = 'original-token', signal) => api.issuePrivateVideoPlayback(id, token, signal),
    release: () => { epoch++; for (const fn of releases) fn(); },
    changeOwner: () => { active = OTHER + ':' + SID; }, changeSession: () => { active = OWNER + ':' + OTHER; },
    changeBackend: value => { backend = value; }, revoke: () => { active = null; } };
}

for (const browser of [false, true]) {
  test((browser ? 'browser' : 'native') + ' issuer binds exact session/resource URLs and separates account and media credentials', async () => {
    const f = issuerFixture({ browser }); const lease = await f.issue();
    lease.assertCurrent(); assert.equal(lease.source.uri, f.root + 'playback');
    assert.equal(lease.source.useCaching, false); assert.equal(lease.source.contentType, 'progressive');
    assert.deepEqual(lease.source.headers, browser ? undefined : { 'X-Peso-Media-Grant': GRANT, 'Cache-Control': 'no-store' });
    assert.equal(f.calls.length, 1);
    const [url, init] = f.calls[0]; assert.equal(url, f.root + 'session');
    assert.equal(init.method, 'POST'); assert.equal(init.credentials, browser ? 'include' : 'omit');
    assert.equal(init.redirect, 'error'); assert.equal(init.keepalive, false);
    assert.equal(init.headers.Authorization, 'Bearer original-token');
    assert.equal(init.headers['X-Peso-Media-Grant'], undefined);
    assert.deepEqual(JSON.parse(init.body), { transport: browser ? 'browser' : 'native', asset_kinds: ['playback'] });
    assert.ok(!JSON.stringify(lease.source).includes('original-token'));
    if (browser) assert.ok(!JSON.stringify(lease.source).includes(GRANT));
    f.release(); assert.throws(lease.assertCurrent);
  });
  test((browser ? 'browser' : 'native') + ' rejects substituted identities, asset domains, provider URLs, credentials and expiry', async () => {
    const normal = issuerFixture({ browser });
    const cases = [null, [], { resource_id: OTHER }, { resource_kind: 'archive' }, { unknown: true },
      { urls: { ...normal.value().urls, playback: 'https://storage.invalid/signed?token=secret' } },
      { urls: { ...normal.value().urls, playback: normal.root + 'playback?token=secret' } },
      { urls: { ...normal.value().urls, playback: normal.root.replace(SID, OTHER) + 'playback' } },
      { urls: {} }, { urls: { ...normal.value().urls, extra: normal.root + 'extra' } },
      { expires_in: 0 }, { expires_in: 301 }, { expires_in: 1.5 }, { expires_in: 1 },
      { expires_at: 'tomorrow' }, { expires_at: new Date(NOW - 1000).toISOString() },
      { expires_at: new Date(NOW + 301000).toISOString(), expires_in: 300 },
      ...(browser ? [{ media_grant: GRANT }] : [{ media_grant: 'short' }, { media_grant: GRANT.slice(0, -1) + 'B' }])];
    for (const changes of cases) {
      const f = issuerFixture({ browser, fetcher: async (_u, _i, response) => changes === null || Array.isArray(changes)
        ? Response.json(changes, { headers: { 'Cache-Control': CACHE } }) : response(changes) });
      // The native path has no session namespace; that one substitution is a no-op there.
      if (!browser && changes?.urls?.playback === normal.root + 'playback' && Object.keys(changes).length === 1) continue;
      await assert.rejects(f.issue(), /Unable to load this video/); assert.equal(f.calls.length, 1);
    }
  });
}

test('unsafe or drifting backend, disabled transport, missing identity and malformed resource deny before account fetch', async () => {
  for (const backend of ['http://api.usepeso.com', 'https://localhost', 'https://127.0.0.1', 'https://user:pass@api.usepeso.com', 'https://api.usepeso.com/?query=secret', 'https://api.usepeso.com/#secret']) {
    const f = issuerFixture(); f.changeBackend(backend); await assert.rejects(f.issue()); assert.equal(f.calls.length, 0);
  }
  for (const id of ['AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA', 'invalid', '00000000-0000-0000-0000-000000000000', VIDEO + '/session']) {
    const f = issuerFixture(); await assert.rejects(f.issue(id)); assert.equal(f.calls.length, 0);
  }
  const off = issuerFixture({ enabled: false }); await assert.rejects(off.issue()); assert.equal(off.calls.length, 0);
  const f = issuerFixture(); f.revoke(); await assert.rejects(f.issue()); assert.equal(f.calls.length, 0);
});

test('redirect, wrong status/type/cache policy, absent body, oversized body and malformed JSON never return a source', async () => {
  for (const create of [f => f.response({}, { status: 409 }), f => f.response({}, { headers: { 'Cache-Control': 'private,max-age=60' } }),
    f => f.response({}, { headers: { 'Cache-Control': 'no-store' } }), f => f.response({}, { headers: { 'Content-Type': 'text/plain', 'Cache-Control': CACHE } }),
    () => new Response('{', { headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } }),
    () => new Response('x'.repeat(8193), { headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } }),
    () => new Response(null, { headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } }),
    f => { const r = f.response(); Object.defineProperty(r, 'redirected', { value: true }); return r; }]) {
    let f; f = issuerFixture({ fetcher: () => create(f) }); await assert.rejects(f.issue());
  }
});

for (const phase of ['headers', 'body']) {
  test('release, external cancellation and explicit deadline settle stalled ' + phase + ' without relying on transport abort', async () => {
    for (const cancellation of ['release', 'external', 'deadline']) {
      const wait = deferred(); let f;
      f = issuerFixture({ fakeTimers: true, fetcher: () => phase === 'headers' ? wait.promise : new Response(new ReadableStream({ pull: () => wait.promise }), {
        headers: { 'Content-Type': 'application/json', 'Cache-Control': CACHE } }) });
      const controller = new AbortController(); const work = f.issue(VIDEO, 'original-token', controller.signal);
      await tick();
      if (cancellation === 'release') f.release(); else if (cancellation === 'external') controller.abort(); else f.timers[0]();
      await assert.rejects(work); assert.equal(f.calls[0][1].signal.aborted, true);
      wait.resolve(phase === 'headers' ? f.response() : undefined); await tick();
    }
  });
}

test('owner, session and backend changes reject late headers and invalidate already-issued sources', async () => {
  for (const change of ['changeOwner', 'changeSession', 'changeBackend', 'release']) {
    const pending = deferred(); const f = issuerFixture({ fetcher: () => pending.promise });
    const work = f.issue(); await tick(); f[change]('https://other.invalid'); pending.resolve(f.response()); await assert.rejects(work);
    const g = issuerFixture(); const lease = await g.issue(); g[change]('https://other.invalid'); assert.throws(lease.assertCurrent);
  }
});

test('actual legacy API refuses playback minting when private media is enabled', async () => {
  // Existing backend adapter fixture tests exercise legacy cache behavior separately.
  const source = fs.readFileSync(path.join(__dirname, '../lib/backendApi.ts'), 'utf8');
  let calls = 0;
  const api = load('lib/backendApi.ts', {
    'react-native': { Platform: { OS: 'web' } }, './privateMediaLifecycle': require('../lib/privateMediaLifecycle'),
    './privateMediaLogout': require('../lib/privateMediaLogout'), './backendConfig': { getBackendApiUrl: () => BACKEND },
    './videoRequestPayloadPolicy': require('../lib/videoRequestPayloadPolicy'), './backendErrorPolicy': require('../lib/backendErrorPolicy'),
  }, { __DEV__: false, process: { env: { EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'true' } }, fetch: async () => { calls++; } });
  await assert.rejects(api.getVideoPlaybackUrl(VIDEO, 'token'), /private media session/);
  await assert.rejects(api.getSavedVideoPlaybackUrl(VIDEO, 'token'), /private media session/);
  assert.equal(calls, 0); assert.ok(source.includes('signal?: AbortSignal'));
});

test('source release waits for late replacement, clears it, and never delivers readiness', async () => {
  const { attachPrivateMediaSource, releasePrivateMedia } = require('../lib/privateMediaLifecycle');
  const wait = deferred(); const entered = deferred(); const events = []; let ready = 0, errors = 0;
  const source = { uri: 'https://synthetic.invalid/media', headers: { 'X-Peso-Media-Grant': 'fixture' } };
  const player = { pause() { events.push('pause'); }, async replaceAsync(value) { events.push(value); if (value) { entered.resolve(); await wait.promise; } } };
  const cleanup = attachPrivateMediaSource(player, source, () => {}, () => { ready++; }, () => { errors++; });
  await entered.promise; let released = false;
  const logout = releasePrivateMedia().then(() => { released = true; }); await tick(); assert.equal(released, false);
  wait.resolve(); await logout; assert.equal(events.at(-1), null); assert.equal(ready, 0); assert.equal(errors, 0); cleanup(); await tick();
});

test('serialized source replacement preserves newer clip and clears rejected or stale replacement', async () => {
  const { attachPrivateMediaSource } = require('../lib/privateMediaLifecycle');
  const wait = deferred(), entered = deferred(), events = [];
  const a = { uri: 'a' }, b = { uri: 'b' }; let current;
  const player = { pause() {}, async replaceAsync(value) { events.push(value); current = value; if (value === a) { entered.resolve(); await wait.promise; } } };
  const ca = attachPrivateMediaSource(player, a, () => {}, () => {}, () => {}); await entered.promise; ca();
  const ready = deferred(); const cb = attachPrivateMediaSource(player, b, () => {}, () => ready.resolve(), () => {});
  wait.resolve(); await ready.promise; assert.equal(current, b); cb(); await tick(); assert.equal(current, null);
  for (const fail of ['before', 'after', 'replace']) {
    const failed = deferred(); let checks = 0;
    const broken = { pause() {}, async replaceAsync(value) { current = value; if (value && fail === 'replace') throw new Error('synthetic partial replacement'); } };
    const cleanup = attachPrivateMediaSource(broken, b, () => { checks++; if (fail === 'before' || fail === 'after' && checks === 2) throw new Error('stale'); }, () => assert.fail('readiness after failure'), () => failed.resolve());
    await failed.promise; assert.equal(current, null); cleanup(); await tick();
  }
});

test('a failed player clear prevents media release acknowledgement', async () => {
  const { attachPrivateMediaSource, releasePrivateMedia } = require('../lib/privateMediaLifecycle');
  const player = { pause() {}, async replaceAsync() { throw new Error('fixture decoder clear failure'); } };
  const cleanup = attachPrivateMediaSource(player, null, () => {}, () => {}, () => {});
  await assert.rejects(releasePrivateMedia(), /Unable to release private media/); cleanup(); await tick();
});


test('elapsed transport time may shorten a valid lease without extending its absolute expiry', async () => {
  for (const browser of [false, true]) {
    const f = issuerFixture({ browser, elapsedSeconds: 10 }); const lease = await f.issue();
    lease.assertCurrent(); assert.equal(lease.expiresAt, NOW + 120000);
  }
});


test('unmount keeps an unfinished replacement registered until its final clear settles', async () => {
  const { attachPrivateMediaSource, releasePrivateMedia } = require('../lib/privateMediaLifecycle');
  const wait = deferred(), entered = deferred(); let current, released = false, ready = 0;
  const player = { pause() {}, async replaceAsync(value) { current = value; if (value) { entered.resolve(); await wait.promise; } } };
  const cleanup = attachPrivateMediaSource(player, { uri: 'synthetic-late' }, () => {}, () => { ready++; }, () => {});
  await entered.promise; cleanup();
  const logout = releasePrivateMedia().then(() => { released = true; }); await tick(); assert.equal(released, false);
  wait.resolve(); await logout; assert.equal(current, null); assert.equal(ready, 0);
});

test('browser prepares an exact authenticated export navigation without a credential in its link', async () => {
  const f = issuerFixture({ browser: true });
  const lease = await f.api.issueBrowserPrivateDownload({ kind: 'video', id: VIDEO, asset: 'export:pose-barbell' }, 'original-token');
  assert.equal(lease.href, f.root + 'download/export%3Apose-barbell');
  assert.deepEqual(Object.keys(lease).sort(), ['assertCurrent','expiresAt','href']);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0][0], f.root + 'session');
  assert.equal(f.calls[0][1].headers.Authorization, 'Bearer original-token');
  assert.deepEqual(JSON.parse(f.calls[0][1].body), { transport: 'browser', asset_kinds: ['export:pose-barbell'] });
  f.changeSession();
  assert.throws(lease.assertCurrent);
});

test('archive download only accepts the exact verified archive scope and asset URL', async () => {
  const root = BACKEND + '/private-media/session/' + SID + '/archive/' + VIDEO + '/';
  const target = { kind: 'archive', id: VIDEO, asset: 'archive' };
  for (const urls of [{ archive: root + 'archive' }, { archive: root + 'archive?token=secret' },
    { archive: root.replace(SID, OTHER) + 'archive' }, { archive: root + 'archive', extra: root + 'extra' }]) {
    const f = issuerFixture({ browser: true, fetcher: (_u,_i,response) => response({ resource_kind: 'archive', urls }) });
    const work = f.api.issueBrowserPrivateDownload(target,'original-token');
    if (urls.archive === root + 'archive' && !urls.extra) {
      const lease = await work;
      assert.equal(lease.href, root + 'download/archive');
      assert.equal(f.calls[0][0], root + 'session');
      f.release();
      assert.throws(lease.assertCurrent);
    } else {
      await assert.rejects(work, /Unable to prepare this download/);
    }
  }
});

test('download rejects native transport and invalid asset selectors before sending account credentials', async () => {
  const f = issuerFixture({ browser: true });
  const native = issuerFixture();
  for (const [fixture, target] of [[native,{ kind:'video',id:VIDEO,asset:'export:clean' }],
    [f,{ kind:'video',id:VIDEO,asset:'playback' }], [f,{ kind:'video',id:VIDEO,asset:'export:unknown' }],
    [f,{ kind:'archive',id:VIDEO,asset:'export:clean' }], [f,{ kind:'avatar',id:VIDEO,asset:'archive' }]]) {
    await assert.rejects(fixture.api.issueBrowserPrivateDownload(target,'original-token'), /Unable to prepare this download/);
    assert.equal(fixture.calls.length,0);
  }
});

test('native export issuer selects one exact asset and returns only the media grant to the downloader', async () => {
  const f = issuerFixture({ fetcher: (url, init, response) => {
    assert.equal(init.credentials, 'omit');
    assert.equal(init.headers.Authorization, 'Bearer original-token');
    assert.deepEqual(JSON.parse(init.body), { transport: 'native', asset_kinds: ['export:clean'] });
    return response({ urls: { 'export:clean': url.replace(/session$/, 'export%3Aclean') } });
  } });
  const lease = await f.api.issueNativePrivateDownload(VIDEO, 'original-token', 'clean');
  assert.equal(lease.uri, f.root + 'export%3Aclean');
  assert.equal(lease.grant, GRANT);
  assert.equal(Object.hasOwn(lease, 'accessToken'), false);
  f.release();
  assert.throws(lease.assertCurrent);

  const web = issuerFixture({ browser: true });
  await assert.rejects(web.api.issueNativePrivateDownload(VIDEO, 'original-token', 'clean'));
  assert.equal(web.calls.length, 0);
});
