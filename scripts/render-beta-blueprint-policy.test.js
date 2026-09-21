const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const beta = fs.readFileSync(path.join(root, 'render-beta.yaml'), 'utf8');
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
    assert.match(block, /BACKEND_CORS_ORIGINS\n\s+value: https:\/\/main--peso-webapp\.netlify\.app/);
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

test('private main Netlify branch is bound only to the pending Render beta release', () => {
  assert.match(netlify, /\[context\.main\.environment\][\s\S]*PESO_RELEASE_ENV = "render-beta"/);
  assert.match(netlify, /\[context\.main\.environment\][\s\S]*EXPO_PUBLIC_SUPABASE_URL = "https:\/\/iseqgaewjpjcxrndibep\.supabase\.co"/);
  assert.match(netlify, /\[context\.main\.environment\][\s\S]*EXPO_PUBLIC_PRODUCTION_BACKEND_URL = "https:\/\/peso-beta-api\.onrender\.com"/);
  assert.doesNotMatch(netlify, /\[context\.production\.environment\]/);
});

test('beta validation runs Blueprint, policy, runtime, and peso-staging migration gates without deploying', () => {
  assert.match(workflow, /render blueprints validate render-beta\.yaml --workspace "\$RENDER_WORKSPACE_ID"/);
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
