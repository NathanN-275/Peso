const assert = require('node:assert/strict');
const test = require('node:test');
const { assertStagingE2EEnvironment } = require('./e2e-environment');
const valid = {
  PESO_E2E_ENV: 'staging', PESO_E2E_ALLOW_ADMIN_FIXTURES: 'true',
  PESO_E2E_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
  PESO_E2E_WEB_BASE_URL: 'https://private-staging.example.com',
  PESO_E2E_SUPABASE_SERVICE_ROLE_KEY: 'fixture-only',
  PESO_E2E_SIGNUP_EMAIL: 'fixture@example.com', PESO_E2E_SIGNUP_PASSWORD: 'fixture-only',
};
test('administrative E2E accepts only the explicit isolated database', () => {
  assert.doesNotThrow(() => assertStagingE2EEnvironment(valid));
  for (const url of ['https://jfgiydtrskpqxyorvvbc.supabase.co',
    'https://attacker.example', 'https://iseqgaewjpjcxrndibep.supabase.co.attacker.example',
    'https://iseqgaewjpjcxrndibep.supabase.co/?redirect=other']) {
    assert.throws(() => assertStagingE2EEnvironment({ ...valid, PESO_E2E_SUPABASE_URL: url }));
  }
});
test('administrative E2E rejects missing authorization and unsafe website URLs', () => {
  for (const change of [{ PESO_E2E_ENV: 'production' }, { PESO_E2E_ALLOW_ADMIN_FIXTURES: 'false' },
    { PESO_E2E_SUPABASE_SERVICE_ROLE_KEY: '' }, { PESO_E2E_WEB_BASE_URL: 'http://example.com' },
    { PESO_E2E_WEB_BASE_URL: 'https://user:password@example.com' }]) {
    assert.throws(() => assertStagingE2EEnvironment({ ...valid, ...change }));
  }
});
