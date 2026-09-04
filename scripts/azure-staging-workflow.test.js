const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const workflowSource = fs.readFileSync(
  path.join(__dirname, '../.github/workflows/azure-staging.yml'),
  'utf8'
);

test('Azure staging workflow verifies main before publishing the root image', () => {
  assert.match(workflowSource, /push:[\s\S]*branches:[\s\S]*- main/);
  assert.match(workflowSource, /workflow_dispatch:/);
  assert.match(workflowSource, /npm run test:policy/);
  assert.match(workflowSource, /npm run typecheck/);
  assert.match(workflowSource, /node-version: "22"/);
  assert.match(workflowSource, /sudo apt-get install --yes ffmpeg/);
  assert.match(workflowSource, /python -m unittest discover -s tests/);
  assert.match(workflowSource, /az bicep build --file infra\/azure\/staging\/main\.bicep/);
  assert.match(workflowSource, /file: \.\/Dockerfile/);
  assert.match(workflowSource, /IMAGE_REPOSITORY: ghcr\.io\/nathann-275\/peso-backend/);
});

test('published backend image receives full-SHA and main tags', () => {
  assert.match(workflowSource, /packages: write/);
  assert.match(workflowSource, /docker\/build-push-action@[a-f0-9]{40} # v6/);
  assert.match(workflowSource, /push: true/);
  assert.match(workflowSource, /:sha-\$\{\{ github\.sha \}\}/);
  assert.match(workflowSource, /:\s*main|\}\}:main/);
  assert.match(workflowSource, /org\.opencontainers\.image\.source=https:\/\/github\.com\/\$\{\{ github\.repository \}\}/);
  assert.match(workflowSource, /docker buildx imagetools inspect/);
  assert.match(workflowSource, /digest: \$\{\{ steps\.registry\.outputs\.digest \}\}/);
  assert.match(workflowSource, /docker logout ghcr\.io/);
  assert.match(workflowSource, /PUBLIC_DIGEST/);
});

test('Azure deployment uses OIDC and remains fail-closed behind the staging gate', () => {
  assert.match(workflowSource, /vars\.AZURE_STAGING_DEPLOY_ENABLED == 'true'/);
  assert.match(workflowSource, /id-token: write/);
  assert.match(workflowSource, /uses: azure\/login@[a-f0-9]{40} # v2/);
  assert.match(workflowSource, /client-id: \$\{\{ vars\.AZURE_STAGING_CLIENT_ID \}\}/);
  assert.match(workflowSource, /tenant-id: \$\{\{ vars\.AZURE_TENANT_ID \}\}/);
  assert.match(workflowSource, /subscription-id: \$\{\{ vars\.AZURE_SUBSCRIPTION_ID \}\}/);
  assert.doesNotMatch(workflowSource, /AZURE_CLIENT_SECRET|client-secret/i);
});

test('deploy job updates only immutable image fields on the two staging resources', () => {
  assert.match(workflowSource, /DEPLOY_IMAGE="\$\{IMAGE_REPOSITORY\}@\$\{IMAGE_DIGEST\}"/);
  assert.match(workflowSource, /Microsoft\.App\/containerApps\/\$\{AZURE_API_NAME\}/);
  assert.match(workflowSource, /Microsoft\.App\/jobs\/\$\{AZURE_WORKER_JOB_NAME\}/);
  assert.equal(
    (workflowSource.match(/--set "properties\.template\.containers\[0\]\.image=\$\{DEPLOY_IMAGE\}"/g) || []).length,
    2
  );
  assert.doesNotMatch(workflowSource, /secret set|listsecrets|role assignment|group create/i);
});
