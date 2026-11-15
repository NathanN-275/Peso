const { randomUUID } = require('node:crypto');
const { lstatSync, writeFileSync } = require('node:fs');
const { isAbsolute, join } = require('node:path');
const { RENDER_BETA_WEB_ORIGIN } = require('./release-env');
const { STUDENT_PROJECT, STUDENT_SUPABASE_URL } = require('./student-environment');

function assertPrivateReceiptDirectory(directory) {
  if (!directory || !isAbsolute(directory)) {
    throw new Error('Staging E2E requires an absolute private receipt directory.');
  }
  const info = lstatSync(directory);
  if (!info.isDirectory() || (info.mode & 0o077) !== 0) {
    throw new Error('Staging E2E receipts require a private directory.');
  }
}

function assertStagingE2EEnvironment(env) {
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
  if (env.PESO_E2E_WEB_BASE_URL !== RENDER_BETA_WEB_ORIGIN) {
    throw new Error('Staging E2E must use the exact private staging website origin.');
  }
  assertPrivateReceiptDirectory(env.PESO_E2E_RECEIPT_DIR);
}

function assertStagingVerificationLink(link, callbackPath) {
  let url;
  try {
    url = new URL(link);
  } catch {
    throw new Error('Staging Auth returned an invalid verification link.');
  }
  const redirects = url.searchParams.getAll('redirect_to');
  if (url.origin !== STUDENT_SUPABASE_URL || url.pathname !== '/auth/v1/verify' ||
      url.username || url.password || url.hash ||
      redirects.length !== 1 || redirects[0] !== RENDER_BETA_WEB_ORIGIN + callbackPath) {
    throw new Error('Staging Auth returned an unexpected verification destination.');
  }
}

function recordStagingFixture(directory, kind, email) {
  assertPrivateReceiptDirectory(directory);
  const receipt = join(directory, `${kind}-${randomUUID()}`);
  const identity = { projectRef: STUDENT_PROJECT, kind, email };
  const write = (stage, values) => writeFileSync(
    `${receipt}.${stage}.json`,
    JSON.stringify({ ...identity, ...values, recordedAt: new Date().toISOString() }) + '\n',
    { flag: 'wx', mode: 0o600, flush: true }
  );
  write('intent', {});
  return (userId) => write('created', { userId });
}

module.exports = { assertStagingE2EEnvironment, assertStagingVerificationLink, recordStagingFixture };
