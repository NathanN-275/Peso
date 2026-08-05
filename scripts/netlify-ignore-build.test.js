const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const {
  isNonWebPath,
  listChangedFiles,
  netlifyIgnoreExitCode,
  shouldIgnoreBuild,
} = require('./netlify-ignore-build');

test('Netlify skips changes confined to known non-web areas', () => {
  const changedFiles = [
    'backend/app/main.py',
    'dashboard/src/App.tsx',
    'docs/adr/0008-example.md',
    'supabase/migrations/20260805000000_example.sql',
    '.github/workflows/security.yml',
    'README.md',
    'CONTEXT.md',
  ];

  assert.equal(changedFiles.every(isNonWebPath), true);
  assert.equal(shouldIgnoreBuild(changedFiles), true);
  assert.equal(netlifyIgnoreExitCode(changedFiles), 0);
});

test('Netlify builds for web, shared application, asset, and configuration changes', () => {
  for (const filePath of [
    'web/src/pages/index.astro',
    'src/web/web-app.tsx',
    'assets/demo/peso-pose-overlay.mp4',
    'package.json',
    'netlify.toml',
    '.env.example',
  ]) {
    assert.equal(isNonWebPath(filePath), false, filePath);
    assert.equal(shouldIgnoreBuild([filePath]), false, filePath);
    assert.equal(netlifyIgnoreExitCode([filePath]), 1, filePath);
  }
});

test('Netlify builds mixed change sets when any file can affect the web output', () => {
  assert.equal(
    shouldIgnoreBuild(['docs/security.md', 'web/src/styles/global.css']),
    false,
  );
});

test('Netlify builds empty or unknown change sets as a fail-open default', () => {
  assert.equal(shouldIgnoreBuild([]), false);
  assert.equal(netlifyIgnoreExitCode([]), 1);
});

test('changed-file discovery uses null-delimited paths and disables rename collapsing', () => {
  let invocation;
  const runGit = (...args) => {
    invocation = args;
    return 'docs/usage notes.md\0web/src/pages/index.astro\0';
  };

  const changedFiles = listChangedFiles(
    { CACHED_COMMIT_REF: 'cached-sha', COMMIT_REF: 'current-sha' },
    runGit,
  );

  assert.deepEqual(changedFiles, [
    'docs/usage notes.md',
    'web/src/pages/index.astro',
  ]);
  assert.deepEqual(invocation, [
    'git',
    [
      'diff',
      '--name-only',
      '--no-renames',
      '--diff-filter=ACDMRTUXB',
      '-z',
      'cached-sha',
      'current-sha',
      '--',
    ],
    { encoding: 'utf8' },
  ]);
});

test('changed-file discovery rejects missing Netlify commit metadata', () => {
  assert.throws(
    () => listChangedFiles({}, () => ''),
    /commit references are unavailable/,
  );
});

test('script continues the build when Netlify comparison metadata is unavailable', () => {
  const result = spawnSync(
    process.execPath,
    [require.resolve('./netlify-ignore-build')],
    { encoding: 'utf8', env: {} },
  );

  assert.equal(result.status, 1);
  assert.match(
    result.stderr,
    /Continuing Netlify build because the change set could not be resolved/,
  );
});
