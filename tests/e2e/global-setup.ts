const REQUIRED_STAGING_VARIABLES = [
  'PESO_E2E_WEB_BASE_URL',
  'PESO_E2E_SUPABASE_URL',
  'PESO_E2E_SUPABASE_SERVICE_ROLE_KEY',
  'PESO_E2E_SIGNUP_EMAIL',
  'PESO_E2E_SIGNUP_PASSWORD',
];

export default function globalSetup() {
  if (process.env.PESO_E2E_ENV !== 'staging' || process.env.PESO_E2E_ALLOW_ADMIN_FIXTURES !== 'true') {
    throw new Error(
      'Web E2E requires PESO_E2E_ENV=staging and PESO_E2E_ALLOW_ADMIN_FIXTURES=true.'
    );
  }

  const missing = REQUIRED_STAGING_VARIABLES.filter((name) => !process.env[name]?.trim());
  if (missing.length > 0) {
    throw new Error(`Missing staging E2E variables: ${missing.join(', ')}`);
  }

  for (const name of ['PESO_E2E_WEB_BASE_URL', 'PESO_E2E_SUPABASE_URL']) {
    const url = new URL(process.env[name]!);
    if (url.protocol !== 'https:') {
      throw new Error(`${name} must be HTTPS.`);
    }
  }
}
