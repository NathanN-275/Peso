const assert = require('node:assert/strict');
const test = require('node:test');

const {
  buildAuthChallengeUrl,
  isTrustedAuthChallengeMessageSource,
  isTrustedAuthChallengeNavigation,
  parseAuthChallengeMessage,
} = require('../lib/auth-challenge');

test('verified challenge messages return one in-memory token for the expected action', () => {
  const result = parseAuthChallengeMessage(
    JSON.stringify({
      version: 1,
      type: 'peso.turnstile',
      action: 'signup',
      status: 'verified',
      token: 'verified-token',
    }),
    'signup'
  );

  assert.deepEqual(result, {
    ok: true,
    event: {
      action: 'signup',
      status: 'verified',
      token: 'verified-token',
    },
  });
});

test('non-token challenge states are accepted without retaining a token', () => {
  for (const message of [
    { version: 1, type: 'peso.turnstile', action: 'login', status: 'ready' },
    { version: 1, type: 'peso.turnstile', action: 'login', status: 'expired' },
    {
      version: 1,
      type: 'peso.turnstile',
      action: 'login',
      status: 'error',
      code: 'challenge-failed',
    },
  ]) {
    const result = parseAuthChallengeMessage(JSON.stringify(message), 'login');
    assert.equal(result.ok, true);
    assert.equal('token' in result.event, false);
  }
});

test('challenge parser rejects malformed, cross-action, and tokenless verified messages', () => {
  for (const rawMessage of [
    'not-json',
    JSON.stringify({ version: 2, type: 'peso.turnstile', action: 'signup', status: 'ready' }),
    JSON.stringify({ version: 1, type: 'other', action: 'signup', status: 'ready' }),
    JSON.stringify({ version: 1, type: 'peso.turnstile', action: 'login', status: 'ready' }),
    JSON.stringify({ version: 1, type: 'peso.turnstile', action: 'signup', status: 'verified' }),
  ]) {
    assert.equal(parseAuthChallengeMessage(rawMessage, 'signup').ok, false);
  }
});

test('native challenge URL includes only the allowed action and a reset nonce', () => {
  assert.equal(
    buildAuthChallengeUrl(
      'https://example.com/auth/turnstile.html?ignored=value#fragment',
      'reset_password',
      7
    ),
    'https://example.com/auth/turnstile.html?action=reset_password&reset=7'
  );
});

test('native navigation trusts only the configured challenge document', () => {
  const challengeUrl = 'https://example.com/auth/turnstile.html';

  assert.equal(
    isTrustedAuthChallengeNavigation(
      'https://example.com/auth/turnstile.html?action=signup&reset=1',
      challengeUrl
    ),
    true
  );
  assert.equal(
    isTrustedAuthChallengeNavigation('https://example.com/auth/other.html', challengeUrl),
    false
  );
  assert.equal(
    isTrustedAuthChallengeNavigation('https://attacker.example/auth/turnstile.html', challengeUrl),
    false
  );
  assert.equal(
    isTrustedAuthChallengeNavigation(
      'https://example.com/auth/turnstile.html?action=admin&reset=1',
      challengeUrl
    ),
    false
  );
  assert.equal(
    isTrustedAuthChallengeNavigation(
      'https://example.com/auth/turnstile.html?action=signup&reset=1&token=unsafe',
      challengeUrl
    ),
    false
  );
});

test('native bridge messages cannot originate from blank documents', () => {
  const challengeUrl = 'https://example.com/auth/turnstile.html';

  assert.equal(isTrustedAuthChallengeMessageSource('about:blank', challengeUrl), false);
  assert.equal(
    isTrustedAuthChallengeMessageSource(
      'https://example.com/auth/turnstile.html?action=login&reset=2',
      challengeUrl
    ),
    true
  );
});
