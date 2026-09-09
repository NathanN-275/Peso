// Permanent allowlist: changing Student's database requires a new reviewed ADR.
const STUDENT_PROJECT = 'iseqgaewjpjcxrndibep';
const PRODUCTION_PROJECT = 'jfgiydtrskpqxyorvvbc';
const STUDENT_SUPABASE_URL = `https://${STUDENT_PROJECT}.supabase.co`;
const STUDENT_ORIGIN = 'https://main--peso-webapp.netlify.app';
const crypto = require('node:crypto');

function validateDatabaseUrl(value, { scaler = false } = {}) {
  try {
    const url = new URL(value);
    const username = decodeURIComponent(url.username);
    const role = scaler ? 'peso_azure_scaler_student' : 'postgres';
    const direct = url.hostname === `db.${STUDENT_PROJECT}.supabase.co` && username === role;
    const pooler = /^aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com$/.test(url.hostname) &&
      username === `${role}.${STUDENT_PROJECT}`;
    return ['postgres:', 'postgresql:'].includes(url.protocol) &&
      (direct || pooler) && Boolean(url.password) && url.pathname === '/postgres' &&
      ['', '5432', '6543'].includes(url.port) && !url.hash &&
      url.searchParams.getAll('sslmode').length === 1 &&
      ['require', 'verify-full'].includes(url.searchParams.get('sslmode')) &&
      [...url.searchParams.keys()].every((key) => key === 'sslmode');
  } catch {
    return false;
  }
}

function validateStudentEnvironment(env, { databaseOnly = false } = {}) {
  const errors = [];
  if (!validateDatabaseUrl(env.SUPABASE_DB_URL)) {
    errors.push('SUPABASE_DB_URL must be an encrypted peso-staging owner connection.');
  }
  if (databaseOnly) return errors;
  for (const name of ['RUNTIME_SUPABASE_URL', 'EXPO_PUBLIC_SUPABASE_URL']) {
    if (env[name] !== STUDENT_SUPABASE_URL) errors.push(`${name} must target peso-staging exactly.`);
  }
  if (!validateDatabaseUrl(env.SCALER_POSTGRES_CONNECTION, { scaler: true })) {
    errors.push('SCALER_POSTGRES_CONNECTION must use the isolated Student scaler login and encrypted connection.');
  }
  if (env.STUDENT_NETLIFY_ORIGIN !== STUDENT_ORIGIN) {
    errors.push('STUDENT_NETLIFY_ORIGIN must be the exact main branch test site.');
  }
  if (!env.RUNTIME_SUPABASE_JWT_SECRET) {
    errors.push('Missing RUNTIME_SUPABASE_JWT_SECRET.');
  }
  // Legacy Supabase JWTs carry a project ref. Never log their contents.
  for (const name of ['RUNTIME_SUPABASE_SERVICE_ROLE_KEY', 'EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY']) {
    const key = env[name];
    if (!key) { errors.push(`Missing ${name}.`); continue; }
    if (key.startsWith('eyJ')) {
      try {
        const payload = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString());
        const role = name.startsWith('RUNTIME') ? 'service_role' : 'anon';
        if (payload.ref !== STUDENT_PROJECT || payload.role !== role) throw new Error('wrong project or role');
      } catch { errors.push(`${name} is not a peso-staging key with the expected role.`); }
    } else if (!key.startsWith(name.startsWith('RUNTIME') ? 'sb_secret_' : 'sb_publishable_')) {
      errors.push(`${name} has an unrecognized key format.`);
    }
  }
  return errors;
}

async function verifyStudentKeys(env) {
  // Opaque keys have no readable project ref. Verify every credential against
  // the allowlisted project before it can be written to Key Vault.
  for (const [name, path] of [
    ['EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY', '/auth/v1/settings'],
    ['RUNTIME_SUPABASE_SERVICE_ROLE_KEY', '/auth/v1/admin/users?page=1&per_page=1'],
  ]) {
    const key = env[name];
    const response = await fetch(STUDENT_SUPABASE_URL + path, {
      headers: { apikey: key, Authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(20000),
    });
    await response.body?.cancel();
    if (!response.ok) throw new Error(`${name} was rejected by peso-staging.`);
  }

  // A JWT secret has no project identifier. Prove it belongs to peso-staging by
  // signing a short-lived service token and asking only the allowlisted project
  // to verify it. Never print the secret or generated token.
  const now = Math.floor(Date.now() / 1000);
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const unsigned = `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({
    aud: 'authenticated', exp: now + 60, iat: now, iss: 'supabase',
    ref: STUDENT_PROJECT, role: 'service_role', sub: 'peso-student-release-check',
  })}`;
  const signature = crypto.createHmac('sha256', env.RUNTIME_SUPABASE_JWT_SECRET)
    .update(unsigned).digest('base64url');
  const token = `${unsigned}.${signature}`;
  const jwtResponse = await fetch(`${STUDENT_SUPABASE_URL}/rest/v1/`, {
    headers: {
      apikey: env.RUNTIME_SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${token}`,
    },
    signal: AbortSignal.timeout(20000),
  });
  await jwtResponse.body?.cancel();
  if (!jwtResponse.ok) throw new Error('RUNTIME_SUPABASE_JWT_SECRET was rejected by peso-staging.');
}

if (require.main === module) {
  const errors = validateStudentEnvironment(process.env, { databaseOnly: process.argv.includes('--database-only') });
  for (const error of errors) console.error(error);
  process.exitCode = errors.length ? 1 : 0;
  if (!errors.length && process.argv.includes('--verify-keys')) {
    verifyStudentKeys(process.env).catch(() => {
      console.error('Student credential verification failed; deployment is blocked.');
      process.exitCode = 1;
    });
  }
}

module.exports = { STUDENT_PROJECT, PRODUCTION_PROJECT, STUDENT_SUPABASE_URL, STUDENT_ORIGIN,
  validateDatabaseUrl, validateStudentEnvironment, verifyStudentKeys };
