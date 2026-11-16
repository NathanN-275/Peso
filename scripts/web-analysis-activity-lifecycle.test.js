const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const tick = () => new Promise(setImmediate);

// Exercise the actual provider's effects, including a queue arriving after its
// first empty response. The pure polling predicate cannot catch this lifecycle.
function fixture() {
  const slots = [], effects = [], timers = [], listeners = new Map(), storage = new Map();
  let cursor = 0, response = [], calls = 0;
  const changed = (a, b) => !a || a.length !== b.length || a.some((v, i) => !Object.is(v, b[i]));
  const react = {
    createContext: () => ({ Provider: 'provider' }), use: () => null,
    useState(initial) { const i = cursor++; slots[i] ??= { value: typeof initial === 'function' ? initial() : initial };
      return [slots[i].value, v => { slots[i].value = typeof v === 'function' ? v(slots[i].value) : v; }]; },
    useRef(value) { const i = cursor++; return slots[i] ??= { current: value }; },
    useMemo(fn, deps) { const i = cursor++; if (!slots[i] || changed(slots[i].deps, deps)) slots[i] = { deps, value: fn() }; return slots[i].value; },
    useCallback(fn, deps) { return react.useMemo(() => fn, deps); },
    useEffect(fn, deps) { const i = cursor++; if (!slots[i] || changed(slots[i].deps, deps)) {
      const previous = slots[i]; slots[i] = { deps }; effects.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); });
    } },
  };
  const user = { id: 'owner' }, session = { access_token: 'fixture-token' };
  const document = { visibilityState: 'visible', addEventListener: (k, fn) => listeners.set(k, fn), removeEventListener: k => listeners.delete(k) };
  const window = { localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) } };
  const imports = {
    react, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }) },
    'react-native': { Platform: { OS: 'web' }, AppState: {} },
    '../../context/AuthContext': { useAuth: () => ({ user, session }) },
    '../../lib/analysisActivityPolicy': require('../lib/analysisActivityPolicy'),
    '../../lib/backendAuth': { getFreshBackendAccessToken: async () => session.access_token },
    '../../lib/backendApi': { getAnalysisActivity: async () => { calls++; return { items: response, active_count: response.filter(x => ['queued', 'processing'].includes(x.status)).length, active_limit: 3 }; } },
  };
  const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/web/web-analysis-activity.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const module = { exports: {} };
  new Function('require', 'module', 'exports', 'window', 'document', 'setTimeout', 'clearTimeout', compiled.outputText)(name => {
    assert.ok(imports[name], name); return imports[name];
  }, module, module.exports, window, document,
  (fn, delay) => { const timer = { fn, delay, cleared: false }; timers.push(timer); return timer; }, t => { if (t) t.cleared = true; });
  const render = () => { cursor = 0; const value = module.exports.WebAnalysisActivityProvider({ children: null }).props.value;
    for (const effect of effects.splice(0)) effect(); return value; };
  return { render, timers, get calls() { return calls; }, respond: value => { response = value; },
    visibility: value => { document.visibilityState = value; listeners.get('visibilitychange')?.(); },
    next: async () => { const timer = timers.find(t => !t.cleared); assert.ok(timer, 'active polling timer'); timer.cleared = true; await timer.fn(); await tick(); },
    unmount: () => slots.forEach(slot => slot.cleanup?.()),
  };
}
const activity = (id, stage) => ({ video_id: id, job_id: id, status: stage === 'ready' ? 'ready' : stage === 'failed' ? 'failed' : stage === 'queued' ? 'queued' : 'processing', stage, created_at: new Date().toISOString() });

test('an empty foreground provider restarts polling when each new lift is queued', async () => {
  const f = fixture(); f.render(); await tick(); let value = f.render(); assert.equal(f.calls, 1);
  value.recordQueued({ videoId: 'one', jobId: 'one', status: 'queued' }); f.respond([activity('one', 'pose')]);
  f.render(); await tick(); value = f.render();
  assert.equal(value.items[0].stage, 'pose', 'new work must fetch server truth without switching tabs');
  value.recordQueued({ videoId: 'two', jobId: 'two', status: 'queued' }); f.render();
  f.respond([activity('one', 'ready'), activity('two', 'barbell_tracking')]); await f.next(); value = f.render();
  assert.deepEqual(value.items.map(x => x.stage), ['ready', 'barbell_tracking']);
  f.respond([activity('one', 'ready'), activity('two', 'failed')]); await f.next(); value = f.render();
  assert.equal(value.activeCount, 0);
  value.recordQueued({ videoId: 'three', jobId: 'three', status: 'queued' }); f.respond([activity('three', 'pose')]);
  f.render(); await tick(); assert.equal(f.render().items[0].stage, 'pose'); f.unmount();
});

test('hidden work stops polling and returning to the page refreshes it', async () => {
  const f = fixture(); f.respond([activity('one', 'pose')]); f.render(); await tick(); f.render(); await tick(); f.render();
  f.visibility('hidden'); f.render(); assert.equal(f.timers.filter(t => !t.cleared).length, 0);
  f.respond([activity('one', 'ready')]); f.visibility('visible'); f.render(); await tick(); assert.equal(f.render().items[0].stage, 'ready'); f.unmount();
});
