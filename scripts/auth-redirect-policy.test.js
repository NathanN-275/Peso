const assert = require('node:assert/strict');
const test = require('node:test');

const {
  parseNativeAuthRedirect,
  parseWebAuthRedirect,
  redactAuthParams,
} = require('../lib/auth-redirect');

test('native auth redirects accept only the exact Peso scheme and destinations', () => {
  const confirmation = parseNativeAuthRedirect(
    'pesoapp://login#access_token=access&refresh_token=refresh&type=signup'
  );
  const recovery = parseNativeAuthRedirect(
    'pesoapp://reset-password?code=recovery-code&type=recovery'
  );

  assert.equal(confirmation.trusted, true);
  assert.equal(confirmation.destination, 'login');
  assert.equal(confirmation.accessToken, 'access');
  assert.equal(confirmation.hasSessionParams, false);
  assert.match(confirmation.errorMessage, /no longer supported/i);
  assert.equal(recovery.trusted, true);
  assert.equal(recovery.destination, 'reset-password');
  assert.equal(recovery.code, 'recovery-code');
  assert.equal(recovery.hasSessionParams, true);
});

test('native auth redirects reject unknown schemes, hosts, and path suffixes', () => {
  for (const url of [
    'https://attacker.example/reset-password?code=stolen',
    'pesoapp://attacker/reset-password?code=stolen',
    'pesoapp://reset-password/extra?code=stolen',
    'pesoapp://login.evil.example#access_token=access&refresh_token=refresh',
  ]) {
    assert.equal(parseNativeAuthRedirect(url).trusted, false, url);
  }
});

test('web confirmation and recovery destinations remain distinct', () => {
  const confirmation = parseWebAuthRedirect(
    '/app/login',
    '',
    '#access_token=access&refresh_token=refresh&type=signup'
  );
  const recovery = parseWebAuthRedirect(
    '/app/reset',
    '',
    '#access_token=access&refresh_token=refresh&type=recovery'
  );

  assert.equal(confirmation.destination, 'login');
  assert.equal(confirmation.isRecovery, false);
  assert.equal(recovery.destination, 'reset-password');
  assert.equal(recovery.isRecovery, true);
  assert.equal(parseWebAuthRedirect('/unexpected/app/login', '', '').destination, null);
  assert.equal(
    parseWebAuthRedirect('/unexpected/reset', '?type=recovery', '').isRecovery,
    false
  );
});

test('expired auth links have a specific message and logs redact credentials', () => {
  const parsed = parseNativeAuthRedirect(
    'pesoapp://reset-password#error_code=otp_expired&error_description=Email+link+expired'
  );

  assert.match(parsed.errorMessage, /expired or was already used/i);
  assert.deepEqual(
    redactAuthParams({ code: 'secret', access_token: 'access', refresh_token: 'refresh', type: 'recovery' }),
    { code: '[redacted]', access_token: '[redacted]', refresh_token: '[redacted]', type: 'recovery' }
  );
});
