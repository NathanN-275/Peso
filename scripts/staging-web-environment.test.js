const assert = require('node:assert/strict');
const test = require('node:test');
const { buildScript, buildEnvironment, APP_SITE_ID } = require('./netlify-build');
const { validateReleaseEnv } = require('./release-env');
const { fingerprint, stagingReleaseIdentity, verifyStagingPublicKey } = require('./staging-web-environment');
const historicalApiId = require('../config/combined-web-release-binding.json').api_service_id;
const binding = { ...require('../config/staging-web-release-binding.json'),
  site_id: '11111111-2222-4333-8444-555555555555', status: 'private-config-verified',
  supabase_public_key_sha256: fingerprint('sb_publishable_staging_fixture'),
  turnstile_site_key_sha256: fingerprint('real-staging-widget-fixture') };
const env = { PESO_RELEASE_ENV: 'web-staging', SITE_ID: binding.site_id, CONTEXT: 'production',
  COMMIT_REF: 'a'.repeat(40), EXPO_NO_DOTENV: '1', URL: binding.site_origin,
  EXPO_PUBLIC_SUPABASE_URL: binding.supabase_url,
  EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_staging_fixture',
  EXPO_PUBLIC_TURNSTILE_SITE_KEY: 'real-staging-widget-fixture',
  EXPO_PUBLIC_AUTH_CHALLENGE_URL: `${binding.site_origin}/auth/turnstile/`,
  EXPO_PUBLIC_PRODUCTION_BACKEND_URL: binding.api_url, EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'false' };
const validate = (change = {}, selected = binding) =>
  validateReleaseEnv({ ...env, ...change }, { stagingBinding: selected }).errors;

test('dedicated staging forces its guard while preserving historical dispatch', () => {
  assert.equal(buildScript(env, undefined, binding), 'web:build:release');
  const weaker = { ...env, PESO_RELEASE_ENV: 'production' };
  assert.equal(buildEnvironment(weaker, undefined, binding).PESO_RELEASE_ENV, 'web-staging');
  assert.equal(weaker.PESO_RELEASE_ENV, 'production');
  assert.equal(buildScript({ SITE_ID: APP_SITE_ID, CONTEXT: 'branch-deploy', BRANCH: 'main' }), 'web:build:release');
  for (const change of [{ SITE_ID: 'other' }, { CONTEXT: 'deploy-preview' }, { CONTEXT: 'branch-deploy' },
    { CONTEXT: undefined }, { NETLIFY: 'true' }, { PULL_REQUEST: 'true' }]) {
    assert.throws(() => buildScript({ ...env, ...change }, undefined, binding));
    assert.ok(validate(change).length);
  }
});

test('staging requires exact verified identities, keys, source and origins', () => {
  assert.deepEqual(validate(), []);
  assert.ok(validateReleaseEnv(env).errors.length, 'pending tracked binding must block');
  for (const change of [{ status: 'pending' }, { site_id: APP_SITE_ID }, { schema_version: 2 },
    { site_origin: 'https://other.example' }, { api_url: 'https://other.example' },
    { supabase_url: 'https://jfgiydtrskpqxyorvvbc.supabase.co' },
    { api_service_id: historicalApiId }, { worker_service_id: 'srv-other' },
    { supabase_public_key_sha256: null }, { turnstile_site_key_sha256: null }]) {
    assert.ok(validate({}, { ...binding, ...change }).length, JSON.stringify(change));
  }
  for (const change of [{ PESO_RELEASE_ENV: 'production' }, { COMMIT_REF: 'main' },
    { EXPO_NO_DOTENV: undefined }, { URL: 'https://main.usepeso.com' },
    { DEPLOY_PRIME_URL: 'https://preview.example.com' },
    { EXPO_PUBLIC_SUPABASE_URL: 'https://jfgiydtrskpqxyorvvbc.supabase.co' },
    { EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_production_fixture' },
    { EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_secret_fixture' },
    { EXPO_PUBLIC_SUPABASE_ANON_KEY: 'legacy-override' }, { EXPO_PUBLIC_BACKEND_URL: 'https://override.example' }]) {
    assert.ok(validate(change).length, JSON.stringify(change));
  }
  for (const origin of ['https://api-staging.usepeso.com/', 'https://api-staging.usepeso.com/path',
    'https://api-staging.usepeso.com:443', 'https://user:pass@api-staging.usepeso.com',
    'https://api-staging.usepeso.com.attacker.example', 'http://api-staging.usepeso.com']) {
    assert.ok(validate({ EXPO_PUBLIC_PRODUCTION_BACKEND_URL: origin }).length, origin);
  }
  for (const suffix of ['?x=1', '#fragment', '/', '../turnstile/']) {
    assert.ok(validate({ EXPO_PUBLIC_AUTH_CHALLENGE_URL: env.EXPO_PUBLIC_AUTH_CHALLENGE_URL + suffix }).length);
  }
});

test('staging rejects production JWTs and test CAPTCHA even with recorded fingerprints', () => {
  for (const key of ['1x00000000000000000000AA', '2x00000000000000000000AB',
    '1x00000000000000000000BB', '2x00000000000000000000BB', '3x00000000000000000000FF']) {
    assert.ok(validate({ EXPO_PUBLIC_TURNSTILE_SITE_KEY: key },
      { ...binding, turnstile_site_key_sha256: fingerprint(key) }).length);
  }
  const key = `eyJhbGciOiJIUzI1NiJ9.${Buffer.from(JSON.stringify({
    ref: 'jfgiydtrskpqxyorvvbc', role: 'anon' })).toString('base64url')}.fixture`;
  assert.ok(validate({ EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: key },
    { ...binding, supabase_public_key_sha256: fingerprint(key) }).length);
});

test('media activation requires matching backend/database prerequisites', () => {
  const enabled = { ...binding, private_media_enabled: true };
  assert.ok(validate({ EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'true' }).length);
  assert.ok(validate({ EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'true' }, enabled).length);
  assert.deepEqual(validate({ EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'true' },
    { ...enabled, media_prerequisites_verified: true }), []);
  assert.equal(stagingReleaseIdentity(env, binding).site_id, binding.site_id);
  assert.throws(() => stagingReleaseIdentity(env));
});

test('opaque keys must be accepted by the exact isolated Auth endpoint', async () => {
  let requested;
  await verifyStagingPublicKey(env, async (url, options) => {
    requested = { url, options };
    return { ok: true, body: { cancel: async () => {} } };
  });
  assert.equal(requested.url, `${binding.supabase_url}/auth/v1/settings`);
  assert.equal(requested.options.headers.apikey, env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
  assert.equal(requested.options.redirect, 'error');
  await assert.rejects(verifyStagingPublicKey(env, async () => ({ ok: false })), /rejected/);
});
