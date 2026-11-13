const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

// Execute Peso modules only. Auth, React, callbacks, storage and fetch are mocks;
// this harness never imports or constructs an installed Auth SDK client.
const A = { access_token: 'synthetic-A', expires_at: 4000000000, user: { id: 'owner-A' } };
const B = { access_token: 'synthetic-B', expires_at: 4000000000, user: { id: 'owner-B' } };
const ready = (session, revision = 1, event = 'SIGNED_IN') => ({ session, revision, event, status: 'ready', error: null });
const deferred = () => { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const tick = () => new Promise((resolve) => setImmediate(resolve));

function load(relative, mocks, globals = {}, source) {
  const filename = path.resolve(__dirname, '..', relative);
  const code = ts.transpileModule(source ?? fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const module = { exports: {} };
  const sandbox = { module, exports: module.exports, URL, Promise, setTimeout, clearTimeout,
    console: { warn() {}, error() {}, info() {}, log() {} }, ...globals };
  sandbox.require = (name) => {
    if (!Object.hasOwn(mocks, name)) throw new Error('Unexpected module dependency: ' + name);
    return mocks[name];
  };
  vm.runInNewContext(code, sandbox, { filename });
  return module.exports;
}

function supabaseFixture({ enabled = true, platform = 'web', locks = true } = {}) {
  const events = []; const callbacks = []; const listeners = new Set(); const activeKeys = [];
  const values = new Map(); const localValues = new Map(); const lockNames = [];
  let snapshot = { ...ready(null, 0, 'INITIAL_SESSION'), status: 'initializing' };
  let options; let clientOptions; let finished = 0; let rawLogoutEvents = 0; const updates = []; const mutationIntents = []; const pendingGlobalTokens = new Set(); const logoutIntents = [];
  const asyncStorage = { async getItem(key) { return values.get(key) ?? null; },
    async setItem(key, value) { values.set(key, value); }, async removeItem(key) { values.delete(key); } };
  const localStorage = { getItem: (key) => localValues.get(key) ?? null,
    setItem: (key, value) => { localValues.set(key, value); }, removeItem: (key) => { localValues.delete(key); } };
  const hints = [];
  const publish = (next) => { snapshot = next; for (const fn of listeners) fn(next); };
  const controller = { storage: { controlled: true }, getSnapshot: () => snapshot,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    authStateChanged(event, session) { hints.push([event, session]); },
    async initialize() { events.push('initialize'); publish(ready(A)); },
    async waitForSession(session) { events.push('wait'); return session; }, async retry() { events.push('retry'); },
    async getTransitionSessionKey() { events.push('transitionKey'); return A.access_token; } };
  const client = { auth: { async getSession() { events.push('getSession'); return { data: { session: A }, error: null }; },
    onAuthStateChange(fn) { callbacks.push(fn); return { data: { subscription: { unsubscribe() {} } } }; },
    async signOut() { events.push('signOut'); return { error: null }; },
    async updateUser(attributes) { updates.push(attributes); return { data: { user: A.user }, error: null }; } } };
  const api = load('lib/supabase.ts', {
    '@react-native-async-storage/async-storage': { __esModule: true, default: asyncStorage },
    '@supabase/supabase-js': { createClient(url, key, config) { events.push('createClient'); clientOptions = config; return client; }, processLock() {} },
    'react-native': { Platform: { OS: platform } },
    './backendApi': { getBackendApiUrl: () => 'https://api.usepeso.com', revokeGlobalPrivateMediaSession() {}, revokeReplacementPrivateMediaSession() {},
      async verifyIncomingPrivateMediaSession() { events.push('verifyIncoming'); return { owner_id: 'owner-A', session_id: 'session-A', accepted: true }; } },
    './privateExportFiles': { ensurePrivateExportStartupCleanup() { if (platform !== 'web') events.push('exportCleanup'); } },
    './privateMediaLogout': { getPrivateMediaSessionKey: (token) => token ?? null,
      createMediaLogoutFetch: () => ({ fetch() {}, async getConfirmedGlobalReceipt() { return null; },
        async finishLocalSignOut() { finished += 1; },
        async hasPendingGlobalLogout(token) { return pendingGlobalTokens.has(token); }, authStateChanged() { rawLogoutEvents += 1; },
        signOut(key, action) { logoutIntents.push(key); return action(); }, getAuthMutationKey() { return null; }, getLogoutIntentKey() { return undefined; },
        updateUser(key, action) { mutationIntents.push(key); return action(); } }) },
    './privateMediaLifecycle': { releasePrivateMedia: async () => {}, getActivePrivateMediaSessionKey: () => snapshot.status === 'ready' ? snapshot.session?.access_token ?? null : null, setActivePrivateMediaSessionKey: (key) => activeKeys.push(key) },
    './privateMediaSession': { createPrivateMediaSessionController(config) { events.push('controller'); options = config; return controller; } },
  }, { process: { env: { EXPO_PUBLIC_SUPABASE_URL: 'https://project-fixture.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'synthetic-public-fixture', EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: String(enabled) } },
    localStorage, navigator: locks ? { locks: { async request(name, action) { lockNames.push(name); return action(); } } } : {} });
  return { api, client, controller, callbacks, hints, events, options, clientOptions, asyncStorage,
    localValues, lockNames, activeKeys, publish, updates, mutationIntents, pendingGlobalTokens, logoutIntents, finished: () => finished, rawLogoutEvents: () => rawLogoutEvents };
}

test('controller storage is installed before client creation with the exact explicit Auth key', async () => {
  const f = supabaseFixture();
  assert.deepEqual(f.events.slice(0, 2), ['controller', 'createClient']);
  assert.equal(f.options.storageKey, 'sb-project-fixture-auth-token');
  assert.equal(f.clientOptions.auth.storageKey, f.options.storageKey);
  assert.equal(typeof f.options.validateIncomingSession, 'function');
  assert.equal((await f.options.validateIncomingSession(A.access_token, 'https://api.usepeso.com')).accepted, true);
  assert.equal(f.options.getLogoutIntentKey(), undefined);
  assert.equal(f.clientOptions.auth.storage, f.controller.storage);
  assert.equal(f.clientOptions.auth.detectSessionInUrl, true);
  await f.options.storage.setItem('key', 'value'); assert.equal(f.localValues.get('key'), 'value');
  await f.options.runExclusive(async () => 7);
  assert.deepEqual(f.lockNames, ['peso:private-media-session:v1:sb-project-fixture-auth-token']);
  const unavailable = supabaseFixture({ locks: false }); let entered = false;
  await assert.rejects(unavailable.options.runExclusive(async () => { entered = true; }), /coordination is unavailable/);
  assert.equal(entered, false);
});

test('native startup clears private export crash files before verifying an incoming account', async () => {
  const f = supabaseFixture({ platform: 'ios' });
  await f.options.validateIncomingSession(A.access_token, 'https://api.usepeso.com');
  assert.deepEqual(f.events.slice(-2), ['exportCleanup', 'verifyIncoming']);
});

test('raw SDK hints never activate an incoming key or clear global receipts; accepted null can clear them', async () => {
  const f = supabaseFixture(); f.callbacks[0]('SIGNED_IN', B); f.callbacks[0]('SIGNED_OUT', null);
  assert.equal(f.hints.length, 2); assert.deepEqual(f.activeKeys, []);
  assert.equal(f.rawLogoutEvents(), 0); assert.equal(f.finished(), 0);
  f.publish({ ...ready(null), status: 'blocked' }); assert.equal(f.finished(), 0);
  f.publish(ready(null)); await tick(); assert.equal(f.finished(), 1);
});

test('initialization awaits ordinary getSession outside callbacks then reconciles actual storage', async () => {
  const f = supabaseFixture(); await f.api.initializeAcceptedAuthSession();
  assert.deepEqual(f.events.slice(2), ['getSession', 'initialize', 'wait']);
  await f.api.initializeAcceptedAuthSession(); assert.equal(f.events.filter((x) => x === 'getSession').length, 1);
  const failed = supabaseFixture(); failed.client.auth.getSession = async () => { throw new Error('private raw failure'); };
  await failed.api.initializeAcceptedAuthSession();
  assert.equal(failed.events.includes('initialize'), true); assert.equal(failed.events.includes('wait'), false);
});

test('stale bootstrap hints cannot hide a newer accepted generation', async () => {
  const f = supabaseFixture();
  f.controller.initialize = async () => { f.publish(ready(B, 3)); };
  f.controller.waitForSession = async () => { throw new Error('superseded raw SDK result'); };
  await f.api.initializeAcceptedAuthSession();
  assert.equal(f.api.getAcceptedAuthSnapshot().session, B);
  assert.equal(f.api.getAcceptedAuthSnapshot().status, 'ready');
});

test('disabled web/native preserve original SDK storage choices and raw event behavior', async () => {
  for (const platform of ['web', 'ios']) {
    const f = supabaseFixture({ enabled: false, platform });
    assert.equal(f.clientOptions.auth.storage, platform === 'web' ? undefined : f.asyncStorage);
    f.callbacks[0]('SIGNED_IN', A);
    assert.deepEqual(f.activeKeys, [A.access_token]); assert.equal(f.rawLogoutEvents(), 1);
    await f.api.initializeAcceptedAuthSession();
    assert.equal(f.hints.some(([event, value]) => event === 'INITIAL_SESSION' && value === A), true);
  }
});

function backendFixture({ session = A, refreshed = null, refreshError = null, accept = async (value) => value } = {}) {
  let refreshCalls = 0;
  const api = load('lib/backendAuth.ts', { './supabase': { supabaseConfigError: null,
    waitForAcceptedAuthSession: accept,
    supabase: { auth: { async getSession() { return { data: { session }, error: null }; },
      async refreshSession() { refreshCalls += 1; return { data: { session: refreshed }, error: refreshError }; } } } } });
  return { api, refreshCalls: () => refreshCalls };
}

test('backend token acquisition returns only accepted results and stops on unresolved acceptance', async () => {
  const f = backendFixture({ accept: async () => B });
  assert.equal(await f.api.getFreshBackendAccessToken(), B.access_token); assert.equal(f.refreshCalls(), 0);
  const blocked = backendFixture({ accept: async () => { throw new Error('blocked transition'); } });
  await assert.rejects(blocked.api.getFreshBackendAccessToken(), /blocked transition/); assert.equal(blocked.refreshCalls(), 0);
});

test('failed or empty refresh cannot fall back to the stale raw session', async () => {
  for (const refreshError of [null, { message: 'synthetic rejected refresh' }]) {
    const stale = { ...A, expires_at: 1 };
    const f = backendFixture({ session: stale, refreshError });
    await assert.rejects(f.api.getFreshBackendAccessToken()); assert.equal(f.refreshCalls(), 1);
  }
  const f = backendFixture({ session: { ...A, expires_at: 1 }, refreshed: B, accept: async (s) => {
    if (s === B) throw new Error('new session not accepted'); return s;
  } });
  await assert.rejects(f.api.getFreshBackendAccessToken(), /not accepted/);
});

function reactHarness(relative, mocks, props = {}) {
  const slots = []; let cursor = 0; const effects = [];
  const jsx = (type, elementProps) => ({ type, props: elementProps });
  const react = { createContext: () => ({ Provider: 'AuthProvider' }), useContext() {},
    useState(initial) { const index = cursor++; if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[index].value, (value) => { slots[index].value = typeof value === 'function' ? value(slots[index].value) : value; }]; },
    useRef(initial) { const index = cursor++; if (!slots[index]) slots[index] = { current: initial }; return slots[index]; },
    useEffect(effect) { const index = cursor++; if (!slots[index]) { slots[index] = true; effects.push(effect); } } };
  const native = { Platform: { OS: 'web' }, AppState: {}, StyleSheet: { create: (value) => value },
    View: 'View', Text: 'Text', Pressable: 'Pressable', Image: 'Image', KeyboardAvoidingView: 'KeyboardAvoidingView', ScrollView: 'ScrollView' };
  const module = load(relative, { react, 'react/jsx-runtime': { jsx, jsxs: jsx }, 'react-native': native, ...mocks });
  const render = () => { cursor = 0; return (module.AuthProvider ?? module.default)({ children: 'application-children', ...props }); };
  return { module, render, effects: () => { for (const effect of effects.splice(0)) effect(); } };
}
function nodes(tree) {
  if (!tree || typeof tree !== 'object') return [];
  const children = tree.props?.children;
  return [tree, ...(Array.isArray(children) ? children : [children]).flatMap(nodes)];
}

function contextFixture(overrides = {}) {
  let snapshot = ready(A); const listeners = new Set(); const profile = []; const waits = []; const accountUpdates = [];
  const callbacks = { async signInWithPassword() { return { data: { session: B }, error: null }; },
    async signUp() { return { data: { session: B, user: B.user }, error: null }; },
    onAuthStateChange() { throw new Error('AuthContext must not subscribe to raw Auth'); },
    async getSession() { throw new Error('AuthContext must not publish a raw bootstrap session'); } };
  const controller = { supabase: { auth: callbacks }, supabaseConfigError: null, supabaseAuthUrl: 'https://fixture.invalid/auth/v1',
    getAcceptedAuthSnapshot: () => snapshot,
    subscribeAcceptedAuthSession(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    async initializeAcceptedAuthSession() {},
    async waitForAcceptedAuthSession(session) { waits.push(session); return session; },
    async retryAuthSessionTransition() { publish(ready(null, 8, 'SIGNED_OUT')); },
    async updateUserWithPrivateMedia(key, attributes) { accountUpdates.push([key, attributes]); return { error: null }; },
    ...overrides };
  const publish = (next) => { snapshot = next; for (const fn of listeners) fn(next); };
  const h = reactHarness('context/AuthContext.tsx', { '../lib/supabase': controller,
    '../lib/privateMediaLogout': { getPrivateMediaSessionKey: (token) => token ?? null },
    '../lib/profile': { async ensureOwnProfile(user, token) { profile.push([user, token]); } } });
  return { ...h, publish, profile, waits, accountUpdates, controller, value: () => h.render().props.value };
}

test('AuthContext publishes one accepted stream and initializes profiles only for ready generations', async () => {
  const f = contextFixture(); f.render(); f.effects(); await tick();
  assert.equal(f.value().session, A); assert.deepEqual(f.profile, [[A.user, A.access_token]]);
  f.publish({ ...ready(B, 2), status: 'pending' }); await tick();
  assert.equal(f.value().session, null); assert.equal(f.profile.length, 1);
  f.publish({ ...ready(B, 3), status: 'blocked', error: 'Please retry.' });
  assert.equal(f.value().session, null);
  f.publish(ready(B, 4)); await tick();
  assert.equal(f.value().session, B); assert.deepEqual(f.profile.at(-1), [B.user, B.access_token]);
});

test('queued profile initialization cannot run after its accepted generation is suspended', async () => {
  const f = contextFixture(); f.render(); f.effects();
  f.publish({ ...ready(B, 2), status: 'pending' });
  await tick(); assert.deepEqual(f.profile, []);
});

test('login and signup cannot resolve with their raw sessions before acceptance finishes', async () => {
  for (const method of ['signInWithEmail', 'signUpWithEmail']) {
    const gate = deferred(); let settled = false;
    const f = contextFixture({ waitForAcceptedAuthSession: () => gate.promise });
    const value = f.value();
    const pending = (method === 'signInWithEmail' ? value[method]('fixture@example.invalid', 'synthetic-password', 'challenge')
      : value[method]('fixture@example.invalid', 'synthetic-password', undefined, 'challenge')).then((result) => { settled = true; return result; });
    await tick(); assert.equal(settled, false);
    gate.resolve(A); const result = await pending;
    if (method === 'signUpWithEmail') assert.equal(result.session, A);
  }
});

test('blocked transition exposes a reachable retry and restores the sign-in screen after secured removal', async () => {
  const f = contextFixture(); f.render(); f.effects();
  f.publish({ ...ready(B, 2), status: 'blocked', error: 'Please retry.' });
  let tree = f.render(); const button = nodes(tree).find((node) => node.type === 'Pressable');
  assert.ok(button); assert.equal(f.value().session, null);
  button.props.onPress(); await tick(); tree = f.render();
  assert.equal(f.value().session, null);
  assert.equal(nodes(tree).some((node) => node.type === 'Pressable'), false);
  assert.equal(nodes(tree).some((node) => node.props?.children === 'application-children' && !node.props.style[1]), true);
});

test('native PKCE helper waits for acceptance and never adopts untrusted callback sessions', async () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../src/native-root.tsx'), 'utf8');
  const parsed = ts.createSourceFile('native-root.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const declaration = parsed.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === 'hydrateAuthRedirectSession');
  assert.ok(declaration);
  const gate = deferred(); let exchanges = 0; let settled = false;
  const api = load('src/native-root.tsx', {}, { supabase: { auth: { async exchangeCodeForSession() {
    exchanges += 1; return { data: { session: B }, error: null }; } } }, waitForAcceptedAuthSession: () => gate.promise,
    getPrivateMediaSessionKey: (token) => token ?? null, supabaseAuthUrl: 'https://fixture.invalid/auth/v1' },
  'export ' + declaration.getText(parsed));
  assert.equal(await api.hydrateAuthRedirectSession({ trusted: false, hasRecoverySessionParams: true, code: 'synthetic-code' }), null);
  assert.equal(exchanges, 0);
  const pending = api.hydrateAuthRedirectSession({ trusted: true, hasRecoverySessionParams: true, code: 'synthetic-code' })
    .then((result) => { settled = true; return result; });
  await tick(); assert.equal(settled, false); assert.equal(exchanges, 1);
  gate.resolve(B); const result = await pending; assert.equal(result.method, 'code'); assert.equal(result.sessionKey, B.access_token);
});

test('native continuation and password reset checks require accepted sessions; raw bootstrap callback wiring stays retired', () => {
  const native = fs.readFileSync(path.resolve(__dirname, '../src/native-root.tsx'), 'utf8');
  const reset = fs.readFileSync(path.resolve(__dirname, '../src/screens/ChangePasswordScreen.tsx'), 'utf8');
  const context = fs.readFileSync(path.resolve(__dirname, '../context/AuthContext.tsx'), 'utf8');
  assert.match(native, /const accepted = await waitForAcceptedAuthSession\(currentSession\)/);
  assert.match(native, /callbackSessionKey === exchangeMethod\.sessionKey/);
  assert.match(native, /activatePasswordRecoveryMode\(callbackSessionKey\)/);
  assert.match(reset, /const acceptedSession = await waitForAcceptedAuthSession\(session\)/);
  assert.doesNotMatch(context, /supabase\.auth\.(?:getSession|onAuthStateChange)/);
});

test('password reset cannot mutate credentials using a raw unaccepted recovery session', async () => {
  const gate = deferred(); let updates = 0; let acceptanceChecks = 0;
  const h = reactHarness('src/screens/ChangePasswordScreen.tsx', {
    'expo-status-bar': { StatusBar: 'StatusBar' },
    'react-native-safe-area-context': { SafeAreaView: 'SafeAreaView' },
    '../../context/AuthContext': { useAuth: () => ({ passwordRecoveryMode: true,
      async updatePassword() { updates += 1; } }) },
    '../../lib/supabase': { supabase: { auth: { async getSession() { return { data: { session: B } }; } } },
      waitForAcceptedAuthSession: () => { acceptanceChecks += 1; return gate.promise; } },
    '../components/Button': { __esModule: true, default: 'Button' },
    '../components/Input': { __esModule: true, default: 'Input' },
    '../theme/tokens': { __esModule: true, default: { spacing: { screenX: 20 } } },
    '../../ResetPassword.png': 'synthetic-image',
  }, { onBack() {}, onReset() {} });
  let tree = h.render();
  for (const input of nodes(tree).filter((node) => node.type === 'Input')) input.props.onChangeText('synthetic-password');
  tree = h.render();
  const pending = nodes(tree).find((node) => node.props?.testID === 'reset-submit').props.onPress();
  await tick(); assert.equal(updates, 0); assert.equal(acceptanceChecks, 1);
  gate.reject(new Error('Session transition remains blocked.')); await pending;
  assert.equal(updates, 0);
  assert.equal(nodes(h.render()).some((node) => node.props?.children === 'Unable to reset password.'), true);
});


test('account update captures accepted UI identity and delegates actual-token enforcement to the fetch seam', async () => {
  const f = supabaseFixture(); f.publish(ready(A));
  const attributes = { email: 'intended-A@example.invalid' };
  await f.api.updateUserWithPrivateMedia(A.access_token, attributes);
  assert.deepEqual(f.mutationIntents, [A.access_token]); assert.deepEqual(f.updates, [attributes]);
  assert.equal(typeof f.options.getAuthMutationKey, 'function');
});

test('account updates cannot dispatch while blocked or through raw incoming credentials', async () => {
  const blocked = supabaseFixture(); blocked.publish({ ...ready(A), status: 'blocked' });
  await assert.rejects(blocked.api.updateUserWithPrivateMedia(A.access_token, { password: 'synthetic-password' }), /session changed/);
  assert.equal(blocked.updates.length, 0); assert.equal(blocked.events.includes('getSession'), false);
  const changed = supabaseFixture(); changed.publish(ready(A));
  changed.client.auth.getSession = async () => ({ data: { session: B }, error: null });
  await assert.rejects(changed.api.updateUserWithPrivateMedia(A.access_token, { password: 'synthetic-password' }), /session changed/);
  assert.equal(changed.updates.length, 0); assert.deepEqual(changed.mutationIntents, []);
});

test('account-update preflight rechecks acceptance after an asynchronous session read', async () => {
  const f = supabaseFixture(); f.publish(ready(A)); const gate = deferred();
  f.client.auth.getSession = () => gate.promise;
  const pending = f.api.updateUserWithPrivateMedia(A.access_token, { password: 'synthetic-password' });
  f.publish(ready(B, 2)); gate.resolve({ data: { session: A }, error: null });
  await assert.rejects(pending, /session changed/); assert.equal(f.updates.length, 0); assert.deepEqual(f.mutationIntents, []);
});

test('feature-off account updates retain direct SDK behavior without new preflight', async () => {
  const f = supabaseFixture({ enabled: false });
  await f.api.updateUserWithPrivateMedia(null, { password: 'synthetic-password' });
  assert.equal(f.updates.length, 1); assert.deepEqual(f.mutationIntents, []); assert.equal(f.events.includes('getSession'), false);
});

test('AuthContext password mutation keeps the UI-captured session after accepted identity changes', async () => {
  const f = contextFixture(); const old = f.value(); f.effects();
  f.publish(ready(B, 2)); await assert.rejects(old.updatePassword('synthetic-password'), /session changed/);
  assert.equal(f.accountUpdates[0][0], A.access_token); assert.equal(f.accountUpdates[0][1].password, 'synthetic-password');
});

test('password recovery is bound to the accepted provider session and survives only same-session refresh', async () => {
  const f = contextFixture(); f.render(); f.effects();
  f.publish(ready(A, 2, 'PASSWORD_RECOVERY')); assert.equal(f.value().passwordRecoveryMode, true);
  f.publish(ready({ ...A, expires_at: A.expires_at + 100 }, 3, 'TOKEN_REFRESHED'));
  assert.equal(f.value().passwordRecoveryMode, true);
  f.publish(ready(B, 4, 'SIGNED_IN')); assert.equal(f.value().passwordRecoveryMode, false);
  f.publish(ready(B, 5, 'PASSWORD_RECOVERY')); assert.equal(f.value().passwordRecoveryMode, true);
  f.publish(ready(null, 6, 'SIGNED_OUT')); assert.equal(f.value().passwordRecoveryMode, false);
});

test('unbound pending recovery cannot carry into a normal accepted login', async () => {
  const f = contextFixture(); f.render(); f.effects(); f.publish(ready(null, 2, 'SIGNED_OUT'));
  assert.equal(f.value().activatePasswordRecoveryMode(null), false); assert.equal(f.value().passwordRecoveryMode, false);
  f.publish(ready(B, 3, 'SIGNED_IN')); assert.equal(f.value().passwordRecoveryMode, false);
});

test('both Settings credential handlers dispatch only through the captured-session wrapper', async () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../src/screens/SettingsScreen.tsx'), 'utf8');
  const parsed = ts.createSourceFile('SettingsScreen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function find(node, predicate) { if (predicate(node)) return node; let result; ts.forEachChild(node, (child) => { result ??= find(child, predicate); }); return result; }
  for (const name of ['handleUpdateEmail', 'handleUpdatePassword']) {
    const declaration = find(parsed, (node) => ts.isVariableDeclaration(node) && node.name.getText(parsed) === name);
    assert.ok(declaration); const calls = [];
    const api = load('src/screens/SettingsScreen.tsx', {}, {
      email: 'intended-A@example.invalid', password: 'synthetic-password', confirmPassword: 'synthetic-password',
      mediaSessionKey: A.access_token, mounted: { current: true }, currentSessionKey: { current: A.access_token }, getPrivateMediaEpoch: () => 0,
      supabase: { auth: { updateUser() { throw new Error('Unbound SDK mutation must stay unreachable'); } } },
      async updateUserWithPrivateMedia(key, attributes) { calls.push([key, attributes]); return { error: null }; },
      setErrorMessage() {}, setMessage() {}, setUpdatingEmail() {}, setUpdatingPassword() {}, clearMessages() {}, setPassword() {}, setConfirmPassword() {},
    }, 'export const handler = ' + declaration.initializer.getText(parsed));
    await api.handler(); assert.equal(calls.length, 1); assert.equal(calls[0][0], A.access_token);
    assert.equal(name === 'handleUpdateEmail' ? calls[0][1].email : calls[0][1].password,
      name === 'handleUpdateEmail' ? 'intended-A@example.invalid' : 'synthetic-password');
  }
  assert.doesNotMatch(source, /supabase\.auth\.updateUser/);
});


test('late password success cannot clear a new accepted session recovery mode', async () => {
  const gate = deferred(); const f = contextFixture({ updateUserWithPrivateMedia: () => gate.promise });
  const old = f.value(); f.effects();
  f.publish(ready(A, 2, 'PASSWORD_RECOVERY'));
  const pending = old.updatePassword('synthetic-password');
  f.publish(ready(B, 3, 'PASSWORD_RECOVERY')); assert.equal(f.value().passwordRecoveryMode, true);
  gate.resolve({ error: null }); await assert.rejects(pending, /session changed/);
  assert.equal(f.value().passwordRecoveryMode, true);
});


test('Settings credential replies cannot update a later session or resurrect cleared form state', async () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../src/screens/SettingsScreen.tsx'), 'utf8');
  const parsed = ts.createSourceFile('SettingsScreen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function find(node, predicate) { if (predicate(node)) return node; let result; ts.forEachChild(node, (child) => { result ??= find(child, predicate); }); return result; }
  for (const name of ['handleUpdateEmail', 'handleUpdatePassword']) {
    const declaration = find(parsed, (node) => ts.isVariableDeclaration(node) && node.name.getText(parsed) === name);
    const gate = deferred(); const updates = []; const currentSessionKey = { current: A.access_token }; let dispatched;
    const entered = new Promise((resolve) => { dispatched = resolve; });
    const api = load('src/screens/SettingsScreen.tsx', {}, {
      email: 'intended-A@example.invalid', password: 'synthetic-password', confirmPassword: 'synthetic-password',
      mediaSessionKey: A.access_token, mounted: { current: true }, currentSessionKey, getPrivateMediaEpoch: () => 0,
      supabase: {}, async updateUserWithPrivateMedia() { dispatched(); return gate.promise; },
      setErrorMessage(value) { updates.push(['error', value]); }, setMessage(value) { updates.push(['message', value]); },
      setUpdatingEmail(value) { updates.push(['emailBusy', value]); }, setUpdatingPassword(value) { updates.push(['passwordBusy', value]); },
      clearMessages() {}, setPassword(value) { updates.push(['password', value]); }, setConfirmPassword(value) { updates.push(['confirmation', value]); },
    }, 'export const handler = ' + declaration.initializer.getText(parsed));
    const pending = api.handler(); await entered; currentSessionKey.current = B.access_token;
    const countBeforeReply = updates.length; gate.resolve({ error: null }); await pending;
    assert.equal(updates.length, countBeforeReply);
  }
});


test('a native listener captured before adoption binds recovery to the current accepted callback session', async () => {
  const f = contextFixture(); const initial = f.value(); f.effects();
  f.publish(ready(B, 2));
  assert.equal(initial.activatePasswordRecoveryMode(B.access_token), true);
  assert.equal(f.value().passwordRecoveryMode, true);
  f.publish(ready({ ...B, expires_at: B.expires_at + 100 }, 3, 'TOKEN_REFRESHED'));
  assert.equal(f.value().passwordRecoveryMode, true);
});

test('late or blocked native recovery callbacks cannot mark a different accepted session', async () => {
  const f = contextFixture(); const initial = f.value(); f.effects();
  const C = { ...B, access_token: 'synthetic-C', user: { id: 'owner-C' } };
  f.publish(ready(C, 2));
  assert.equal(initial.activatePasswordRecoveryMode(B.access_token), false);
  assert.equal(f.value().passwordRecoveryMode, false);
  f.publish({ ...ready(B, 3), status: 'blocked' });
  assert.equal(initial.activatePasswordRecoveryMode(B.access_token), false);
  assert.equal(f.value().passwordRecoveryMode, false);
  f.publish(ready(C, 4, 'PASSWORD_RECOVERY')); assert.equal(f.value().passwordRecoveryMode, true);
  assert.equal(initial.activatePasswordRecoveryMode(B.access_token), false);
  assert.equal(f.value().passwordRecoveryMode, true);
});

test('native callback continuation keeps the exchanged accepted key instead of adopting a later raw session', async () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../src/native-root.tsx'), 'utf8');
  const parsed = ts.createSourceFile('native-root.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function find(node, predicate) { if (predicate(node)) return node; let result; ts.forEachChild(node, (child) => { result ??= find(child, predicate); }); return result; }
  const declaration = find(parsed, (node) => ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'handleUrl');
  for (const current of [B, { ...B, access_token: 'synthetic-C', user: { id: 'owner-C' } }]) {
    const activated = [];
    const api = load('src/native-root.tsx', {}, {
      routeRef: { current: 'login' },
      parseNativeAuthRoute: () => ({ route: 'reset', trusted: true, destination: 'reset-password', queryParams: {}, hashParams: {},
        isRecoveryResetLink: true, hasRecoverySessionParams: true, errorMessage: null }),
      redactAuthParams: (value) => value,
      setAuthLinkErrorMessage() {}, setRecoverySessionReady() {}, setIsHandlingRecoveryLink() {}, setIsRecoveryMode() {}, setRoute() {},
      AUTH_ROUTES: { resetPasswordForm: 'reset' },
      hydrateAuthRedirectSession: async () => ({ method: 'code', sessionKey: B.access_token }),
      supabase: { auth: { getSession: async () => ({ data: { session: current } }) } },
      waitForAcceptedAuthSession: async (value) => value,
      getPrivateMediaSessionKey: (token) => token ?? null, supabaseAuthUrl: 'https://fixture.invalid/auth/v1',
      activatePasswordRecoveryMode: (key) => { activated.push(key); return true; },
    }, 'export const handler = ' + declaration.initializer.getText(parsed));
    await api.handler('pesoapp://reset-password?code=synthetic', 'runtime');
    assert.deepEqual(activated, current === B ? [B.access_token] : []);
  }
});


test('a web recovery URL marker can select its route but cannot mark an existing session as recovery', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../src/native-root.tsx'), 'utf8');
  const parsed = ts.createSourceFile('native-root.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function find(node, predicate) { if (predicate(node)) return node; let result; ts.forEachChild(node, (child) => { result ??= find(child, predicate); }); return result; }
  const declaration = find(parsed, (node) => ts.isVariableDeclaration(node) && node.name.getText(parsed) === 'handleWebAuthLink');
  for (const errorMessage of [null, 'Expired link.']) {
    const routes = []; const errors = []; let activations = 0; let localModes = 0;
    const api = load('src/native-root.tsx', {}, {
      window: { location: { pathname: '/app/reset', search: '?type=recovery', hash: '' } },
      parseWebAuthLink: () => ({ route: 'reset', resetRouteDetected: true, supabaseAuthErrorDetected: Boolean(errorMessage),
        errorMessage, searchParams: {}, hashParams: {} }),
      redactAuthParams: (value) => value,
      getAcceptedAuthSnapshot: () => ready({ ...B, access_token: 'synthetic-C' }),
      getPrivateMediaSessionKey: (token) => token, supabaseAuthUrl: 'https://fixture.invalid/auth/v1',
      activatePasswordRecoveryMode() { activations += 1; return true; },
      setIsRecoveryMode() { localModes += 1; },
      setAuthLinkErrorMessage(value) { errors.push(value); }, setRoute(value) { routes.push(value); },
    }, 'export const handler = ' + declaration.initializer.getText(parsed));
    assert.equal(api.handler(), true); assert.deepEqual(routes, ['reset']); assert.deepEqual(errors, [errorMessage]);
    assert.equal(activations, 0); assert.equal(localModes, 0);
  }
});


test('visible retry resumes only a previously requested pending global logout for the captured raw session', async () => {
  const f = supabaseFixture(); f.publish({ ...ready(null), status: 'blocked' });
  f.pendingGlobalTokens.add(A.access_token);
  await f.api.retryAuthSessionTransition();
  assert.deepEqual(f.logoutIntents, [A.access_token]);
  assert.equal(f.events.filter((event) => event === 'signOut').length, 1);
  assert.ok(f.events.indexOf('transitionKey') < f.events.indexOf('getSession'));
  assert.equal(f.events.includes('retry'), false);
});

test('acknowledged or other-session global evidence cannot select a new global logout during retry', async () => {
  const acknowledged = supabaseFixture(); acknowledged.publish({ ...ready(null), status: 'blocked' });
  await acknowledged.api.retryAuthSessionTransition();
  assert.deepEqual(acknowledged.logoutIntents, []); assert.equal(acknowledged.events.includes('retry'), true);
  const changed = supabaseFixture(); changed.publish({ ...ready(null), status: 'blocked' });
  changed.pendingGlobalTokens.add(A.access_token); changed.pendingGlobalTokens.add(B.access_token);
  changed.client.auth.getSession = async () => ({ data: { session: B }, error: null });
  await changed.api.retryAuthSessionTransition();
  assert.deepEqual(changed.logoutIntents, []); assert.equal(changed.events.includes('retry'), true);
  const anonymous = supabaseFixture(); anonymous.pendingGlobalTokens.add(A.access_token);
  anonymous.controller.getTransitionSessionKey = async () => null;
  await anonymous.api.retryAuthSessionTransition();
  assert.deepEqual(anonymous.logoutIntents, []); assert.equal(anonymous.events.includes('retry'), true);
});

test('global retry keeps provider rejection and unreadable SDK state blocked with sanitized failures', async () => {
  const rejected = supabaseFixture(); rejected.pendingGlobalTokens.add(A.access_token);
  rejected.client.auth.signOut = async () => ({ error: new Error('synthetic-private-provider-error') });
  await assert.rejects(rejected.api.retryAuthSessionTransition(),
    (error) => error.message === 'Unable to finish your sign-in change. Please retry.' && !error.cause);
  assert.equal(rejected.events.includes('retry'), false);
  const unreadable = supabaseFixture(); unreadable.pendingGlobalTokens.add(A.access_token);
  unreadable.client.auth.getSession = async () => { throw new Error('synthetic-private-read-error'); };
  await assert.rejects(unreadable.api.retryAuthSessionTransition(),
    (error) => error.message === 'Unable to finish your sign-in change. Please retry.' && !error.cause);
  assert.deepEqual(unreadable.logoutIntents, []); assert.equal(unreadable.events.includes('retry'), false);
});

test('disabled transition retry adds no provider session read or global choice', async () => {
  const f = supabaseFixture({ enabled: false }); f.pendingGlobalTokens.add(A.access_token);
  await f.api.retryAuthSessionTransition();
  assert.equal(f.events.includes('getSession'), false); assert.deepEqual(f.logoutIntents, []);
  assert.equal(f.events.includes('retry'), true);
});
