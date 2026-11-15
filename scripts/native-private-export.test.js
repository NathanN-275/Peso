const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const VIDEO = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const ANALYSIS = '33333333-3333-4333-8333-333333333333';
const FILE = '44444444-4444-4444-8444-444444444444';
const URI = 'file:///cache/peso-private-export-v1/' + FILE + '/asset.mov';
const OPTIONS = { pose: false, barbell: false };
const tick = () => new Promise(setImmediate);
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function load(file, mocks, timers = {}) {
  const source = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
  const module = { exports: {} };
  const result = ts.transpileModule(source, {
    fileName: file, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  assert.deepEqual(result.diagnostics.map(d => ({ code: d.code, message: ts.flattenDiagnosticMessageText(d.messageText, '\n') })), []);
  new Function('require', 'module', 'exports', 'process', 'setTimeout', 'clearTimeout', result.outputText)(name => {
    assert.ok(Object.hasOwn(mocks, name), name);
    return mocks[name];
  }, module, module.exports, { env: { EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'true' } },
  timers.setTimeout ?? setTimeout, timers.clearTimeout ?? clearTimeout);
  return module.exports;
}

function fixture(overrides = {}) {
  const events = [];
  const saved = [];
  const releases = new Set();
  const external = new AbortController();
  let epoch = 0;
  let backend = overrides.backend ?? 'https://api.usepeso.com';
  const files = {
    reserve() { events.push('reserve'); return FILE; },
    cancel(id) { assert.equal(id, FILE); events.push('cancel'); overrides.cancel?.(); },
    remove(id) { assert.equal(id, FILE); events.push('remove'); overrides.remove?.(); },
    async download(id, url, grant) {
      assert.equal(id, FILE);
      assert.match(url, /^https:\/\/api\.usepeso\.com\/private-media\/video\//);
      assert.equal(grant, 'synthetic-media-grant');
      events.push('download');
      return overrides.download ? overrides.download() : URI;
    },
  };
  const lifecycle = load('lib/privateMediaLifecycle.js', {});
  const api = load('lib/nativePrivateVideoExport.ts', {
    'expo/fetch': { async fetch(url, init) {
      const id = new URL(url).pathname.split('/')[2];
      assert.equal(url, backend + '/videos/' + id + '/analyzed-export');
      assert.equal(init.headers.Authorization, 'Bearer account-token');
      assert.equal(init.headers['X-Peso-Media-Grant'], undefined);
      assert.equal(init.credentials, 'omit');
      assert.equal(init.redirect, 'error');
      assert.deepEqual(JSON.parse(init.body), OPTIONS);
      events.push(['prepare', id, init.signal]);
      if (overrides.prepareResponse) return overrides.prepareResponse();
      const value = overrides.prepare ? await overrides.prepare(id) :
        { video_id: id, analysis_id: ANALYSIS, variant: 'clean', storage_path: null, export_url: null };
      return Response.json(value);
    } },
    './videoRequestPayloadPolicy': require('../lib/videoRequestPayloadPolicy'),
    './backendConfig': { getBackendApiUrl: () => backend },
    './privateExportFiles': { getPrivateExportFiles: () => files },
    './privateMediaLifecycle': {
      getActivePrivateMediaSessionKey: () => 'owner:accepted',
      getPrivateMediaEpoch: () => epoch,
      registerPrivateMediaRelease(callback) {
        releases.add(callback);
        const unregister = lifecycle.registerPrivateMediaRelease(callback);
        return () => { releases.delete(callback); unregister(); };
      },
    },
    './privateMediaLogout': { getPrivateMediaSessionKey: token => token === 'account-token' ? 'owner:accepted' : null },
    './privateVideoPlayback': { async issueNativePrivateDownload(id, token, variant) {
      assert.equal(token, 'account-token');
      assert.equal(variant, 'clean');
      events.push(['issue', id]);
      return { uri: 'https://api.usepeso.com/private-media/video/' + id + '/export%3Aclean',
        grant: 'synthetic-media-grant', assertCurrent() {} };
    } },
    './profilePolicy': { isCanonicalUuid: value => typeof value === 'string' && /^[a-f0-9-]{36}$/.test(value) },
    './supabase': { supabaseAuthUrl: 'https://fixture.invalid/auth/v1' },
  }, overrides.timers);
  return {
    events, saved, releases, external,
    run: (ids = [VIDEO]) => api.savePrivateVideoExports(ids, 'account-token', OPTIONS, 'clean',
      async uri => {
        assert.equal(uri, URI);
        events.push('save');
        await overrides.save?.();
      }, id => saved.push(id), external.signal),
    release() { epoch++; return lifecycle.releasePrivateMedia(); },
    switchBackend() { backend = 'https://other.usepeso.com'; },
  };
}
const kinds = events => events.map(value => Array.isArray(value) ? value[0] : value);

test('native exports prepare, issue, save and clear each file in selection order', async () => {
  const f = fixture();
  await f.run([VIDEO, OTHER]);
  assert.deepEqual(kinds(f.events),
    ['prepare','issue','reserve','download','save','remove','prepare','issue','reserve','download','save','remove']);
  assert.equal(f.events[0][1], VIDEO);
  assert.equal(f.events[6][1], OTHER);
  assert.deepEqual(f.saved, [VIDEO, OTHER]);
  assert.equal(f.releases.size, 0);
});

test('legacy provider URLs and substituted metadata never reach the private download issuer', async () => {
  for (const change of [{ export_url: 'https://fixture.invalid/signed' }, { storage_path: 'provider-path' },
    { variant: 'pose' }, { video_id: OTHER }, { analysis_id: 'invalid' }]) {
    const f = fixture({ prepare: id => ({ video_id: id, analysis_id: ANALYSIS, variant: 'clean',
      storage_path: null, export_url: null, ...change }) });
    await assert.rejects(f.run(), /Unable to save/);
    assert.deepEqual(kinds(f.events), ['prepare']);
  }
});

test('session release cancels native transfer and waits for settlement before deleting its file', async () => {
  const transfer = deferred();
  const f = fixture({ download: () => transfer.promise, cancel: () => { throw new Error('fixture cancel failure'); } });
  const work = f.run([VIDEO, OTHER]);
  void work.catch(() => {});
  await tick();
  let released = false;
  const release = f.release().then(() => { released = true; });
  await tick();
  assert.equal(released, false);
  assert.deepEqual(kinds(f.events), ['prepare','issue','reserve','download','cancel']);
  transfer.resolve(URI);
  await assert.rejects(work, /Unable to save/);
  await release;
  assert.deepEqual(kinds(f.events), ['prepare','issue','reserve','download','cancel','remove']);
});

test('release during a user library save joins the save and prevents the next item', async () => {
  const library = deferred();
  const f = fixture({ save: () => library.promise });
  const work = f.run([VIDEO, OTHER]);
  void work.catch(() => {});
  await tick();
  const release = f.release();
  await tick();
  assert.deepEqual(kinds(f.events), ['prepare','issue','reserve','download','save','cancel']);
  library.resolve();
  await assert.rejects(work);
  await release;
  assert.deepEqual(kinds(f.events), ['prepare','issue','reserve','download','save','cancel','remove']);
});

test('cleanup failure remains registered and blocks new work until retry clears the exact reservation', async () => {
  let diskFailure = true;
  const f = fixture({ remove() { if (diskFailure) throw new Error('fixture unlink'); } });
  await assert.rejects(f.run(), /Unable to clear/);
  assert.equal(f.releases.size, 1);
  assert.deepEqual(f.saved, [VIDEO]);
  await assert.rejects(f.run(), /Unable to clear/);
  await assert.rejects(f.release(), /Unable to release/);
  assert.equal(f.releases.size, 1);
  diskFailure = false;
  await f.release();
  assert.equal(f.releases.size, 0);
  assert.equal(kinds(f.events).filter(event => event === 'prepare').length, 1);
});

test('screen cancellation and backend changes reject a late preparation before any bytes', async () => {
  for (const change of [f => f.external.abort(), f => f.switchBackend()]) {
    const preparation = deferred();
    const f = fixture({ prepare: () => preparation.promise });
    const work = f.run();
    void work.catch(() => {});
    await tick();
    change(f);
    preparation.resolve({ video_id: VIDEO, analysis_id: ANALYSIS, variant: 'clean', export_url: null, storage_path: null });
    await assert.rejects(work, /Unable to save/);
    assert.deepEqual(kinds(f.events), ['prepare']);
    assert.equal(f.releases.size, 0);
  }
});

test('a native file URL outside the reserved cache directory never reaches the library', async () => {
  const f = fixture({ download: () => 'file:///cache/foreign/asset.mov' });
  await assert.rejects(f.run(), /Unable to save/);
  assert.deepEqual(kinds(f.events), ['prepare','issue','reserve','download','remove']);
});

test('startup purge retries failed cleanup and never requires a native module on web', () => {
  let attempts = 0;
  const removed = [];
  class File {
    constructor(name) { this.name = name; }
    delete() { removed.push(this.name); }
  }
  const legacy = new File('peso-Side-Squat-pose-barbell-11111111-2.mp4');
  const unrelated = new File('peso-video-cache.mp4');
  const shadowDirectory = { name: 'peso-Squat-clean-11111111-1.mp4' };
  const files = { purgeOnStartup() { if (++attempts === 1) throw new Error('fixture cleanup failure'); } };
  const api = load('lib/privateExportFiles.ts', {
    expo: { requireOptionalNativeModule: () => files }, 'react-native': { Platform: { OS: 'ios' } },
    'expo-file-system': { File, Paths: { cache: { list: () => [legacy, unrelated, shadowDirectory] } } },
  });
  assert.throws(api.ensurePrivateExportStartupCleanup, /cleanup failure/);
  assert.deepEqual(removed, []);
  api.ensurePrivateExportStartupCleanup();
  api.ensurePrivateExportStartupCleanup();
  assert.equal(attempts, 2);
  assert.deepEqual(removed, [legacy.name]);
  const web = load('lib/privateExportFiles.ts', {
    expo: { requireOptionalNativeModule() { assert.fail('loaded a native module on web'); } },
    'react-native': { Platform: { OS: 'web' } }, 'expo-file-system': {},
  });
  web.ensurePrivateExportStartupCleanup();
});

test('an unapproved backend is rejected before preparation or native download', async () => {
  const invalid = fixture({ backend: 'https://usepeso.com.fixture.invalid' });
  await assert.rejects(invalid.run(), /Unable to save/);
  assert.deepEqual(invalid.events, []);
});

for (const stop of ['release', 'deadline']) {
  test('preparation ' + stop + ' settles after headers with a stalled metadata body', async () => {
    const timers = [];
    const f = fixture({
      prepareResponse: () => new Response(new ReadableStream({ pull: () => new Promise(() => {}) }), {
        headers: { 'Content-Type': 'application/json' },
      }),
      timers: {
        setTimeout(callback, ms) { assert.equal(ms, 300000); timers.push(callback); return 1; },
        clearTimeout() {},
      },
    });
    const work = f.run();
    void work.catch(() => {});
    await tick();
    if (stop === 'release') await f.release();
    else timers[0]();
    await assert.rejects(work, /Unable to save/);
    assert.equal(f.events[0][2].aborted, true);
    assert.deepEqual(kinds(f.events), ['prepare']);
    assert.equal(f.releases.size, 0);
  });
}

test('oversized preparation metadata never starts a native operation', async () => {
  const f = fixture({
    prepareResponse: () => new Response('x'.repeat(8193), { headers: { 'Content-Type': 'application/json' } }),
  });
  await assert.rejects(f.run(), /Unable to save/);
  assert.deepEqual(kinds(f.events), ['prepare']);
});
