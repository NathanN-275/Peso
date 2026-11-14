const assert = require('node:assert/strict');
const test = require('node:test');
const { APP_SITE_ID, buildScript, buildEnvironment } = require('./netlify-build');

test('an explicitly bound new project builds both surfaces in production and previews', () => {
  const site = '11111111-2222-3333-4444-555555555555';
  const binding = { schema_version: 1, site_id: site };
  for (const CONTEXT of ['production', 'deploy-preview', 'branch-deploy']) {
    assert.equal(buildScript({ SITE_ID: site, CONTEXT }, binding), 'web:build:release');
    assert.equal(buildScript({ SITE_ID: 'other', CONTEXT }, binding), 'web:build:marketing');
  }
});

test('combined dispatch cannot select a weaker release environment', () => {
  const binding = { schema_version: 1, site_id: '11111111-2222-3333-4444-555555555555' };
  for (const CONTEXT of ['production', 'deploy-preview', 'branch-deploy']) {
    const env = { SITE_ID: binding.site_id, CONTEXT, PESO_RELEASE_ENV: 'staging' };
    assert.equal(buildEnvironment(env, binding).PESO_RELEASE_ENV, 'public-beta');
    assert.equal(env.PESO_RELEASE_ENV, 'staging');
  }
  const historical = { SITE_ID: APP_SITE_ID, PESO_RELEASE_ENV: 'render-beta' };
  assert.equal(buildEnvironment(historical, binding), historical);
});

test('missing, malformed and historical app bindings cannot enable combined production', () => {
  for (const site_id of [null, '', 'not-a-site-id', APP_SITE_ID]) {
    assert.equal(buildScript({ SITE_ID: site_id, CONTEXT: 'production' }, {
      schema_version: 1, site_id,
    }), 'web:build:marketing');
  }
  assert.equal(buildScript({ SITE_ID: '11111111-2222-3333-4444-555555555555' }, {
    schema_version: 2, site_id: '11111111-2222-3333-4444-555555555555',
  }), 'web:build:marketing');
});

test('only the stable main branch deploy builds the private beta', () => {
  assert.equal(buildScript({ SITE_ID: APP_SITE_ID, CONTEXT: 'branch-deploy', BRANCH: 'main' }), 'web:build:release');
  for (const env of [
    {},
    { CONTEXT: 'production', BRANCH: 'production' },
    { CONTEXT: 'production', BRANCH: 'main' },
    { CONTEXT: 'deploy-preview', BRANCH: 'main' },
    { CONTEXT: 'branch-deploy', BRANCH: 'feature' },
  ]) assert.equal(buildScript(env), 'web:build:marketing');
});

test('every non-app project and preview fails closed to marketing', () => {
  for (const SITE_ID of [undefined, '', 'marketing-project', APP_SITE_ID]) {
    for (const CONTEXT of ['production', 'deploy-preview', 'branch-deploy', undefined]) {
      for (const BRANCH of ['main', 'production', 'feature', undefined]) {
        const expected = SITE_ID === APP_SITE_ID && CONTEXT === 'branch-deploy' && BRANCH === 'main'
          ? 'web:build:release' : 'web:build:marketing';
        assert.equal(buildScript({ SITE_ID, CONTEXT, BRANCH }), expected);
      }
    }
  }
});


test('shared Netlify configuration contains no project-specific branch environment', () => {
  const config = require('node:fs').readFileSync(require('node:path').join(__dirname, '../netlify.toml'), 'utf8');
  assert.doesNotMatch(config, /\[context\.[^\]]*environment\]/);
  assert.doesNotMatch(config, /EXPO_PUBLIC_|PESO_RELEASE_ENV/);
});

test('only the historical stable main deploy receives the exact staging environment', () => {
  const input = { SITE_ID: APP_SITE_ID, CONTEXT: 'branch-deploy', BRANCH: 'main',
    PESO_RELEASE_ENV: 'production', EXPO_PUBLIC_SUPABASE_URL: 'https://wrong.invalid',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://wrong-api.invalid',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://wrong-web.invalid/auth/turnstile/',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'synthetic-project-key' };
  assert.deepEqual(buildEnvironment(input), { ...input, PESO_RELEASE_ENV: 'render-beta',
    EXPO_PUBLIC_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: '',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://main--peso-webapp.netlify.app/auth/turnstile/',
    EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'false' });
  assert.equal(input.PESO_RELEASE_ENV, 'production');
  assert.equal(input.EXPO_PUBLIC_SUPABASE_URL, 'https://wrong.invalid');
  for (const change of [
    { SITE_ID: 'other-project' }, { SITE_ID: undefined }, { CONTEXT: 'production' },
    { CONTEXT: 'deploy-preview' }, { CONTEXT: undefined }, { BRANCH: 'feature' }, { BRANCH: undefined },
  ]) {
    const other = { ...input, ...change };
    assert.equal(buildEnvironment(other), other);
  }
});

test('combined main builds preserve configured endpoints and keys in every deploy context', () => {
  const binding = { schema_version: 1, site_id: '11111111-2222-3333-4444-555555555555' };
  for (const CONTEXT of ['production', 'branch-deploy', 'deploy-preview']) {
    const input = { SITE_ID: binding.site_id, BRANCH: 'main', CONTEXT, PESO_RELEASE_ENV: 'render-beta',
      EXPO_PUBLIC_SUPABASE_URL: 'https://jfgiydtrskpqxyorvvbc.supabase.co',
      EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://candidate-api.example.com',
      EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://candidate.example.com/auth/turnstile/',
      EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'synthetic-combined-key' };
    assert.deepEqual(buildEnvironment(input, binding), { ...input, PESO_RELEASE_ENV: 'public-beta' });
    assert.equal(input.PESO_RELEASE_ENV, 'render-beta');
  }
});


test('actual dispatcher passes scoped staging settings to npm without changing other projects', (t) => {
  const fs = require('node:fs');
  const path = require('node:path');
  const { spawnSync } = require('node:child_process');
  const directory = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'peso-netlify-dispatch-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  fs.writeFileSync(path.join(directory, 'npm'), `#!${process.execPath}
const keys = ['PESO_RELEASE_ENV', 'EXPO_PUBLIC_SUPABASE_URL', 'EXPO_PUBLIC_PRODUCTION_BACKEND_URL',
  'EXPO_PUBLIC_AUTH_CHALLENGE_URL', 'EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY'];
process.stdout.write(JSON.stringify({ args: process.argv.slice(2),
  env: Object.fromEntries(keys.map(key => [key, process.env[key]])) }));
`, { mode: 0o755 });
  const supplied = { PATH: directory, SITE_ID: APP_SITE_ID, CONTEXT: 'branch-deploy', BRANCH: 'main',
    PESO_RELEASE_ENV: 'fixture-scope', EXPO_PUBLIC_SUPABASE_URL: 'https://fixture-db.invalid',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://fixture-api.invalid',
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://fixture-web.invalid/auth/turnstile/',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'synthetic-project-key' };
  for (const SITE_ID of [APP_SITE_ID, 'unbound-project']) {
    const env = { ...supplied, SITE_ID };
    const result = spawnSync(process.execPath, [path.join(__dirname, 'netlify-build.js')], {
      cwd: directory, env, encoding: 'utf8', timeout: 5000,
    });
    assert.ifError(result.error); assert.equal(result.status, 0, result.stderr);
    const observed = JSON.parse(result.stdout);
    assert.deepEqual(observed.args, ['run', SITE_ID === APP_SITE_ID ? 'web:build:release' : 'web:build:marketing']);
    assert.deepEqual(observed.env, SITE_ID === APP_SITE_ID ? {
      PESO_RELEASE_ENV: 'render-beta', EXPO_PUBLIC_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
      EXPO_PUBLIC_PRODUCTION_BACKEND_URL: '',
      EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://main--peso-webapp.netlify.app/auth/turnstile/',
      EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'synthetic-project-key',
    } : {
      PESO_RELEASE_ENV: supplied.PESO_RELEASE_ENV, EXPO_PUBLIC_SUPABASE_URL: supplied.EXPO_PUBLIC_SUPABASE_URL,
      EXPO_PUBLIC_PRODUCTION_BACKEND_URL: supplied.EXPO_PUBLIC_PRODUCTION_BACKEND_URL,
      EXPO_PUBLIC_AUTH_CHALLENGE_URL: supplied.EXPO_PUBLIC_AUTH_CHALLENGE_URL,
      EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: supplied.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
    });
  }
});
