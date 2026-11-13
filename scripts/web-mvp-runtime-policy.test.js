const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const read = name => fs.readFileSync(path.resolve(__dirname, '..', name), 'utf8');

test('MVP dependency pins match the maintained backend set with Azure SDKs removed', () => {
  const pins = name => read(name).split('\n').map(line => line.trim()).filter(line => line && !line.startsWith('#'));
  assert.deepEqual(pins('backend/requirements-mvp.txt'), pins('backend/requirements.txt').filter(line => !line.startsWith('azure-')));
  assert.ok(pins('backend/requirements-mvp.txt').every(line => /^[a-z0-9_-]+(?:\[[a-z,]+\])?==[^ ]+$/.test(line)));
});

test('MVP image retains the complete verified media build while excluding the Azure adapter', () => {
  const mvp = read('Dockerfile.mvp');
  const normalized = mvp.replace('COPY backend/requirements-mvp.txt ./requirements.txt', 'COPY backend/requirements.txt ./requirements.txt')
    .replace('ENV PESO_RUNTIME_PROFILE=web-mvp \\\n    PYTHONDONTWRITEBYTECODE=1', 'ENV PYTHONDONTWRITEBYTECODE=1');
  assert.equal(normalized, read('Dockerfile'));
  assert.match(read('Dockerfile.mvp.dockerignore'), /^\*\*$/m);
  assert.match(read('Dockerfile.mvp.dockerignore'), /^!backend\/requirements-mvp\.txt$/m);
  assert.match(read('Dockerfile.mvp.dockerignore'), /^backend\/app\/services\/azure_blob_storage\.py$/m);
});

test('both public Render services select the Azure-free MVP image and Supabase provider', () => {
  const blocks = read('render-public-beta.yaml').split(/  - type: /).slice(1);
  assert.equal(blocks.length, 2);
  for (const block of blocks) {
    assert.match(block, /dockerfilePath: \.\/Dockerfile\.mvp\n/);
    assert.match(block, /PESO_RUNTIME_PROFILE\n\s+value: web-mvp/);
    assert.match(block, /UPLOAD_STORAGE_PROVIDER\n\s+value: supabase/);
    assert.match(block, /autoDeployTrigger: "off"/);
    assert.doesNotMatch(block, /key: AZURE_|azurecontainerapps|blob\.core\.windows\.net/);
  }
});

test('required container and Render validation build the MVP artifact and verify SDK absence', () => {
  for (const name of ['security.yml', 'render-beta-validate.yml']) {
    assert.match(read('.github/workflows/' + name), /docker build --pull --file Dockerfile\.mvp --tag/);
  }
  const runtime = read('scripts/container_runtime_check.py');
  assert.match(runtime, /find_spec\('azure'\) is None/);
  assert.match(runtime, /find_spec\('app.services.azure_blob_storage'\) is None/);
});
