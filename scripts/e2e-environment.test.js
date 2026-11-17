const assert = require('node:assert/strict');
const test = require('node:test');
const { assertStagingE2EEnvironment } = require('./e2e-environment');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { assertStagingDeploymentIdentity, recordStagingFixture, assertStagingVerificationLink } = require('./e2e-environment');
const binding = { ...require('../config/staging-web-release-binding.json'),
  site_id: '11111111-2222-4333-8444-555555555555', status: 'private-config-verified' };
const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'peso-e2e-guard-')));
fs.chmodSync(directory, 0o700);
const state = path.join(directory, 'visitor.json');
fs.writeFileSync(state, '{"cookies":[],"origins":[]}', { mode: 0o600 });
test.after(() => fs.rmSync(directory, { recursive: true, force: true }));
const valid = {
  PESO_E2E_ENV: 'staging', PESO_E2E_ALLOW_ADMIN_FIXTURES: 'true',
  PESO_E2E_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
  PESO_E2E_WEB_BASE_URL: binding.site_origin, PESO_E2E_API_URL: binding.api_url,
  PESO_E2E_SITE_ID: binding.site_id, PESO_E2E_SOURCE_SHA: 'a'.repeat(40),
  PESO_E2E_STORAGE_STATE: state, PESO_E2E_RECEIPT_DIR: directory,
  PESO_E2E_SUPABASE_SERVICE_ROLE_KEY: 'fixture-only',
  PESO_E2E_SIGNUP_EMAIL: 'fixture@example.com', PESO_E2E_SIGNUP_PASSWORD: 'fixture-only',
};
test('administrative E2E accepts only the explicit isolated database', () => {
  assert.doesNotThrow(() => assertStagingE2EEnvironment(valid, binding));
  assert.throws(() => assertStagingE2EEnvironment(valid), /exact dedicated/);
  for (const url of ['https://jfgiydtrskpqxyorvvbc.supabase.co',
    'https://attacker.example', 'https://iseqgaewjpjcxrndibep.supabase.co.attacker.example',
    'https://iseqgaewjpjcxrndibep.supabase.co/?redirect=other']) {
    assert.throws(() => assertStagingE2EEnvironment({ ...valid, PESO_E2E_SUPABASE_URL: url }, binding));
  }
});
test('administrative E2E rejects missing authorization and unsafe website URLs', () => {
  for (const change of [{ PESO_E2E_ENV: 'production' }, { PESO_E2E_ALLOW_ADMIN_FIXTURES: 'false' },
    { PESO_E2E_SUPABASE_SERVICE_ROLE_KEY: '' }, { PESO_E2E_WEB_BASE_URL: 'http://example.com' },
    { PESO_E2E_WEB_BASE_URL: 'https://user:password@example.com' }]) {
    assert.throws(() => assertStagingE2EEnvironment({ ...valid, ...change }, binding));
  }
});

test('E2E requires exact website, API, site ID and source', () => {
  for (const change of [{ PESO_E2E_WEB_BASE_URL: 'https://main.usepeso.com' },
    { PESO_E2E_WEB_BASE_URL: `${binding.site_origin}/app` }, { PESO_E2E_API_URL: 'https://other.example' },
    { PESO_E2E_SITE_ID: 'other' }, { PESO_E2E_SOURCE_SHA: 'main' }]) {
    assert.throws(() => assertStagingE2EEnvironment({ ...valid, ...change }, binding));
  }
});

test('reusable visitor state and receipts require private paths outside the repository', () => {
  fs.chmodSync(state, 0o644);
  assert.throws(() => assertStagingE2EEnvironment(valid, binding));
  fs.chmodSync(state, 0o600);
  const link = path.join(directory, 'symlink');
  fs.symlinkSync(state, link);
  assert.throws(() => assertStagingE2EEnvironment({ ...valid, PESO_E2E_STORAGE_STATE: link }, binding));
  for (const location of ['relative', path.resolve(__dirname, '..')]) {
    assert.throws(() => assertStagingE2EEnvironment({ ...valid, PESO_E2E_RECEIPT_DIR: location }, binding));
  }
  fs.mkdirSync(path.join(directory, '.git'));
  assert.throws(() => assertStagingE2EEnvironment(valid, binding), /every Git checkout/);
  fs.rmdirSync(path.join(directory, '.git'));
});

test('hosted artifact identity must match the source, database and fresh service pair', () => {
  const identity = { release_env: 'web-staging', site_id: binding.site_id,
    source_commit: valid.PESO_E2E_SOURCE_SHA, site_origin: binding.site_origin,
    api_url: binding.api_url, supabase_url: binding.supabase_url,
    api_service_id: binding.api_service_id, worker_service_id: binding.worker_service_id,
    private_media_enabled: false };
  assert.doesNotThrow(() => assertStagingDeploymentIdentity(identity, valid, binding));
  for (const key of Object.keys(identity)) {
    assert.throws(() => assertStagingDeploymentIdentity({ ...identity, [key]: 'wrong' }, valid, binding));
  }
});

test('fixture receipts retain project and created owner identity without passwords', () => {
  const record = recordStagingFixture(directory, 'login', 'unique@example.com');
  record('fixture-owner');
  const files = fs.readdirSync(directory).filter(name => /\.(intent|created)\.json$/.test(name));
  assert.equal(files.length, 2);
  for (const file of files) {
    const value = JSON.parse(fs.readFileSync(path.join(directory, file)));
    assert.equal(value.projectRef, 'iseqgaewjpjcxrndibep');
    assert.equal(fs.statSync(path.join(directory, file)).mode & 0o077, 0);
    assert.equal(value.password, undefined);
    assert.ok(Number.isFinite(Date.parse(value.recordedAt)));
  }
  assert.throws(() => record('different-owner'), /EEXIST/);
});

test('verification links cannot navigate into another project or redirect origin', () => {
  const make = redirect => `https://iseqgaewjpjcxrndibep.supabase.co/auth/v1/verify?token=fixture&redirect_to=${encodeURIComponent(redirect)}`;
  assert.doesNotThrow(() => assertStagingVerificationLink(make('https://staging.usepeso.com/app/login'), '/app/login'));
  for (const destination of ['https://production.example/app/login', 'https://staging.usepeso.com/app/reset']) {
    assert.throws(() => assertStagingVerificationLink(make(destination), '/app/login'));
  }
  assert.throws(() => assertStagingVerificationLink(make('https://staging.usepeso.com/app/login') + '&redirect_to=other', '/app/login'));
  assert.throws(() => assertStagingVerificationLink('invalid-fixture-token', '/app/reset'),
    /^Error: Staging Auth returned an invalid verification link\.$/);
});
