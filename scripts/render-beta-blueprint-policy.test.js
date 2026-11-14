const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const beta = fs.readFileSync(path.join(root, 'render-beta.yaml'), 'utf8');
const publicBeta = fs.readFileSync(path.join(root, 'render-public-beta.yaml'), 'utf8');
const production = fs.readFileSync(path.join(root, 'render.yaml'), 'utf8');
const netlify = fs.readFileSync(path.join(root, 'netlify.toml'), 'utf8');
const workflow = fs.readFileSync(path.join(root, '.github/workflows/render-beta-validate.yml'), 'utf8');

function serviceBlock(name, nextName) {
  const start = beta.indexOf(`    name: ${name}`);
  const end = nextName ? beta.indexOf(`    name: ${nextName}`, start) : beta.length;
  assert.ok(start >= 0 && end > start, `missing ${name}`);
  return beta.slice(start, end);
}

test('Render beta is isolated from the unchanged production Blueprint', () => {
  assert.match(production, /name: Peso-backend/);
  assert.match(production, /name: peso-analysis-worker/);
  assert.doesNotMatch(production, /peso-beta-/);
  assert.match(beta, /name: peso-beta-api/);
  assert.match(beta, /name: peso-beta-analysis-worker/);
  assert.doesNotMatch(beta, /name: Peso-backend|name: peso-analysis-worker\n/);
});

test('fresh Render pairs have matched compute and isolated Supabase projects', () => {
  const preferences = require('../config/public-beta-owner-preferences.json');
  const staging = fs.readFileSync(path.join(root, 'render-public-beta-staging.yaml'), 'utf8');
  for (const [blueprint, suffix, workerName, environment, projectRef, otherProjectRef, cors] of [
    [publicBeta, '', 'analysis-worker', 'production', preferences.supabase_project_ref, 'iseqgaewjpjcxrndibep', /sync: false/],
    [staging, '-staging', 'worker', 'student', 'iseqgaewjpjcxrndibep', preferences.supabase_project_ref, /value: https:\/\/main--peso-webapp\.netlify\.app/],
  ]) {
    const [api, worker, ...extra] = blueprint.split(/  - type: /).slice(1);
    assert.equal(extra.length, 0);
    assert.ok(api.includes(`name: peso-public-beta${suffix}-api\n`));
    assert.ok(worker.includes(`name: peso-public-beta${suffix}-${workerName}\n`));
    assert.match(api, /plan: 0\.5c-512mb/);
    assert.match(api, /healthCheckPath: \/health\/ready/);
    assert.match(worker, /plan: 1c-2g/);
    assert.match(worker, /dockerCommand: python -m app\.jobs\.analysis_worker/);
    for (const block of [api, worker]) {
      assert.match(block, /autoDeployTrigger: "off"/);
      assert.match(block, /dockerfilePath: \.\/Dockerfile\.mvp/);
      assert.match(block, /UPLOAD_STORAGE_PROVIDER\n\s+value: supabase/);
      assert.ok(block.includes(`PESO_DEPLOYMENT_ENVIRONMENT\n        value: ${environment}\n`));
      assert.ok(block.includes(`value: https://${projectRef}.supabase.co\n`));
      assert.ok(block.includes(`INTAKE_STOP_PROJECTED_MONTHLY_USD\n        value: "${preferences.stop_new_uploads_at_projected_monthly_usd}"`));
      assert.match(block, /SAVED_VIDEO_STORAGE_TTL_HOURS\n\s+value: "72"/);
      if (environment === 'student') {
        assert.match(block, /PRIVATE_MEDIA_ENABLED\n\s+value: "false"\n/);
        assert.doesNotMatch(block, /PRIVATE_MEDIA_PUBLIC_ORIGIN|PRIVATE_MEDIA_BROWSER_ORIGINS/);
        assert.doesNotMatch(block, /SUPABASE_JWT_SECRET/);
      } else {
        assert.match(block, /PRIVATE_MEDIA_ENABLED\n\s+sync: false/);
        assert.match(block, /SUPABASE_JWT_SECRET\n\s+sync: false/);
        for (const key of ['PRIVATE_MEDIA_PUBLIC_ORIGIN', 'PRIVATE_MEDIA_BROWSER_ORIGINS']) {
          assert.match(block, new RegExp(`${key}\n\\s+sync: false`));
        }
      }
      assert.match(block, new RegExp(`BACKEND_CORS_ORIGINS\n\\s+${cors.source}\n`));
      for (const key of ['BUDGET_SHUTDOWN_TOKEN', 'SUPABASE_SERVICE_ROLE_KEY', 'CLEANUP_JOB_TOKEN']) {
        assert.match(block, new RegExp(`${key}\n\\s+sync: false`));
      }
      assert.ok(!block.includes(otherProjectRef));
      assert.doesNotMatch(block, /US_IP_BETA_ENABLED|TRUSTED_PROXY_CIDRS|main\.usepeso\.com|name: peso-beta-/);
    }
  }
});

test('both beta services use the root Dockerfile and manual deploys', () => {
  for (const block of [
    serviceBlock('peso-beta-api', 'peso-beta-analysis-worker'),
    serviceBlock('peso-beta-analysis-worker'),
  ]) {
    assert.match(block, /runtime: docker/);
    assert.match(block, /dockerfilePath: \.\/Dockerfile/);
    assert.match(block, /dockerContext: \./);
    assert.match(block, /autoDeployTrigger: "off"/);
    assert.match(block, /PESO_DEPLOYMENT_ENVIRONMENT\n\s+value: student/);
    assert.match(block, /BACKEND_ENV\n\s+value: production/);
    assert.match(block, /BACKEND_CORS_ORIGINS\n\s+value: https:\/\/main\.usepeso\.com\n/);
    assert.doesNotMatch(block, /main--peso-webapp|value: https:\/\/main\.usepeso\.com[,/*]/);
    assert.match(block, /UPLOAD_RESERVATIONS_ENABLED\n\s+value: "true"/);
    assert.match(block, /UPLOAD_STORAGE_PROVIDER\n\s+value: supabase/);
    assert.doesNotMatch(block, /AZURE_BLOB|BUDGET_SHUTDOWN/);
    for (const key of [
      'SUPABASE_URL',
      'SUPABASE_SERVICE_ROLE_KEY',
      'SUPABASE_JWT_SECRET',
      'CLEANUP_JOB_TOKEN',
    ]) {
      assert.match(block, new RegExp(`${key}\\n\\s+sync: false`));
    }
  }
});

test('beta API readiness and Starter worker sizing are explicit', () => {
  assert.match(serviceBlock('peso-beta-api', 'peso-beta-analysis-worker'), /healthCheckPath: \/health\/ready/);
  assert.match(serviceBlock('peso-beta-analysis-worker'), /plan: starter/);
  assert.match(serviceBlock('peso-beta-analysis-worker'), /dockerCommand: python -m app\.jobs\.analysis_worker/);
});

test('only the historical private main deploy receives the bound Render beta environment', () => {
  const { APP_SITE_ID, buildEnvironment } = require('./netlify-build');
  const stagingBinding = require('../config/render-beta-release-binding.json');
  assert.deepEqual(buildEnvironment({ SITE_ID: APP_SITE_ID, CONTEXT: 'branch-deploy', BRANCH: 'main' }), {
    SITE_ID: APP_SITE_ID, CONTEXT: 'branch-deploy', BRANCH: 'main', PESO_RELEASE_ENV: 'render-beta',
    EXPO_PUBLIC_SUPABASE_URL: 'https://iseqgaewjpjcxrndibep.supabase.co',
    EXPO_PUBLIC_PRODUCTION_BACKEND_URL: stagingBinding.api_url,
    EXPO_PUBLIC_AUTH_CHALLENGE_URL: 'https://main--peso-webapp.netlify.app/auth/turnstile/',
    EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'false',
  });
  assert.doesNotMatch(netlify, /\[context\.[^\]]*environment\]/);
  assert.doesNotMatch(netlify, /EXPO_PUBLIC_|PESO_RELEASE_ENV/);
});

test('beta validation runs Blueprint, policy, runtime, and peso-staging migration gates without deploying', () => {
  assert.match(workflow, /render blueprints validate render-beta\.yaml --workspace "\$RENDER_WORKSPACE_ID"/);
  assert.match(workflow, /render blueprints validate render-public-beta-staging\.yaml --workspace "\$RENDER_WORKSPACE_ID"/);
  assert.match(workflow, /RENDER_API_KEY: \$\{\{ secrets\.RENDER_API_KEY \}\}/);
  assert.match(workflow, /npm run test:policy/);
  assert.match(workflow, /npm run typecheck/);
  assert.match(workflow, /python -m unittest discover -s tests/);
  assert.match(workflow, /docker build --pull/);
  assert.match(workflow, /verify_container_runtime\.sh/);
  assert.match(workflow, /node scripts\/student-environment\.js --database-only/);
  assert.match(workflow, /supabase migration list --db-url "\$SUPABASE_DB_URL"/);
  assert.match(workflow, /supabase db push --db-url "\$SUPABASE_DB_URL" --dry-run/);
  assert.doesNotMatch(workflow, /render deploys create|render blueprint sync|supabase db push --db-url "\$SUPABASE_DB_URL"\s*$/m);
});

test('manual staging preview pins reviewed source without accepting arbitrary branches or mutable refs', () => {
  assert.match(workflow, /release_sha:\n\s+description:[^\n]+\n\s+required: true\n\s+type: string/);
  assert.match(workflow, /refs\/heads\/main\|refs\/heads\/feat\/combined-public-beta/);
  assert.match(workflow, /git merge-base --is-ancestor "\$EXPECTED_SOURCE_COMMIT" "\$GITHUB_SHA"/);
  assert.match(workflow, /\^\[a-f0-9\]\{40\}\$/);
  assert.match(workflow, /test "\$\(git rev-parse HEAD\)" = "\$EXPECTED_SOURCE_COMMIT"/);
  assert.match(workflow, /ref: \$\{\{ inputs\.release_sha \}\}/);
  assert.match(workflow, /needs: validate[\s\S]*environment: student/);
  assert.match(workflow, /source_commit=%s\\nworkflow_commit=%s\\n/);
  assert.match(workflow, /sha256sum supabase\/migrations\/\*\.sql/);
  assert.doesNotMatch(workflow, /pull_request_target|secrets: inherit/);
});
