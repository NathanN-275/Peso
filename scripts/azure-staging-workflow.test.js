const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../.github/workflows/azure-staging.yml'), 'utf8');

test('Student publication verifies main and builds without publishing', () => {
  assert.match(source, /github.ref == 'refs\/heads\/main'/);
  assert.match(source, /npm run audit:ci/);
  assert.match(source, /npm run test:policy/);
  assert.match(source, /npm run typecheck/);
  assert.match(source, /python -m unittest discover -s tests/);
  assert.match(source, /push: false/);
  assert.match(source, /pull: true/);
  assert.match(source, /load: true/);
});

test('Only the exact locally tested and scanned image is published', () => {
  const runtime = source.indexOf('run: ./scripts/verify_container_runtime.sh');
  const scan = source.indexOf('uses: aquasecurity/trivy-action@');
  const drift = source.indexOf('Refuse candidate tag drift after verification');
  const publish = source.indexOf('docker push "${IMAGE_TAG}"');
  const evidence = source.indexOf('release-evidence/image-security.json');
  assert.ok(runtime > 0 && scan > runtime && drift > scan && publish > drift && evidence > publish);
  assert.match(source, /severity: HIGH,CRITICAL/);
  assert.match(source, /exit-code: "1"/);
  assert.match(source, /ignore-unfixed: false/);
  assert.match(source, /output: trivy-results\.json/);
  assert.match(source, /offline_uid_10001_runtime_check: "passed"/);
  assert.match(source, /finding_count:/);
  assert.match(source, /docker push "\$\{IMAGE_TAG\}" 2>&1 \| tee docker-push\.txt/);
  assert.match(source, /REGISTRY_DIGEST=.*docker-push\.txt/);
  assert.match(source, /IMMUTABLE_REFERENCE="\$\{IMAGE_REPOSITORY\}@\$\{REGISTRY_DIGEST\}"/);
  assert.match(source, /docker pull "\$\{IMMUTABLE_REFERENCE\}"/);
  assert.match(source, /docker image inspect[\s\S]*"\$\{IMMUTABLE_REFERENCE\}"[\s\S]*"\$\{EXPECTED_IMAGE_ID\}"/);
  assert.match(source, /IMAGE_DIGEST: \$\{\{ steps.registry.outputs.digest \}\}/);
  assert.doesNotMatch(source, /push: true|:main\s|docker logout|PUBLIC_DIGEST|imagetools inspect/);
});

test('Retired West US deployment cannot run when main changes', () => {
  assert.doesNotMatch(source, /AZURE_STAGING_DEPLOY_ENABLED|rg-peso-staging-westus2|az resource update|azure\/login|id-token: write/);
});
