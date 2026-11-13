const assert = require('node:assert/strict');
const { chmodSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const test = require('node:test');
const { assertStagingE2EEnvironment, assertStagingVerificationLink, recordStagingFixture } = require('./e2e-environment');
const valid = {
  PESO_E2E_ENV: 'staging', PESO_E2E_ALLOW_ADMIN_FIXTURES: 'true',
  PESO_E2E_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
  PESO_E2E_WEB_BASE_URL: 'https://main.usepeso.com',
  PESO_E2E_SUPABASE_SERVICE_ROLE_KEY: 'fixture-only',
  PESO_E2E_SIGNUP_EMAIL: 'fixture@example.com', PESO_E2E_SIGNUP_PASSWORD: 'fixture-only',
};

function privateDirectory(t) {
  const directory = mkdtempSync(join(tmpdir(), 'peso-e2e-receipts-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test('administrative E2E accepts only the exact isolated database and website', (t) => {
  const settings = { ...valid, PESO_E2E_RECEIPT_DIR: privateDirectory(t) };
  assert.doesNotThrow(() => assertStagingE2EEnvironment(settings));
  for (const url of ['https://jfgiydtrskpqxyorvvbc.supabase.co',
    'https://attacker.example', 'https://iseqgaewjpjcxrndibep.supabase.co.attacker.example',
    'https://iseqgaewjpjcxrndibep.supabase.co/?redirect=other']) {
    assert.throws(() => assertStagingE2EEnvironment({ ...settings, PESO_E2E_SUPABASE_URL: url }));
  }
  for (const url of ['http://main.usepeso.com', 'https://main--peso-webapp.netlify.app', 'https://usepeso.com',
    'https://unrelated.example', 'https://user:password@main.usepeso.com',
    `${valid.PESO_E2E_WEB_BASE_URL}:8443`, `${valid.PESO_E2E_WEB_BASE_URL}/app`,
    `${valid.PESO_E2E_WEB_BASE_URL}?redirect=other`]) {
    assert.throws(() => assertStagingE2EEnvironment({ ...settings, PESO_E2E_WEB_BASE_URL: url }));
  }
});
test('administrative E2E requires authorization and private receipt storage', (t) => {
  const directory = privateDirectory(t);
  const settings = { ...valid, PESO_E2E_RECEIPT_DIR: directory };
  for (const change of [{ PESO_E2E_ENV: 'production' }, { PESO_E2E_ALLOW_ADMIN_FIXTURES: 'false' },
    { PESO_E2E_SUPABASE_SERVICE_ROLE_KEY: '' }, { PESO_E2E_RECEIPT_DIR: '' },
    { PESO_E2E_RECEIPT_DIR: 'relative' }]) {
    assert.throws(() => assertStagingE2EEnvironment({ ...settings, ...change }));
  }
  chmodSync(directory, 0o755);
  assert.throws(() => assertStagingE2EEnvironment(settings), /private directory/);
});

test('generated links stay on staging and return to the intended Auth route', () => {
  const callback = `${valid.PESO_E2E_WEB_BASE_URL}/app/reset`;
  const link = new URL('/auth/v1/verify', valid.PESO_E2E_SUPABASE_URL);
  link.searchParams.set('token', 'fixture-only');
  link.searchParams.set('redirect_to', callback);
  assert.doesNotThrow(() => assertStagingVerificationLink(link.href, '/app/reset'));
  assert.throws(() => assertStagingVerificationLink(link.href, '/app/login'));
  assert.throws(() => assertStagingVerificationLink(link.href.replace(link.origin, 'https://unrelated.example'), '/app/reset'));
  assert.throws(() => assertStagingVerificationLink(link.href.replace('/auth/v1/verify', '/auth/v1/token'), '/app/reset'));
  link.searchParams.set('redirect_to', 'https://main--peso-webapp.netlify.app/app/reset');
  assert.throws(() => assertStagingVerificationLink(link.href, '/app/reset'));
  link.searchParams.set('redirect_to', callback);
  link.searchParams.append('redirect_to', 'https://unrelated.example');
  assert.throws(() => assertStagingVerificationLink(link.href, '/app/reset'));
  assert.throws(() => assertStagingVerificationLink('invalid-fixture-token', '/app/reset'),
    /^Error: Staging Auth returned an invalid verification link\.$/);
});

test('fixture creation leaves a private intent even when no account ID was returned', (t) => {
  const directory = privateDirectory(t);
  const recordCreated = recordStagingFixture(directory, 'signup', valid.PESO_E2E_SIGNUP_EMAIL);
  const [intentName] = readdirSync(directory);
  assert.match(intentName, /^signup-.*\.intent\.json$/);
  const read = (name) => {
    const path = join(directory, name);
    assert.equal(statSync(path).mode & 0o777, 0o600);
    const { recordedAt, ...data } = JSON.parse(readFileSync(path, 'utf8'));
    assert.ok(Number.isFinite(Date.parse(recordedAt)));
    return data;
  };
  const expected = { projectRef: 'iseqgaewjpjcxrndibep', kind: 'signup', email: valid.PESO_E2E_SIGNUP_EMAIL };
  assert.deepEqual(read(intentName), expected);
  recordCreated('fixture-user-id');
  const createdName = intentName.replace('.intent.json', '.created.json');
  assert.deepEqual(read(createdName), { ...expected, userId: 'fixture-user-id' });
  assert.throws(() => recordCreated('unexpected-id'), { code: 'EEXIST' });
});
