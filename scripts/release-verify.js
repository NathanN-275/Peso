const { spawnSync } = require('node:child_process');
const os = require('node:os');
const path = require('node:path');

const productionLikeBackendEnvironment = {
  SUPABASE_URL: 'https://example.supabase.co',
  SUPABASE_SERVICE_ROLE_KEY: 'release-test-service-role',
  SUPABASE_JWT_SECRET: 'release-test-jwt-secret',
  CLEANUP_JOB_TOKEN: 'release-test-cleanup-token',
  BACKEND_ALLOW_UNAUTHENTICATED_DEV_CLEANUP: 'false',
  PYTHONPYCACHEPREFIX: path.join(os.tmpdir(), 'peso-release-pycache'),
};

const releaseChecks = [
  {
    name: 'Release configuration',
    command: process.execPath,
    args: ['scripts/release-env.js'],
  },
  { name: 'App typecheck', command: 'npm', args: ['run', 'typecheck'] },
  { name: 'Policy tests', command: 'npm', args: ['run', 'test:policy'] },
  {
    name: 'Dashboard typecheck',
    command: 'npm',
    args: ['run', 'dashboard:typecheck'],
  },
  {
    name: 'Dashboard tests',
    command: 'npm',
    args: ['run', 'dashboard:test'],
  },
  {
    name: 'Dashboard production build',
    command: 'npm',
    args: ['run', 'dashboard:build'],
  },
  {
    name: 'Web production export',
    command: 'npm',
    args: ['run', 'web:build'],
  },
  {
    name: 'Web bundle budget',
    command: 'npm',
    args: ['run', 'web:budget'],
  },
  {
    name: 'Staging web authentication flows',
    command: 'npm',
    args: ['run', 'test:web:e2e'],
  },
  {
    name: 'Backend test suite',
    command: '.venv/bin/python',
    args: ['-m', 'pytest', 'tests'],
    cwd: 'backend',
    env: productionLikeBackendEnvironment,
  },
  {
    name: 'Migration and RLS audit',
    command: 'python3',
    args: ['scripts/supabase_security_audit.py'],
  },
  {
    name: 'Node dependency audit',
    command: 'npm',
    args: ['run', 'audit:ci'],
  },
  {
    name: 'Python dependency audit',
    command: 'backend/.venv/bin/python',
    args: [
      '-m',
      'pip_audit',
      '-r',
      'backend/requirements.txt',
      '--ignore-vuln',
      'PYSEC-2026-1805',
    ],
  },
  {
    name: 'Secret scan',
    command: 'gitleaks',
    args: ['detect', '--source', '.', '--no-banner', '--redact'],
  },
  {
    name: 'Git whitespace check',
    command: 'git',
    args: ['diff', '--check'],
  },
];

function runCheck(check) {
  const result = spawnSync(check.command, check.args, {
    cwd: check.cwd || process.cwd(),
    env: { ...process.env, ...(check.env || {}) },
    stdio: 'inherit',
  });

  if (result.error) {
    console.error(`[release:verify] ${check.name} could not start: ${result.error.message}`);
    return 1;
  }

  return result.status ?? 1;
}

function runReleaseChecks(checks = releaseChecks, runner = runCheck) {
  for (const check of checks) {
    console.log(`\n[release:verify] ${check.name}`);
    const status = runner(check);
    if (status !== 0) {
      console.error(`[release:verify] FAILED: ${check.name}`);
      return status;
    }
  }

  console.log('\n[release:verify] All release checks passed.');
  return 0;
}

if (require.main === module) {
  process.exitCode = runReleaseChecks();
}

module.exports = { releaseChecks, runReleaseChecks };
