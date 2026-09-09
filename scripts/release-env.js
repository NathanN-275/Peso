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
const STUDENT_API_BINDING_PATH = require('node:path').resolve(
  __dirname,
  '../config/student-api-release-binding.json'
);

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

function loadStudentApiBinding() {
  try {
    return JSON.parse(require('node:fs').readFileSync(STUDENT_API_BINDING_PATH, 'utf8'));
  } catch {
    return null;
  }
}

function approvedStudentApi(binding) {
  if (!binding || binding.schema_version !== 1 || binding.status !== 'accepted' ||
      !/^ghcr\.io\/nathann-275\/peso-backend@sha256:[a-f0-9]{64}$/.test(binding.image_reference ?? '') ||
      !/^[a-f0-9]{64}$/.test(binding.azure_deployment_outputs_sha256 ?? '') ||
      !/^[1-9][0-9]*$/.test(binding.source_workflow_run_id ?? '')) return '';
  try {
    const api = new URL(binding.api_url);
    const hostname = /^peso-student-api\.[a-z0-9-]+\.centralus\.azurecontainerapps\.io$/;
    return api.protocol === 'https:' && !api.port && api.origin === binding.api_url &&
      hostname.test(api.hostname) ? api.origin : '';
  } catch {
    return '';
  }
}

function validateReleaseEnv(environment, { studentApiBinding = loadStudentApiBinding() } = {}) {
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

  if (releaseEnvironment === 'student') {
    const { STUDENT_SUPABASE_URL, STUDENT_ORIGIN } = require('./student-environment');
    const expectedStudentApi = approvedStudentApi(studentApiBinding);
    if (clean(environment.EXPO_PUBLIC_SUPABASE_URL) !== STUDENT_SUPABASE_URL) {
      errors.push('Student website must use the permanent peso-staging Supabase project.');
    }
    try {
      const api = new URL(clean(environment.EXPO_PUBLIC_PRODUCTION_BACKEND_URL));
      const challenge = new URL(challengeUrl);
      if (!expectedStudentApi || api.origin !== expectedStudentApi ||
          api.origin !== clean(environment.EXPO_PUBLIC_PRODUCTION_BACKEND_URL) || api.protocol !== 'https:' ||
          api.port || challenge.origin !== STUDENT_ORIGIN) {
        throw new Error('invalid Student endpoint');
      }
    } catch {
      errors.push('Student website must use the exact approved Student API and test-site challenge origin.');
    }
  }

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
  approvedStudentApi,
  loadStudentApiBinding,
  validateReleaseEnv,
};
