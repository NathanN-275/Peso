const REQUIRED_PUBLIC_VARIABLES = [
  'EXPO_PUBLIC_SUPABASE_URL',
  'EXPO_PUBLIC_TURNSTILE_SITE_KEY',
  'EXPO_PUBLIC_AUTH_CHALLENGE_URL',
  'EXPO_PUBLIC_PRODUCTION_BACKEND_URL',
];
const URL_VARIABLES = [
  'EXPO_PUBLIC_SUPABASE_URL',
  'EXPO_PUBLIC_AUTH_CHALLENGE_URL',
  'EXPO_PUBLIC_PRODUCTION_BACKEND_URL',
];
const TURNSTILE_TEST_SITE_KEYS = new Set([
  '1x00000000000000000000AA',
  '2x00000000000000000000AB',
  '1x00000000000000000000BB',
  '2x00000000000000000000BB',
  '3x00000000000000000000FF',
]);

function clean(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function isHttpsUrl(value) {
  try {
    return new URL(value).protocol === 'https:';
  } catch {
    return false;
  }
}

function isExactAuthChallengeUrl(value) {
  try {
    const url = new URL(value);
    return (
      url.pathname.replace(/\/+$/g, '') === '/auth/turnstile' &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash
    );
  } catch {
    return false;
  }
}

function validateReleaseEnv(environment) {
  const errors = REQUIRED_PUBLIC_VARIABLES
    .filter((name) => !clean(environment[name]))
    .map((name) => `Missing ${name}.`);
  const publishableKey = clean(environment.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
  const legacyAnonKey = clean(environment.EXPO_PUBLIC_SUPABASE_ANON_KEY);

  for (const name of URL_VARIABLES) {
    const value = clean(environment[name]);
    if (value && !isHttpsUrl(value)) {
      errors.push(`${name} must be an HTTPS URL.`);
    }
  }

  const challengeUrl = clean(environment.EXPO_PUBLIC_AUTH_CHALLENGE_URL);
  if (challengeUrl && !isExactAuthChallengeUrl(challengeUrl)) {
    errors.push(
      'EXPO_PUBLIC_AUTH_CHALLENGE_URL must point to /auth/turnstile/ without credentials, query, or fragment.'
    );
  }

  const releaseEnvironment = clean(
    environment.PESO_RELEASE_ENV || environment.EAS_BUILD_PROFILE || environment.CONTEXT
  );

  if (
    releaseEnvironment === 'production' &&
    TURNSTILE_TEST_SITE_KEYS.has(clean(environment.EXPO_PUBLIC_TURNSTILE_SITE_KEY))
  ) {
    errors.push('Cloudflare Turnstile test site keys are not allowed in production.');
  }

  if (!publishableKey && !legacyAnonKey) {
    errors.push(
      'Missing EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY (or the temporary EXPO_PUBLIC_SUPABASE_ANON_KEY fallback).'
    );
  }

  return {
    errors,
    warnings: !publishableKey && legacyAnonKey
      ? ['EXPO_PUBLIC_SUPABASE_ANON_KEY is deprecated; configure EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY.']
      : [],
  };
}

function runCli() {
  const result = validateReleaseEnv(process.env);

  for (const warning of result.warnings) {
    console.warn(`Release configuration warning: ${warning}`);
  }

  if (result.errors.length > 0) {
    console.error('Release configuration is invalid:');
    for (const error of result.errors) {
      console.error(`- ${error}`);
    }
    process.exitCode = 1;
    return;
  }

  console.log('Release configuration is valid.');
}

if (require.main === module) {
  runCli();
}

module.exports = {
  validateReleaseEnv,
};
