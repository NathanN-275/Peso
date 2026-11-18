const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { setTimeout: nextTimer } = require('node:timers/promises');
const test = require('node:test');
const { createClient } = require('@supabase/supabase-js');

test('a browser-requested PKCE password reset emits PASSWORD_RECOVERY on return', async () => {
  const redirectTo = 'http://localhost/app/reset';
  const callbackCode = 'fixture-recovery-code';
  const user = { id: 'fixture-user', aud: 'authenticated' };
  const values = new Map();
  let challenge;
  let exchanges = 0;

  // Two full page loads share browser storage, as when opening the reset email.
  globalThis.BroadcastChannel = undefined;
  globalThis.document = { visibilityState: 'hidden' };
  globalThis.window = {
    location: new URL(redirectTo),
    history: {
      state: null,
      replaceState(_state, _title, url) {
        window.location = new URL(url);
      },
    },
    addEventListener() {},
    removeEventListener() {},
  };

  const createAuthClient = () => createClient('http://localhost:1', 'fixture-public-key', {
    auth: {
      flowType: 'pkce',
      detectSessionInUrl: true,
      autoRefreshToken: false,
      storage: {
        getItem: key => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
        removeItem: key => values.delete(key),
      },
    },
    global: {
      async fetch(input, init) {
        const url = new URL(input);
        assert.equal(init.method, 'POST');
        const body = JSON.parse(init.body);
        if (url.pathname === '/auth/v1/recover') {
          assert.equal(url.searchParams.get('redirect_to'), redirectTo);
          assert.equal(body.code_challenge_method, 's256');
          challenge = body.code_challenge;
          return Response.json({});
        }

        assert.equal(url.pathname, '/auth/v1/token');
        assert.equal(url.searchParams.get('grant_type'), 'pkce');
        assert.equal(body.auth_code, callbackCode);
        assert.equal(createHash('sha256').update(body.code_verifier).digest('base64url'), challenge);
        exchanges += 1;
        return Response.json({
          access_token: 'fixture-access-token',
          refresh_token: 'fixture-refresh-token',
          token_type: 'bearer',
          expires_in: 3600,
          user,
        });
      },
    },
  }).auth;

  const requestPage = createAuthClient();
  const request = await requestPage.resetPasswordForEmail('fixture@example.invalid', { redirectTo });
  assert.ifError(request.error);
  assert.ok(challenge);

  window.location = new URL(redirectTo);
  window.location.searchParams.set('code', callbackCode);
  const callbackPage = createAuthClient();
  const recoveryUsers = [];
  callbackPage.onAuthStateChange((event, session) => {
    if (event === 'PASSWORD_RECOVERY') recoveryUsers.push(session?.user.id);
  });
  const callback = await callbackPage.initialize();
  assert.ifError(callback.error);
  // The SDK also delivers its callback event on the next timer turn.
  await nextTimer(0);

  assert.equal(exchanges, 1);
  assert.equal(window.location.href, redirectTo);
  assert.ok(recoveryUsers.includes(user.id), 'the returned session must enter password recovery');
});
