const assert = require('node:assert/strict');
const test = require('node:test');

const { approvedRenderBetaApi, validateReleaseEnv } = require('./release-env');

const approvedBinding = (apiUrl) => ({
  schema_version: 1,
  status: 'accepted',
  api_url: apiUrl,
  image_reference: `ghcr.io/nathann-275/peso-backend@sha256:${'a'.repeat(64)}`,
  azure_deployment_outputs_sha256: 'b'.repeat(64),
  source_workflow_run_id: '123456789',
});

const acceptedRenderBetaBinding = (apiUrl = 'https://peso-beta-api.onrender.com') => ({
  schema_version: 1,
  status: 'accepted',
  api_url: apiUrl,
  blueprint_sha256: 'c'.repeat(64),
  source_commit: 'd'.repeat(40),
  api_service_id: 'srv-betaapi123',
  worker_service_id: 'srv-betaworker456',
});

test('release auth configuration rejects a missing Turnstile site key', () => {
  const result = validateReleaseEnv({
    EXPO_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_example',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://example.com/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://api.example.com',
  });

  assert.deepEqual(result.errors, [
    'Missing EXPO_PUBLIC_TURNSTILE_SITE_KEY.',
  ]);
});

test('release auth configuration accepts a complete HTTPS environment', () => {
  const result = validateReleaseEnv({
    PESO_RELEASE_ENV: 'production',
    EXPO_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_example',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: 'real-site-key',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://example.com/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://api.example.com',
  });

  assert.deepEqual(result, { errors: [], warnings: [] });
});

test('production rejects Cloudflare test keys and insecure public URLs', () => {
  const result = validateReleaseEnv({
    PESO_RELEASE_ENV: 'production',
    EXPO_PUBLIC_SUPABASE_URL: 'http://example.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_example',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: '1x00000000000000000000AA',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'http://example.com/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'not-a-url',
  });

  assert.deepEqual(result.errors, [
    'EXPO_PUBLIC_SUPABASE_URL must be an HTTPS URL.',
    'EXPO_PUBLIC_AUTH_CHALLENGE_URL must be an HTTPS URL.',
    'EXPO_PUBLIC_PRODUCTION_BACKEND_URL must be an HTTPS URL.',
    'Cloudflare Turnstile test site keys are not allowed in production.',
  ]);
});

test('EAS and Netlify production contexts also reject Cloudflare test keys', () => {
  const base = {
    EXPO_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_example',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: '1x00000000000000000000AA',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://example.com/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://api.example.com',
  };

  assert.match(
    validateReleaseEnv({ ...base, EAS_BUILD_PROFILE: 'production' }).errors.join(' '),
    /test site keys are not allowed/i
  );
  assert.match(
    validateReleaseEnv({ ...base, CONTEXT: 'production' }).errors.join(' '),
    /test site keys are not allowed/i
  );
});

test('legacy anon key remains a one-release fallback with a warning', () => {
  const result = validateReleaseEnv({
    PESO_RELEASE_ENV: 'staging',
    EXPO_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
    EXPO_PUBLIC_SUPABASE_ANON_KEY: 'legacy-key',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: '1x00000000000000000000AA',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://example.com/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://api.example.com',
  });

  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.warnings, [
    'EXPO_PUBLIC_SUPABASE_ANON_KEY is deprecated; configure EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY.',
  ]);
});

test('release auth challenge URL rejects the wrong document or embedded parameters', () => {
  const result = validateReleaseEnv({
    PESO_RELEASE_ENV: 'staging',
    EXPO_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_example',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: '1x00000000000000000000AA',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://example.com/not-turnstile/?token=unsafe#fragment',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://api.example.com',
  });

  assert.deepEqual(result.errors, [
    'EXPO_PUBLIC_AUTH_CHALLENGE_URL must point to /auth/turnstile/ without credentials, query, or fragment.',
  ]);
});

test('Student builds require the isolated database, Student API and exact challenge site', () => {
  const apiUrl = 'https://peso-student-api.test.westus3.azurecontainerapps.io';
  const env = {
    PESO_RELEASE_ENV: 'student',
    EXPO_PUBLIC_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_test',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: 'test-site-key',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://main--peso-webapp.netlify.app/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: apiUrl,
  };
  const options = {studentApiBinding: approvedBinding(apiUrl)};
  assert.deepEqual(validateReleaseEnv(env, options).errors, []);
  assert.ok(validateReleaseEnv(env).errors.length, 'the tracked pending binding must block Student builds');
  for (const [name, value] of Object.entries({
    EXPO_PUBLIC_SUPABASE_URL: 'https://jfgiydtrskpqxyorvvbc.supabase.co',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://peso-webapp.netlify.app/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://production.example.com',
  })) assert.ok(validateReleaseEnv({...env, [name]: value}, options).errors.length, name);
  assert.ok(validateReleaseEnv({
    ...env,
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://peso-student-api.attacker.westus3.azurecontainerapps.io',
    PESO_STUDENT_API_URL: 'https://peso-student-api.attacker.westus3.azurecontainerapps.io',
  }, options).errors.length);
  const centralUsApi = 'https://peso-student-api.test.centralus.azurecontainerapps.io';
  assert.ok(validateReleaseEnv({
    ...env,
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: centralUsApi,
  }, {studentApiBinding: approvedBinding(centralUsApi)}).errors.length);
  assert.ok(validateReleaseEnv(env, {studentApiBinding: {status: 'pending'}}).errors.length);
});

test('Render beta builds require peso-staging, the exact beta API, and the private main site', () => {
  const env = {
    PESO_RELEASE_ENV: 'render-beta',
    EXPO_PUBLIC_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_test',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: 'test-site-key',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://main--peso-webapp.netlify.app/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://peso-beta-api.onrender.com',
  };
  const options = { renderBetaBinding: acceptedRenderBetaBinding() };

  assert.deepEqual(validateReleaseEnv(env, options).errors, []);
  assert.ok(validateReleaseEnv(env).errors.length, 'the tracked pending binding must block beta builds');
  for (const [name, value] of Object.entries({
    EXPO_PUBLIC_SUPABASE_URL: 'https://jfgiydtrskpqxyorvvbc.supabase.co',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://peso-webapp.netlify.app/auth/turnstile/',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://peso-beta-api-attacker.onrender.com',
  })) assert.ok(validateReleaseEnv({...env, [name]: value}, options).errors.length, name);
});

test('Render beta binding fails closed on pending, malformed, or non-beta evidence', () => {
  assert.equal(approvedRenderBetaApi({ status: 'pending' }), '');
  assert.equal(approvedRenderBetaApi(acceptedRenderBetaBinding('https://peso-beta-api.onrender.com/path')), '');
  assert.equal(approvedRenderBetaApi({
    ...acceptedRenderBetaBinding(),
    blueprint_sha256: 'not-a-digest',
  }), '');
  assert.equal(
    approvedRenderBetaApi(acceptedRenderBetaBinding()),
    'https://peso-beta-api.onrender.com',
  );
});

test('combined public beta binds the selected database, existing services and exact private site', () => {
  const binding = {
    schema_version: 1, status: 'private-candidate-verified',
    site_id: '11111111-1111-4111-8111-111111111111',
    site_origin: 'https://candidate.example.com', api_url: 'https://candidate-api.example.com',
    api_service_id: 'srv-dak9ohfqj5pc73ac2ga0',
    worker_service_id: 'srv-dak9ohfqj5pc73ac2g8g',
    source_commit: 'a'.repeat(40), blueprint_sha256: 'b'.repeat(64),
  };
  const env = {
    PESO_RELEASE_ENV: 'public-beta', SITE_ID: binding.site_id,
    EXPO_PUBLIC_SUPABASE_URL: 'https://jfgiydtrskpqxyorvvbc.supabase.co',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_fixture',
    EXPO_PUBLIC_TURNSTILE_SITE_KEY: 'real-site-key-fixture',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: `${binding.site_origin}/auth/turnstile/`,
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: binding.api_url,
  };
  assert.deepEqual(validateReleaseEnv(env, { combinedBinding: binding }).errors, []);
  assert.ok(validateReleaseEnv(env).errors.length, 'pending tracked binding blocks deployment');
  for (const change of [
    { SITE_ID: '230da8eb-f00e-45d4-ba54-95f2e26f21c4' },
    { EXPO_PUBLIC_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co' },
    { EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://other.example.com/auth/turnstile/' },
    { EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://other-api.example.com' },
    { EXPO_PUBLIC_BACKEND_URL: 'https://override.example.com' },
    { EXPO_PUBLIC_TURNSTILE_SITE_KEY: '1x00000000000000000000AA' },
  ]) assert.ok(validateReleaseEnv({ ...env, ...change }, { combinedBinding: binding }).errors.length);
  for (const change of [
    { status: 'pending' }, { source_commit: null }, { blueprint_sha256: null },
    { api_service_id: 'srv-other' }, { worker_service_id: 'srv-other' },
    { site_origin: `${binding.site_origin}/path` }, { api_url: `${binding.api_url}/path` },
  ]) assert.ok(validateReleaseEnv(env, { combinedBinding: { ...binding, ...change } }).errors.length);
});
