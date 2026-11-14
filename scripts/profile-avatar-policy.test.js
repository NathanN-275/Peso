const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
const policy = require('../lib/profilePolicy');

const OWNER = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const SESSION = '33333333-3333-4333-8333-333333333333';
const REVISION = '44444444-4444-4444-8444-444444444444';
const NEXT_REVISION = '55555555-5555-4555-8555-555555555555';
const ATTEMPT = '66666666-6666-4666-8666-666666666666';
const AVATAR = `${OWNER}/avatar-${ATTEMPT}.jpg`;
const TOKEN = 'original-session-access-token';
const USER = { id: OWNER, email: 'nathan@example.com', user_metadata: { name: 'Nathan', username: 'nathan' } };
const DETAILS = { username: 'nathan', display_name: 'Nathan' };
const record = (changes = {}) => ({ id: OWNER, ...DETAILS, avatar_path: AVATAR,
  created_at: '2026-10-29T12:00:00+00:00', updated_at: '2026-10-29T12:01:00+00:00',
  profile_revision: NEXT_REVISION, ...changes });

// Execute the real TypeScript request/caller code with controlled I/O, without Expo/native devices.
function loadTs(relativePath, imports, globals = {}, development = false) {
  const source = readFileSync(path.join(__dirname, relativePath), 'utf8');
  const compiled = ts.transpileModule(source, {
    reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  });
  assert.deepEqual(compiled.diagnostics, [], `TypeScript syntax failed in ${relativePath}`);
  const code = compiled.outputText;
  const module = { exports: {} };
  const mockedRequire = (name) => {
    assert.ok(Object.hasOwn(imports, name), `Unexpected import ${name}`);
    return imports[name];
  };
  const names = ['require', 'module', 'exports', '__DEV__', ...Object.keys(globals)];
  new Function(...names, code)(mockedRequire, module, module.exports, development, ...Object.values(globals));
  return module.exports;
}

class HttpError extends Error {
  constructor(status) { super('Profile conflict. Reload and try again.'); this.status = status; }
}

function profileHarness(overrides = {}, options = {}) {
  let epoch = 0;
  let sessionKey = `${OWNER}:${SESSION}`;
  const calls = [];
  const api = {
    BackendHttpError: HttpError,
    fetchOwnProfileMetadata: async (...args) => { calls.push(['get', ...args]); return { profile: record() }; },
    updateOwnProfileMetadata: async (...args) => { calls.push(['put', ...args]); return record(); },
    uploadOwnProfileAvatar: async (...args) => { calls.push(['upload', ...args]); return { attempt_id: ATTEMPT, avatar_path: AVATAR }; },
    publishOwnProfileAvatar: async (...args) => { calls.push(['publish', ...args]); return record(); },
    ...overrides,
  };
  const profile = loadTs('../lib/profile.ts', {
    'expo-constants': { appOwnership: 'standalone', AppOwnership: { Expo: 'expo' } },
    'react-native': { Platform: { OS: 'web' } },
    './supabase': { supabaseAuthUrl: 'https://auth.example/auth/v1' },
    './avatarReader': {
      beginProfileAvatarOperation: () => ({ assertCurrent() {}, observe() {}, finish() {} }),
      readProfileAvatar: async (...args) => {
        calls.push(['read-avatar', ...args.slice(0, 2)]);
        if (options.readAvatar) return options.readAvatar(...args);
        return { avatar_data_uri: 'data:image/jpeg;base64,/9j/2Q==', avatar_reupload_required: false, avatar_error: null };
      },
    },
    './backendApi': api,
    './privateMediaLifecycle': { getPrivateMediaEpoch: () => epoch, getActivePrivateMediaSessionKey: () => sessionKey },
    './privateMediaLogout': { getPrivateMediaSessionKey: (token) => token === TOKEN ? `${OWNER}:${SESSION}` : null },
    './profilePolicy': policy,
  }, { fetch: options.fetch ?? fetch });
  return { profile, calls, bumpEpoch: () => { epoch += 1; }, switchSession: () => { sessionKey = `${OWNER}:${OTHER}`; } };
}

function asset({ type = 'image/jpeg', size = 10 } = {}) {
  return { uri: 'blob:selected-photo', file: new Blob([new Uint8Array(size)], { type }), mimeType: type };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test('profile response validation rejects malformed ownership, revision, shape, timestamps and unsafe paths', () => {
  for (const value of [record({ id: OTHER }), record({ profile_revision: null }), record({ profile_revision: REVISION.toUpperCase().replace('4444', 'ABCD') }),
    record({ avatar_path: `${OTHER}/avatar-${ATTEMPT}.jpg` }), record({ avatar_path: `${OWNER}/../secret.jpg` }),
    record({ avatar_path: `${OWNER}/avatar-a.jpg?token=secret` }), record({ created_at: 'yesterday' }),
    { ...record(), avatar_url: 'https://untrusted.example' }, { ...record(), username: [] }, null]) {
    assert.throws(() => policy.validateProfileRecord(value, OWNER), /invalid/);
  }
  assert.equal(policy.validateProfileRecord(record({ avatar_path: `${OWNER}/avatar-1700000000000.png` }), OWNER).id, OWNER);
  assert.throws(() => policy.validateProfileEnvelope({ profile: record(), other: true }, OWNER), /invalid/);
});

test('avatar attempt must be exactly the admitted canonical nonce under the authenticated owner', () => {
  for (const value of [{ attempt_id: ATTEMPT, avatar_path: `${OWNER}/avatar-${REVISION}.jpg` },
    { attempt_id: ATTEMPT, avatar_path: `${OTHER}/avatar-${ATTEMPT}.jpg` },
    { attempt_id: ATTEMPT, avatar_path: AVATAR, upload_url: 'https://untrusted.example' },
    { attempt_id: '../bad', avatar_path: AVATAR }, { attempt_id: ATTEMPT, avatar_path: AVATAR.replace('.jpg', '.png') }]) {
    assert.throws(() => policy.validateAvatarAttempt(value, OWNER), /invalid/);
  }
  assert.equal(policy.validateAvatarAttempt({ attempt_id: ATTEMPT, avatar_path: AVATAR }, OWNER).avatar_path, AVATAR);
});

test('avatar validation happens before bytes dispatch; valid details normalize before atomic publish', async () => {
  const { profile, calls } = profileHarness();
  await assert.rejects(profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, { username: 'bad username' }), /Username/);
  assert.deepEqual(calls, []);
  await assert.rejects(profile.uploadProfileAvatar(USER, TOKEN, asset({ size: 512 * 1024 + 1 }), REVISION, DETAILS), /too large/);
  await assert.rejects(profile.uploadProfileAvatar(USER, TOKEN, asset({ type: 'image/gif' }), REVISION, DETAILS), /Unsupported/);
  assert.deepEqual(calls, []);
  const result = await profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, { username: '  NATHAN ', display_name: ' Nathan ' });
  assert.deepEqual(calls.map(([kind]) => kind), ['upload', 'publish', 'read-avatar']);
  assert.equal(calls[0][1], TOKEN);
  assert.equal(calls[0][2], REVISION);
  assert.equal(calls[1][1], TOKEN);
  assert.equal(calls[1][2], ATTEMPT);
  assert.deepEqual(calls[1][3], DETAILS);
  assert.equal(result.avatar_path, AVATAR);
  assert.equal(result.profile_revision, NEXT_REVISION);
});

test('metadata edits omit avatar_path and retain the validated current avatar in the result', async () => {
  const { profile, calls } = profileHarness();
  const result = await profile.saveOwnProfile(USER, TOKEN, REVISION, DETAILS);
  assert.deepEqual(calls[0], ['put', TOKEN, { profile_revision: REVISION, ...DETAILS }]);
  assert.equal(result.avatar_path, AVATAR);
  assert.deepEqual(calls.map(([kind]) => kind), ['put', 'read-avatar']);
});

test('only an actual null metadata profile gets auth-derived fallback with null revision', async () => {
  const { profile, calls } = profileHarness({ fetchOwnProfileMetadata: async () => ({ profile: null }) });
  const result = await profile.loadOwnProfile(USER, TOKEN);
  assert.equal(result.profile_revision, null);
  assert.equal(result.username, 'nathan');
  assert.equal(result.avatar_data_uri, null);
  assert.deepEqual(calls, []);
  for (const value of [{}, { profile: record({ profile_revision: null }) }]) {
    const h = profileHarness({ fetchOwnProfileMetadata: async () => value });
    await assert.rejects(h.profile.loadOwnProfile(USER, TOKEN), /invalid/);
    assert.deepEqual(h.calls, []);
  }
  const failing = profileHarness({ fetchOwnProfileMetadata: async () => { throw new Error('Backend unavailable'); } });
  await assert.rejects(failing.profile.loadOwnProfile(USER, TOKEN), /unavailable/);
});

test('malformed upload receipt never publishes or signs', async () => {
  const h = profileHarness({ uploadOwnProfileAvatar: async () => ({ attempt_id: ATTEMPT, avatar_path: `${OTHER}/avatar-${ATTEMPT}.jpg` }) });
  await assert.rejects(h.profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, DETAILS), /invalid/);
  assert.deepEqual(h.calls, []);
});

test('malformed publication never signs and never compensates by removing bytes', async () => {
  for (const response of [record({ avatar_path: `${OWNER}/avatar-${REVISION}.jpg` }), record({ profile_revision: REVISION }),
    record({ id: OTHER }), record({ username: 'different' }), { ...record(), extra: 1 }]) {
    const h = profileHarness({ publishOwnProfileAvatar: async () => response });
    await assert.rejects(h.profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, DETAILS), /invalid/);
    assert.deepEqual(h.calls.map(([kind]) => kind), ['upload']);
  }
});

test('upload and publication errors have no retry or compensation side effects', async () => {
  for (const stage of ['uploadOwnProfileAvatar', 'publishOwnProfileAvatar']) {
    let failedCalls = 0;
    const h = profileHarness({ [stage]: async () => { failedCalls += 1; throw new Error('Unknown write outcome'); } });
    await assert.rejects(h.profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, DETAILS), /Unknown/);
    assert.equal(failedCalls, 1);
    assert.ok(h.calls.every(([kind]) => kind === 'upload'));
  }
});

test('epoch and same-owner session replacement during upload stop before publication', async () => {
  for (const change of ['bumpEpoch', 'switchSession']) {
    const waiting = deferred();
    const h = profileHarness({ uploadOwnProfileAvatar: () => waiting.promise });
    const work = h.profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, DETAILS);
    await new Promise(setImmediate);
    h[change]();
    waiting.resolve({ attempt_id: ATTEMPT, avatar_path: AVATAR });
    await assert.rejects(work, /session changed/);
    assert.deepEqual(h.calls, []);
  }
});

test('epoch change while publishing discards late success without signing', async () => {
  const waiting = deferred();
  const h = profileHarness({ publishOwnProfileAvatar: () => waiting.promise });
  const work = h.profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, DETAILS);
  await new Promise(setImmediate);
  h.bumpEpoch();
  waiting.resolve(record());
  await assert.rejects(work, /session changed/);
  assert.deepEqual(h.calls.map(([kind]) => kind), ['upload']);
});

test('wrong caller token fails before any image or backend I/O', async () => {
  const { profile, calls } = profileHarness();
  await assert.rejects(profile.uploadProfileAvatar(USER, 'other-token', asset(), REVISION, DETAILS), /session changed/);
  assert.deepEqual(calls, []);
});

test('auth initialization reads existing metadata without overwriting it or signing its avatar', async () => {
  const { profile, calls } = profileHarness();
  await profile.ensureOwnProfile(USER, TOKEN);
  assert.deepEqual(calls, [['get', TOKEN]]);
});

test('auth initialization creates absent profile and handles concurrent creation without clobbering', async () => {
  const creates = [];
  let reads = 0;
  const h = profileHarness({
    fetchOwnProfileMetadata: async () => ({ profile: reads++ === 0 ? null : record() }),
    updateOwnProfileMetadata: async (...args) => { creates.push(args); throw new HttpError(409); },
  });
  await h.profile.ensureOwnProfile(USER, TOKEN);
  assert.equal(creates.length, 1);
  assert.deepEqual(creates[0], [TOKEN, { profile_revision: null, ...DETAILS }]);
  assert.equal(reads, 2);
  assert.deepEqual(h.calls, []);
});

test('auth initialization username conflicts retry absent creation with null username only', async () => {
  const creates = [];
  const h = profileHarness({
    fetchOwnProfileMetadata: async () => ({ profile: null }),
    updateOwnProfileMetadata: async (token, payload) => {
      creates.push([token, payload]);
      if (creates.length === 1) throw new HttpError(409);
      return record({ username: null, avatar_path: null });
    },
  });
  await h.profile.ensureOwnProfile(USER, TOKEN);
  assert.deepEqual(creates, [[TOKEN, { profile_revision: null, ...DETAILS }],
    [TOKEN, { profile_revision: null, username: null, display_name: 'Nathan' }]]);
});

function backendHarness(fetcher) {
  let epoch = 0;
  const api = loadTs('../lib/backendApi.ts', {
    'react-native': { Platform: { OS: 'web' } },
    './privateMediaLifecycle': { getPrivateMediaEpoch: () => epoch, getActivePrivateMediaSessionKey: () => null,
      registerPrivateMediaRelease: () => () => {} },
    './privateMediaLogout': { getPrivateMediaSessionKey: () => null },
    './backendConfig': { resolveBackendApiConfig: () => ({ url: 'http://localhost:8000', source: 'test' }),
      getBackendApiUrl: () => 'http://localhost:8000', getBackendConnectionDiagnostics: () => ({}) },
    './videoRequestPayloadPolicy': {},
    './backendErrorPolicy': { getBackendErrorMessage: (_text, status) => `HTTP ${status}` },
  }, { fetch: fetcher, console: { error() {}, warn() {}, info() {} } }, true);
  return { api, bumpEpoch: () => { epoch += 1; } };
}

test('real raw backend dispatch uses original bearer, revision precondition and raw bytes exactly once', async () => {
  const calls = [];
  const body = new Blob(['photo'], { type: 'image/jpeg' });
  const h = backendHarness(async (url, init) => {
    calls.push([url, init]);
    throw new TypeError('Network failed after the server may have stored bytes');
  });
  await assert.rejects(h.api.uploadOwnProfileAvatar(TOKEN, REVISION, body, 'image/jpeg'), /Backend unreachable/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'http://localhost:8000/profile/avatar');
  assert.equal(calls[0][1].headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(calls[0][1].headers['X-Peso-Profile-Revision'], REVISION);
  assert.equal(calls[0][1].headers['Content-Type'], 'image/jpeg');
  assert.equal(calls[0][1].body, body);
  assert.equal(Object.hasOwn(calls[0][1], 'allowLoopbackRetry'), false);
});

for (const operation of [
  { name: 'metadata PUT', path: '/profile', method: 'PUT', body: { profile_revision: REVISION, ...DETAILS },
    dispatch: (api) => api.updateOwnProfileMetadata(TOKEN, { profile_revision: REVISION, ...DETAILS }) },
  { name: 'avatar publication POST', path: `/profile/avatar/${ATTEMPT}/publish`, method: 'POST', body: DETAILS,
    dispatch: (api) => api.publishOwnProfileAvatar(TOKEN, ATTEMPT, DETAILS) },
]) {
  test(`real ${operation.name} dispatch never retries a network failure with an unknown write outcome`, async () => {
    const calls = [];
    const h = backendHarness(async (url, init) => {
      calls.push([url, init]);
      throw new TypeError('Network failed after the server may have committed the profile');
    });
    await assert.rejects(operation.dispatch(h.api), /Backend unreachable/);
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], `http://localhost:8000${operation.path}`);
    assert.equal(calls[0][1].method, operation.method);
    assert.equal(calls[0][1].headers.Authorization, `Bearer ${TOKEN}`);
    assert.equal(calls[0][1].headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(calls[0][1].body), operation.body);
    assert.equal(Object.hasOwn(calls[0][1], 'allowLoopbackRetry'), false);
  });
}

test('real raw backend dispatch expresses missing profile explicitly, and requestJson rejects stale responses', async () => {
  const waiting = deferred();
  let headers;
  const h = backendHarness(async (_url, init) => { headers = init.headers; return waiting.promise; });
  const work = h.api.uploadOwnProfileAvatar(TOKEN, null, new Blob(['photo']), 'image/png');
  h.bumpEpoch();
  waiting.resolve(new Response(JSON.stringify({ attempt_id: ATTEMPT, avatar_path: AVATAR }), { status: 200 }));
  await assert.rejects(work, /session changed/);
  assert.equal(headers['X-Peso-Profile-Revision'], 'absent');
});


test('existing requests still use configured loopback fallback, while backend errors retain status for CAS handling', async () => {
  const calls = [];
  const h = backendHarness(async (url) => {
    calls.push(url);
    if (calls.length === 1) throw new TypeError('Network failed');
    return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
  });
  assert.deepEqual(await h.api.testBackendConnection(), { status: 'ok' });
  assert.deepEqual(calls, ['http://localhost:8000/health', 'http://127.0.0.1:8000/health']);
  const conflict = backendHarness(async () => new Response('{}', { status: 409 }));
  await assert.rejects(conflict.api.updateOwnProfileMetadata(TOKEN, { profile_revision: REVISION, ...DETAILS }),
    (error) => error instanceof conflict.api.BackendHttpError && error.status === 409);
});


test('epoch changes while reading selected bytes or private avatar bytes discard late completions', async () => {
  const reading = deferred();
  const h = profileHarness({}, { fetch: () => reading.promise });
  const upload = h.profile.uploadProfileAvatar(USER, TOKEN, { uri: 'blob:private-selection', mimeType: 'image/jpeg' }, REVISION, DETAILS);
  await new Promise(setImmediate);
  h.bumpEpoch();
  reading.resolve(new Response(new Blob(['photo'], { type: 'image/jpeg' })));
  await assert.rejects(upload, /session changed/);
  assert.deepEqual(h.calls, []);

  const signing = deferred();
  const signed = profileHarness({}, { readAvatar: () => signing.promise });
  const loading = signed.profile.loadOwnProfile(USER, TOKEN);
  await new Promise(setImmediate);
  signed.bumpEpoch();
  signing.resolve({ avatar_data_uri: 'data:image/jpeg;base64,/9j/2Q==', avatar_reupload_required: false, avatar_error: null });
  await assert.rejects(loading, /session changed/);
  assert.deepEqual(signed.calls.map(([kind]) => kind), ['get', 'read-avatar']);
});

function settingsHarness({ picker = async () => ({ canceled: true }), save = async () => record(), initialProfile = record() } = {}) {
  const slots = [];
  let cursor = 0;
  let effects = [];
  let auth = { user: USER, session: { access_token: TOKEN }, mediaSessionKey: `${OWNER}:${SESSION}`, signOut: async () => {} };
  let loadCalls = 0;
  let uploadCalls = 0;
  let releaseAvatar = () => {};
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: initial };
      return [slots[index].value, (next) => {
        slots[index].value = typeof next === 'function' ? next(slots[index].value) : next;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { current: initial };
      return slots[index];
    },
    useEffect(effect, dependencies) {
      const index = cursor++;
      const previous = slots[index];
      if (!previous || dependencies.some((value, at) => value !== previous.dependencies[at])) {
        slots[index] = { dependencies, cleanup: null };
        effects.push(() => {
          previous?.cleanup?.();
          slots[index].cleanup = effect();
        });
      }
    },
  };
  const jsx = (type, props) => ({ type, props });
  const Screen = loadTs('../src/screens/SettingsScreen.tsx', {
    'react': hooks,
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    '@expo/vector-icons': { Ionicons: 'Ionicons' },
    'expo-image-picker': { launchImageLibraryAsync: picker },
    'react-native': { ActivityIndicator: 'ActivityIndicator', Image: 'Image', Platform: { OS: 'web' },
      Pressable: 'Pressable', ScrollView: 'ScrollView', StyleSheet: { create: (styles) => styles },
      Text: 'Text', TextInput: 'TextInput', View: 'View' },
    'react-native-safe-area-context': { SafeAreaView: 'SafeAreaView' },
    '../../context/AuthContext': { useAuth: () => auth },
    '../../lib/backendApi': { BackendHttpError: HttpError },
    '../../lib/privateMediaLifecycle': { getPrivateMediaEpoch: () => 0, registerPrivateMediaRelease: () => () => {} },
    '../../lib/avatarReader': { subscribeProfileAvatarRelease: (callback) => { releaseAvatar = callback; return () => {}; } },
    '../../lib/profile': {
      getProfileDisplayName: () => 'Nathan',
      loadOwnProfile: async () => { loadCalls += 1; return initialProfile; },
      saveOwnProfile: save,
      uploadProfileAvatar: async () => { uploadCalls += 1; return initialProfile; },
    },
    '../../lib/supabase': { supabase: {} },
    '../components/BottomNav': { __esModule: true, default: 'BottomNav', NAV_HEIGHT: 60 },
    '../components/Button': { __esModule: true, default: 'Button' },
    '../components/Input': { __esModule: true, default: 'Input' },
    '../theme/tokens': { __esModule: true, default: { colors: {} } },
  }).default;
  function render() {
    cursor = 0;
    effects = [];
    const tree = Screen({ onBack() {} });
    for (const effect of effects) effect();
    return tree;
  }
  function find(tree, predicate) {
    if (!tree || typeof tree !== 'object') return null;
    if (Array.isArray(tree)) {
      for (const child of tree) { const match = find(child, predicate); if (match) return match; }
      return null;
    }
    if (predicate(tree)) return tree;
    return find(tree.props?.children, predicate);
  }
  return { render, find, setAuth: (next) => { auth = next; }, getAuth: () => auth,
    releaseAvatar: () => releaseAvatar(), counts: () => ({ loadCalls, uploadCalls }) };
}

test('Settings preserves unsaved form fields during same-session JWT refresh', async () => {
  const h = settingsHarness();
  h.render();
  await new Promise(setImmediate);
  let tree = h.render();
  h.find(tree, (node) => node.props?.label === 'Profile').props.onPress();
  tree = h.render();
  h.find(tree, (node) => node.type === 'Input' && node.props.label === 'Username').props.onChangeText('unsaved_draft');
  tree = h.render();
  h.setAuth({ ...h.getAuth(), user: { ...USER }, session: { access_token: 'refreshed-token-same-session' } });
  tree = h.render();
  await new Promise(setImmediate);
  tree = h.render();
  assert.equal(h.find(tree, (node) => node.type === 'Input' && node.props.label === 'Username').props.value, 'unsaved_draft');
  assert.equal(h.counts().loadCalls, 1);
});

test('Settings discards a late image picker result after same-owner session replacement', async () => {
  const waiting = deferred();
  const h = settingsHarness({ picker: () => waiting.promise });
  h.render();
  await new Promise(setImmediate);
  let tree = h.render();
  h.find(tree, (node) => node.props?.label === 'Profile').props.onPress();
  tree = h.render();
  const choosing = h.find(tree, (node) => node.props?.accessibilityLabel === 'Change profile picture').props.onPress();
  h.setAuth({ ...h.getAuth(), mediaSessionKey: `${OWNER}:${OTHER}`, session: { access_token: 'new-session-token' } });
  h.render();
  await new Promise(setImmediate);
  waiting.resolve({ canceled: false, assets: [asset()] });
  await choosing;
  assert.equal(h.counts().uploadCalls, 0);
});

test('Settings keeps original caller token through a save and discards late completion after session replacement', async () => {
  const waiting = deferred();
  let saveToken;
  const h = settingsHarness({ save: (_user, token) => { saveToken = token; return waiting.promise; } });
  h.render();
  await new Promise(setImmediate);
  let tree = h.render();
  h.find(tree, (node) => node.props?.label === 'Profile').props.onPress();
  tree = h.render();
  const saving = h.find(tree, (node) => node.type === 'Button' && node.props.label === 'Save Profile').props.onPress();
  h.setAuth({ ...h.getAuth(), mediaSessionKey: `${OWNER}:${OTHER}`, session: { access_token: 'new-session-token' } });
  h.render();
  await new Promise(setImmediate);
  waiting.resolve(record({ username: 'old_session_result' }));
  await saving;
  tree = h.render();
  assert.equal(saveToken, TOKEN);
  assert.equal(h.find(tree, (node) => node.type === 'Input' && node.props.label === 'Username').props.value, 'nathan');
});


test('all shared profile callers pass original token and current published revision to the memory reader', async () => {
  for (const dispatch of [h => h.profile.loadOwnProfile(USER, TOKEN),
    h => h.profile.saveOwnProfile(USER, TOKEN, REVISION, DETAILS),
    h => h.profile.uploadProfileAvatar(USER, TOKEN, asset(), REVISION, DETAILS)]) {
    const h = profileHarness(); const value = await dispatch(h);
    assert.equal(value.avatar_data_uri, 'data:image/jpeg;base64,/9j/2Q==');
    assert.deepEqual(h.calls.at(-1), ['read-avatar', TOKEN, NEXT_REVISION]);
    assert.ok(h.calls.every(([name]) => name !== 'sign'));
  }
});

test('legacy and unavailable image states preserve confirmed editable metadata without retrying profile writes', async () => {
  for (const image of [{ avatar_data_uri: null, avatar_reupload_required: true, avatar_error: null },
    { avatar_data_uri: null, avatar_reupload_required: false, avatar_error: 'Unable to load profile picture. Reload your profile to retry.' }]) {
    const h = profileHarness({}, { readAvatar: async () => image });
    const value = await h.profile.saveOwnProfile(USER, TOKEN, REVISION, DETAILS);
    assert.equal(value.profile_revision, NEXT_REVISION); assert.equal(value.username, DETAILS.username);
    assert.equal(value.avatar_reupload_required, image.avatar_reupload_required);
    assert.equal(value.avatar_error, image.avatar_error); assert.deepEqual(h.calls.map(([name]) => name), ['put', 'read-avatar']);
  }
});

test('avatar invalidation clears mounted image while preserving Settings unsaved fields and legacy reupload action', async () => {
  const h = settingsHarness({ initialProfile: { ...record(), avatar_data_uri: 'data:image/jpeg;base64,/9j/2Q==', avatar_reupload_required: true } });
  h.render(); await new Promise(setImmediate); let tree = h.render();
  h.find(tree, node => node.props?.label === 'Profile').props.onPress(); tree = h.render();
  assert.equal(h.find(tree, node => node.type === 'Image').props.source.uri, 'data:image/jpeg;base64,/9j/2Q==');
  h.find(tree, node => node.type === 'Input' && node.props.label === 'Username').props.onChangeText('unsaved_picture_name');
  h.releaseAvatar(); tree = h.render();
  assert.equal(h.find(tree, node => node.type === 'Image'), null);
  assert.equal(h.find(tree, node => node.type === 'Input' && node.props.label === 'Username').props.value, 'unsaved_picture_name');
  assert.equal(h.find(tree, node => node.props?.accessibilityLabel === 'Change profile picture').props.disabled, false);
  assert.ok(h.find(tree, node => node.props?.accessibilityRole === 'alert' && typeof node.props.children === 'string' && node.props.children.includes('Re-upload')));
});

test('confirmed profile with an image error keeps metadata editing and exposes the requested retry action', async () => {
  const h = settingsHarness({ initialProfile: { ...record(), avatar_data_uri: null,
    avatar_error: 'Unable to load profile picture. Reload your profile to retry.' } });
  h.render(); await new Promise(setImmediate); let tree = h.render();
  h.find(tree, node => node.props?.label === 'Profile').props.onPress(); tree = h.render();
  assert.ok(h.find(tree, node => node.type === 'Button' && node.props.label === 'Reload Profile'));
  assert.equal(h.find(tree, node => node.type === 'Input' && node.props.label === 'Username').props.editable, true);
  assert.equal(h.find(tree, node => node.props?.accessibilityLabel === 'Change profile picture').props.disabled, false);
});
