const { STUDENT_PROJECT, STUDENT_SUPABASE_URL } = require('./student-environment');
const { lstatSync, realpathSync, writeFileSync, existsSync } = require('node:fs');
const { isAbsolute, resolve, relative, dirname, join } = require('node:path');
const { randomUUID } = require('node:crypto');
const binding = require('../config/staging-web-release-binding.json');
const { isStagingProject, STAGING_WEB_ORIGIN, STAGING_API_ORIGIN } = require('./staging-web-environment');

function assertPrivatePath(value, directory = false) {
  if (!value || !isAbsolute(value)) throw new Error('E2E state and receipts require absolute private paths.');
  const info = lstatSync(value);
  const location = relative(resolve(__dirname, '..'), realpathSync(value));
  if (info.isSymbolicLink() || (directory ? !info.isDirectory() : !info.isFile())
      || (info.mode & 0o077) !== 0 || !location.startsWith(`..${require('node:path').sep}`)) {
    throw new Error('E2E state and receipts must be private and outside the repository.');
  }
  if (!directory) assertPrivatePath(dirname(value), true);
  for (let parent = directory ? realpathSync(value) : dirname(realpathSync(value));;) {
    if (existsSync(join(parent, '.git'))) throw new Error('E2E private state must be outside every Git checkout.');
    const next = dirname(parent);
    if (next === parent) break;
    parent = next;
  }
}

function assertStagingE2EEnvironment(env, selected = binding) {
  if (env.PESO_E2E_ENV !== 'staging' || env.PESO_E2E_ALLOW_ADMIN_FIXTURES !== 'true') {
    throw new Error('Web E2E requires explicit staging administrative fixture authorization.');
  }
  if (env.PESO_E2E_SUPABASE_URL !== STUDENT_SUPABASE_URL) {
    throw new Error('Administrative Web E2E fixtures must target the exact peso-staging Supabase project.');
  }
  const required = ['PESO_E2E_WEB_BASE_URL', 'PESO_E2E_SUPABASE_SERVICE_ROLE_KEY',
    'PESO_E2E_SIGNUP_EMAIL', 'PESO_E2E_SIGNUP_PASSWORD'];
  const missing = required.filter((name) => !env[name]?.trim());
  if (missing.length) throw new Error(`Missing staging E2E variables: ${missing.join(', ')}.`);
  if (env.PESO_E2E_WEB_BASE_URL !== STAGING_WEB_ORIGIN
      || env.PESO_E2E_API_URL !== STAGING_API_ORIGIN
      || !isStagingProject({ SITE_ID: env.PESO_E2E_SITE_ID }, selected)
      || selected.status !== 'private-config-verified'
      || selected.site_origin !== STAGING_WEB_ORIGIN || selected.api_url !== STAGING_API_ORIGIN
      || selected.supabase_url !== STUDENT_SUPABASE_URL
      || selected.api_service_id !== 'srv-dbrrjqjrjlhs73cbn6b0'
      || selected.worker_service_id !== 'srv-dbrrjqjrjlhs73cbn6bg'
      || !/^[a-f0-9]{40}$/.test(env.PESO_E2E_SOURCE_SHA || '')) {
    throw new Error('Staging E2E requires the exact dedicated site, API, database and selected source.');
  }
  assertPrivatePath(env.PESO_E2E_STORAGE_STATE);
  assertPrivatePath(env.PESO_E2E_RECEIPT_DIR, true);
}

function assertStagingDeploymentIdentity(identity, env, selected = binding) {
  assertStagingE2EEnvironment(env, selected);
  const expected = { release_env: 'web-staging', site_id: selected.site_id,
    source_commit: env.PESO_E2E_SOURCE_SHA, site_origin: STAGING_WEB_ORIGIN,
    api_url: STAGING_API_ORIGIN, supabase_url: STUDENT_SUPABASE_URL,
    api_service_id: selected.api_service_id, worker_service_id: selected.worker_service_id,
    private_media_enabled: selected.private_media_enabled };
  if (!identity || Object.entries(expected).some(([key, value]) => identity[key] !== value)) {
    throw new Error('Hosted staging artifact identity does not match the approved E2E binding.');
  }
}

function recordStagingFixture(directory, kind, email) {
  assertPrivatePath(directory, true);
  const receipt = join(directory, `${kind}-${randomUUID()}`);
  const write = (stage, values) => writeFileSync(`${receipt}.${stage}.json`,
    JSON.stringify({ projectRef: STUDENT_PROJECT, kind, email, ...values, recordedAt: new Date().toISOString() }) + '\n',
    { flag: 'wx', mode: 0o600, flush: true });
  write('intent', {});
  return (userId) => write('created', { userId });
}

function assertStagingVerificationLink(value, callback) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error('Staging Auth returned an invalid verification link.');
  }
  if (url.origin !== STUDENT_SUPABASE_URL || url.pathname !== '/auth/v1/verify'
      || url.username || url.password || url.hash
      || !['/app/login', '/app/reset'].includes(callback)
      || url.searchParams.getAll('redirect_to').length !== 1
      || url.searchParams.get('redirect_to') !== STAGING_WEB_ORIGIN + callback) {
    throw new Error('Staging Auth returned an unexpected verification destination.');
  }
}

module.exports = { assertStagingE2EEnvironment, assertStagingDeploymentIdentity,
  recordStagingFixture, assertStagingVerificationLink };
