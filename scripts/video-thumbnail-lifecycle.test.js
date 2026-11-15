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
  let props = ['video-A', true, 'token-A', null];
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
    return { dataUri: 'memory:' + id + ':' + capturedSession + ':' + at, expiresAt: Date.now() + 120000,
      assertCurrent() { if (capturedEpoch !== epoch || capturedSession !== session || capturedBackend !== backend) throw new Error('stale'); } };
  };
  const imports = {
    react, './backendConfig': { getBackendApiUrl: () => backend },
    './privateMediaLifecycle': { getPrivateMediaEpoch: () => epoch, getActivePrivateMediaSessionKey: () => session,
      registerPrivateMediaRelease(fn) { releases.add(fn); return () => releases.delete(fn); } },
    './privateVideoThumbnail': { THUMBNAIL_FAILURE: 'Preview unavailable', async readPrivateVideoThumbnail(id, token, signal) {
      calls.push(['private', id, token, signal]); return issue ? issue(id, token, signal, () => lease(id, calls.length)) : lease(id, calls.length);
    } },
  };
  const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/useVideoThumbnail.ts'), 'utf8'), {
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
    try { value = module.exports.useVideoThumbnail(...props); } finally { rendering = false; }
    for (const effect of pendingEffects.splice(0)) effect(); return value;
  };
  return { render, calls, timers, setProps: value => { props = value; },
    changeSession: () => { session = 'owner:session-B'; }, revoke: () => { session = null; }, changeBackend: () => { backend = 'https://other.usepeso.com'; },
    release: () => { session = null; epoch++; for (const fn of [...releases]) fn(); },
    unmount: () => { for (const slot of slots) slot.cleanup?.(); },
  };
}

test('actual thumbnail hook loads memory bytes once, ignores legacy capabilities and stays stable on renders', async () => {
  const f = fixture(); f.setProps(['video-A', true, 'token-A', 'https://provider.invalid/old']);
  assert.equal(f.render().uri, null); await tick(); const view = f.render();
  assert.equal(view.uri, 'memory:video-A:owner:session-A:1'); assert.equal(view.error, false);
  for (let i = 0; i < 5; i++) f.render(); assert.equal(f.calls.length, 1); f.unmount();
});

for (const reason of ['expiry', 'image error']) {
  test(reason + ' allows one automatic renewal then explicit Retry; older callbacks cannot discard a new preview', async () => {
    const f = fixture(); f.render(); await tick(); let view = f.render(); const old = view;
    if (reason === 'expiry') f.timers.at(-1).fn(); else view.onImageError();
    old.onImageError(); f.render(); await tick(); view = f.render();
    assert.equal(f.calls.length, 2); assert.ok(view.uri.endsWith(':2'));
    old.onImageError(); assert.ok(f.render().uri.endsWith(':2'));
    if (reason === 'expiry') f.timers.at(-1).fn(); else view.onImageError();
    view = f.render(); assert.equal(view.uri, null); assert.equal(view.error, true); assert.equal(f.calls.length, 2);
    view.retry(); f.render(); await tick(); assert.ok(f.render().uri.endsWith(':3')); assert.equal(f.calls.length, 3); f.unmount();
  });
}

test('availability false and missing sessions never issue or use a supplied provider URL', async () => {
  const f = fixture(); f.setProps(['video-A', false, 'token-A', 'https://provider.invalid/old']);
  assert.equal(f.render().uri, null); await tick(); assert.equal(f.calls.length, 0);
  f.setProps(['video-A', true, 'token-A', null]); f.revoke(); assert.equal(f.render().uri, null); await tick(); assert.equal(f.calls.length, 0); f.unmount();
});

test('read failure exposes only Retry and does not fall through to a legacy thumbnail URL', async () => {
  const f = fixture({ issue: async () => { throw new Error('sensitive fixture details'); } });
  f.setProps(['video-A', true, 'token-A', 'https://provider.invalid/old']); f.render(); await tick();
  const view = f.render(); assert.equal(view.uri, null); assert.equal(view.error, true); assert.equal(f.calls.length, 1); f.unmount();
});

for (const change of ['release', 'changeSession', 'changeBackend', 'unmount']) {
  test(change + ' aborts or invalidates late thumbnail work', async () => {
    const wait = deferred(); const f = fixture({ issue: async (_id, _token, _signal, lease) => { const original = lease(); await wait.promise; return original; } });
    f.render(); await tick(); f[change](); if (change !== 'unmount') f.render(); wait.resolve(); await tick();
    assert.equal(f.calls[0][3].aborted, true);
    if (change === 'changeSession') assert.ok(!f.render().uri?.includes('session-A'));
    if (change === 'release') assert.equal(f.render().uri, null);
    f.unmount();
  });
}

test('resource and availability changes cannot install an older in-flight preview', async () => {
  const wait = deferred(); const f = fixture({ issue: async (id, _token, _signal, lease) => { const value = lease(); if (id === 'video-A') await wait.promise; return value; } });
  f.render(); f.setProps(['video-B', true, 'token-A', null]); f.render(); await tick(); assert.ok(f.render().uri.includes('video-B'));
  wait.resolve(); await tick(); assert.ok(f.render().uri.includes('video-B'));
  f.setProps(['video-B', false, 'token-A', null]); assert.equal(f.render().uri, null); f.unmount();
});

test('private legacy URL changes do not restart memory reads or their renewal budget', async () => {
  const f = fixture(); f.render(); await tick(); f.render();
  f.setProps(['video-A', true, 'token-A', 'https://provider.invalid/first']); f.render(); await tick();
  f.setProps(['video-A', true, 'token-A', 'https://provider.invalid/second']); f.render(); await tick();
  assert.equal(f.calls.length, 1); f.unmount();
});

test('actual native and web thumbnail callers use the shared component and private metadata availability', () => {
  for (const name of ['src/screens/HomeScreen.tsx', 'src/screens/SavedLiftVideosScreen.tsx', 'src/web/web-app.tsx']) {
    const source = fs.readFileSync(path.join(__dirname, '..', name), 'utf8');
    assert.match(source, /VideoThumbnail/); assert.match(source, /thumbnail_available === true/);
    assert.doesNotMatch(source, /source=\{[^\n]*thumbnail_url/);
  }
  const component = fs.readFileSync(path.join(__dirname, '../src/components/VideoThumbnail.tsx'), 'utf8');
  assert.match(component, /useVideoThumbnail\(/); assert.match(component, /source=\{\{ uri: preview\.uri \}\}/);
  assert.match(component, /event\.stopPropagation\(\)/); assert.match(component, /Retry video preview/);
});



test('disabled private media keeps legacy preview behavior and clears it at the accepted session boundary', async () => {
  const f = fixture({ privateMedia: false }); f.setProps(['video-A', false, 'token-A', 'https://provider.invalid/legacy']);
  f.render(); await tick(); assert.equal(f.render().uri, 'https://provider.invalid/legacy'); assert.equal(f.calls.length, 0);
  f.release(); assert.equal(f.render().uri, null); f.changeSession(); f.render(); await tick(); assert.equal(f.render().uri, null); f.unmount();
});


test('an old thumbnail error after same-session token refresh cannot discard the new preview', async () => {
  const f = fixture(); f.render(); await tick(); const old = f.render();
  f.setProps(['video-A', true, 'rotated-token-A', null]); f.render(); await tick(); const refreshed = f.render();
  assert.equal(f.calls.length, 2); assert.ok(refreshed.uri);
  old.onImageError(); assert.ok(f.render().uri); assert.equal(f.calls.length, 2); f.unmount();
});
