const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const tick = () => new Promise(setImmediate);
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }

// Deterministic React hook scheduling around actual Peso source; no installed Auth
// client, browser profile, account or provider traffic is involved.
function fixture({ privateMedia = true, issue } = {}) {
  const slots = [], pendingEffects = [], releases = new Set(), timers = [], calls = [];
  let rendering = false, cursor = 0, epoch = 0, session = 'owner:session-A', backend = 'https://api.usepeso.com';
  let props = ['video-A', 'token-A', null];
  const changed = (a, b) => !a || !b || a.length !== b.length || a.some((value, index) => !Object.is(value, b[index]));
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[index].value, value => { slots[index].value = typeof value === 'function' ? value(slots[index].value) : value; }];
    },
    useRef(value) { const index = cursor++; if (!slots[index]) slots[index] = { current: value }; return slots[index]; },
    useCallback(fn, dependencies) { const index = cursor++; if (!slots[index] || changed(slots[index].dependencies, dependencies)) slots[index] = { dependencies, fn }; return slots[index].fn; },
    useEffect(fn, dependencies) {
      const index = cursor++;
      if (!slots[index] || changed(slots[index].dependencies, dependencies)) {
        const previous = slots[index]; slots[index] = { dependencies, cleanup: null };
        pendingEffects.push(() => { previous?.cleanup?.(); slots[index].cleanup = fn(); });
      }
    },
  };
  for (const [name, hook] of Object.entries(react)) react[name] = (...args) => { assert.equal(rendering, true, name + ' called outside render'); return hook(...args); };
  const lease = (id, at) => {
    const capturedEpoch = epoch, capturedSession = session, capturedBackend = backend;
    return { source: { uri: 'https://api.usepeso.com/private/' + id, headers: { 'X-Peso-Media-Grant': 'grant-' + at } }, expiresAt: Date.now() + 120000,
      assertCurrent() { if (capturedEpoch !== epoch || capturedSession !== session || capturedBackend !== backend) throw new Error('stale'); } };
  };
  const imports = {
    react, './backendConfig': { getBackendApiUrl: () => backend },
    './privateMediaLifecycle': { getPrivateMediaEpoch: () => epoch, getActivePrivateMediaSessionKey: () => session,
      registerPrivateMediaRelease(fn) { releases.add(fn); return () => releases.delete(fn); } },
    './backendApi': { async getVideoPlaybackUrl(id, token, signal) { calls.push(['legacy', id, token, signal]); return { video_url: 'https://provider.invalid/legacy', expires_in: 120 }; } },
    './privateVideoPlayback': { VIDEO_PLAYBACK_FAILURE: 'Retry playback', async issuePrivateVideoPlayback(id, token, signal) {
      calls.push(['private', id, token, signal]); return issue ? issue(id, token, signal, () => lease(id, calls.length)) : lease(id, calls.length);
    } },
  };
  const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/useVideoPlayback.ts'), 'utf8'), {
    reportDiagnostics: true, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  assert.deepEqual(compiled.diagnostics, []);
  const module = { exports: {} };
  new Function('require', 'module', 'exports', 'process', 'setTimeout', 'clearTimeout', compiled.outputText)(name => {
    assert.ok(Object.hasOwn(imports, name), name); return imports[name];
  }, module, module.exports, { env: { EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: String(privateMedia) } },
  (fn, delay) => { const timer = { fn, delay, cleared: false }; timers.push(timer); return timer; }, timer => { if (timer) timer.cleared = true; });
  const render = () => {
    cursor = 0; rendering = true; let value;
    try { value = module.exports.useVideoPlayback(...props); } finally { rendering = false; }
    for (const effect of pendingEffects.splice(0)) effect(); return value;
  };
  return { render, calls, timers, setProps: value => { props = value; },
    changeSession: () => { session = 'owner:session-B'; }, changeBackend: () => { backend = 'https://other.usepeso.com'; },
    release: () => { epoch++; for (const fn of [...releases]) fn(); },
    unmount: () => { for (const slot of slots) slot.cleanup?.(); },
  };
}

test('actual playback hook uses the private issuer once and never falls through to raw URLs', async () => {
  const f = fixture(); assert.equal(f.render().source, null); await tick();
  const view = f.render(); assert.equal(view.loading, false); assert.equal(view.privateRemote, true);
  assert.equal(view.source.headers['X-Peso-Media-Grant'], 'grant-1');
  for (let i = 0; i < 4; i++) f.render();
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0][0], 'private'); f.unmount();
});

for (const reason of ['expiry', 'decoder error']) {
  test(reason + ' permits one automatic renewal, then explicit Retry without a request loop', async () => {
    const f = fixture(); f.render(); await tick(); let view = f.render();
    if (reason === 'expiry') f.timers.at(-1).fn(); else view.onPlaybackError();
    // Duplicate events from the old decoder cannot spend the next request's budget.
    view.onPlaybackError(); f.render(); await tick(); view = f.render();
    assert.equal(f.calls.length, 2); assert.equal(view.source.headers['X-Peso-Media-Grant'], 'grant-2');
    if (reason === 'expiry') f.timers.at(-1).fn(); else view.onPlaybackError();
    view = f.render(); assert.equal(view.source, null); assert.equal(view.error, 'Retry playback');
    for (let i = 0; i < 4; i++) { view.onPlaybackError(); f.render(); }
    assert.equal(f.calls.length, 2);
    view.retry(); f.render(); await tick(); view = f.render();
    assert.equal(f.calls.length, 3); assert.ok(view.source); assert.equal(view.error, null); f.unmount();
  });
}

test('a delayed error callback from an older playback lease cannot discard its renewed source', async () => {
  const f = fixture(); f.render(); await tick(); const old = f.render();
  old.onPlaybackError(); f.render(); await tick(); const renewed = f.render();
  assert.equal(f.calls.length, 2); assert.ok(renewed.source);
  old.onPlaybackError(); assert.ok(f.render().source); assert.equal(f.calls.length, 2);
  f.unmount();
});

test('network failure offers Retry and makes no automatic fallback request', async () => {
  const f = fixture({ issue: async () => { throw new Error('sensitive upstream error'); } });
  f.render(); await tick(); const view = f.render(); assert.equal(view.source, null);
  assert.equal(view.error, 'Retry playback'); assert.equal(f.calls.length, 1); assert.equal(f.calls[0][0], 'private'); f.unmount();
});

for (const transition of ['release', 'changeSession', 'changeBackend', 'unmount']) {
  test(transition + ' rejects an ignored-abort late issuer and releases its request', async () => {
    const wait = deferred(); const f = fixture({ issue: async (_id, _token, _signal, lease) => { const original = lease(); await wait.promise; return original; } });
    f.render(); await tick(); f[transition]();
    if (transition !== 'unmount') f.render();
    wait.resolve(); await tick();
    if (transition !== 'unmount') {
      // New context issuance may succeed; a late old resource is never adopted.
      const view = f.render(); if (view.lease) assert.doesNotThrow(view.lease.assertCurrent);
    }
    assert.equal(f.calls[0][3].aborted, true); f.unmount();
  });
}

test('rapid resource navigation cannot install the prior video or its timer', async () => {
  const wait = deferred(); const f = fixture({ issue: async (id, _token, _signal, lease) => { const value = lease(); if (id === 'video-A') await wait.promise; return value; } });
  f.render(); f.setProps(['video-B', 'token-A', null]); f.render(); await tick();
  assert.ok(f.render().source.uri.endsWith('video-B')); wait.resolve(); await tick();
  assert.ok(f.render().source.uri.endsWith('video-B')); assert.equal(f.calls.length, 2); f.unmount();
});

test('local recordings make no issuer request and cannot reactivate across session release', async () => {
  const f = fixture(); f.setProps(['video-A', 'token-A', 'file:///owned-recording.mp4']);
  assert.equal(f.render().source, 'file:///owned-recording.mp4'); assert.equal(f.calls.length, 0);
  f.release(); let view = f.render(); assert.equal(view.source, null); assert.ok(view.error);
  f.changeSession(); view = f.render(); assert.equal(view.source, null); assert.equal(f.calls.length, 0); f.unmount();
});

test('private mode refuses remote URLs supplied through the local recording prop', () => {
  const f = fixture(); f.setProps(['video-A', 'token-A', 'https://provider.invalid/old-signed-url']);
  assert.equal(f.render().source, null); assert.ok(f.render().error); assert.equal(f.calls.length, 0); f.unmount();
});

test('disabled private media retains the legacy development playback path', async () => {
  const f = fixture({ privateMedia: false }); f.render(); await tick();
  const view = f.render(); assert.equal(view.source.uri, 'https://provider.invalid/legacy');
  assert.equal(view.privateRemote, false); assert.deepEqual(f.calls.map(call => call[0]), ['legacy']); f.unmount();
});

test('actual review and Saved Lift callers consume the hook and send credentialed CORS at video elements', () => {
  const read = name => fs.readFileSync(path.join(__dirname, '..', name), 'utf8');
  for (const name of ['src/native-root.tsx', 'src/web/web-analysis-routes.tsx', 'src/web/web-app.tsx']) {
    assert.doesNotMatch(read(name), /get(?:Saved)?VideoPlaybackUrl/);
  }
  for (const name of ['src/screens/AnalysisReviewScreen.tsx', 'src/web/web-app.tsx']) {
    assert.match(read(name), /useVideoPlayback\(/);
    assert.match(read(name), /crossOrigin=\{playback\.privateRemote \? 'use-credentials'/);
    assert.match(read(name), /Retry playback/);
  }
  assert.match(read('src/screens/AnalysisReviewScreen.tsx'), /attachPrivateMediaSource/);
  assert.match(read('src/screens/UploadVideoScreen.tsx'), /videoUri=\{selectedVideo\.uri\}/);
});


test('an old playback error after same-session token refresh cannot discard the new lease', async () => {
  const f = fixture(); f.render(); await tick(); const old = f.render();
  f.setProps(['video-A', 'rotated-token-A', null]); f.render(); await tick(); const refreshed = f.render();
  assert.equal(f.calls.length, 2); assert.ok(refreshed.source);
  old.onPlaybackError(); assert.ok(f.render().source); assert.equal(f.calls.length, 2); f.unmount();
});
