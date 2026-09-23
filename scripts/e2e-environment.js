const { STUDENT_SUPABASE_URL } = require('./student-environment');

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
  const web = new URL(env.PESO_E2E_WEB_BASE_URL);
  if (web.protocol !== 'https:' || web.username || web.password || web.search || web.hash) {
    throw new Error('Staging E2E website must be HTTPS without credentials, query or fragment.');
  }
}

module.exports = { assertStagingE2EEnvironment };
