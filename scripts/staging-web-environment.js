const { createHash } = require('node:crypto');
const binding = require('../config/staging-web-release-binding.json');
const { STUDENT_SUPABASE_URL } = require('./student-environment');

const STAGING_WEB_ORIGIN = 'https://staging.usepeso.com';
const STAGING_API_ORIGIN = 'https://api-staging.usepeso.com';
const STAGING_API_ID = 'srv-dbrrjqjrjlhs73cbn6b0';
const STAGING_WORKER_ID = 'srv-dbrrjqjrjlhs73cbn6bg';
const fingerprint = (value) => createHash('sha256').update(value || '').digest('hex');

function isStagingProject(env, selected = binding) {
  return selected?.schema_version === 1 && selected.site_name === 'peso-staging-web'
    && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(selected.site_id || '')
    && selected.site_id !== '230da8eb-f00e-45d4-ba54-95f2e26f21c4'
    && selected.site_id !== require('../config/combined-web-release-binding.json').site_id
    && env.SITE_ID === selected.site_id;
}

function validateStagingWebEnvironment(env, selected = binding) {
  const errors = [];
  if (!isStagingProject(env, selected) || selected.status !== 'private-config-verified'
      || selected.site_origin !== STAGING_WEB_ORIGIN || selected.api_url !== STAGING_API_ORIGIN
      || selected.supabase_url !== STUDENT_SUPABASE_URL
      || selected.api_service_id !== STAGING_API_ID || selected.worker_service_id !== STAGING_WORKER_ID) {
    errors.push('Web staging requires the verified dedicated private project and fresh Web MVP services.');
  }
  if (env.PESO_RELEASE_ENV !== 'web-staging' || env.CONTEXT !== 'production'
      || env.NETLIFY === 'true' || env.PULL_REQUEST === 'true') {
    errors.push('Web staging requires an external manual artifact build in the production deploy context.');
  }
  if (env.EXPO_PUBLIC_SUPABASE_URL !== STUDENT_SUPABASE_URL
      || env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL !== STAGING_API_ORIGIN
      || env.EXPO_PUBLIC_AUTH_CHALLENGE_URL !== `${STAGING_WEB_ORIGIN}/auth/turnstile/`
      || env.EXPO_PUBLIC_BACKEND_URL || env.EXPO_PUBLIC_SUPABASE_ANON_KEY
      || env.URL !== STAGING_WEB_ORIGIN
      || (env.DEPLOY_PRIME_URL && env.DEPLOY_PRIME_URL !== STAGING_WEB_ORIGIN)
      || env.EXPO_NO_DOTENV !== '1') {
    errors.push('Web staging requires exact staging origins without backend or legacy-key overrides.');
  }
  const key = env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY || '';
  let stagingKey = key.startsWith('sb_publishable_');
  if (key.startsWith('eyJ')) {
    try {
      const claims = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString());
      stagingKey = claims.ref === 'iseqgaewjpjcxrndibep' && claims.role === 'anon';
    } catch { stagingKey = false; }
  }
  if (!stagingKey || !/^[a-f0-9]{64}$/.test(selected.supabase_public_key_sha256 || '')
      || fingerprint(key) !== selected.supabase_public_key_sha256) {
    errors.push('Web staging requires the independently verified staging public key fingerprint.');
  }
  const turnstile = env.EXPO_PUBLIC_TURNSTILE_SITE_KEY || '';
  if (!turnstile || /^[123]x0{18}/.test(turnstile)
      || !/^[a-f0-9]{64}$/.test(selected.turnstile_site_key_sha256 || '')
      || fingerprint(turnstile) !== selected.turnstile_site_key_sha256) {
    errors.push('Web staging requires the verified real staging Turnstile key.');
  }
  if (typeof selected.private_media_enabled !== 'boolean'
      || env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED !== String(selected.private_media_enabled)
      || (selected.private_media_enabled && selected.media_prerequisites_verified !== true)) {
    errors.push('Web staging media activation must match verified backend and database prerequisites.');
  }
  if (!/^[a-f0-9]{40}$/.test(env.COMMIT_REF || '')) {
    errors.push('Web staging requires the full source commit for artifact evidence.');
  }
  return errors;
}

async function verifyStagingPublicKey(env, request = fetch) {
  const response = await request(`${STUDENT_SUPABASE_URL}/auth/v1/settings`, {
    headers: { apikey: env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY },
    redirect: 'error',
    signal: AbortSignal.timeout(20000),
  });
  await response.body?.cancel();
  if (!response.ok) throw new Error('Public key was rejected by the isolated staging project.');
}

function stagingReleaseIdentity(env, selected = binding) {
  const errors = validateStagingWebEnvironment(env, selected);
  if (errors.length) throw new Error(errors.join('\n'));
  return { release_env: 'web-staging', site_id: selected.site_id, source_commit: env.COMMIT_REF,
    site_origin: STAGING_WEB_ORIGIN, api_url: STAGING_API_ORIGIN,
    supabase_url: STUDENT_SUPABASE_URL, api_service_id: STAGING_API_ID,
    worker_service_id: STAGING_WORKER_ID, private_media_enabled: selected.private_media_enabled };
}

module.exports = { isStagingProject, validateStagingWebEnvironment, stagingReleaseIdentity, verifyStagingPublicKey,
  STAGING_WEB_ORIGIN, STAGING_API_ORIGIN, fingerprint };
