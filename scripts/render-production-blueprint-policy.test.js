const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const blueprint = fs.readFileSync(path.resolve(__dirname, '../render.yaml'), 'utf8');

function serviceBlock(name, nextName) {
  const start = blueprint.indexOf(`    name: ${name}`);
  const end = nextName ? blueprint.indexOf(`    name: ${nextName}`, start) : blueprint.length;
  assert.notEqual(start, -1, `missing ${name} service`);
  assert.notEqual(end, -1, `missing end of ${name} service`);
  return blueprint.slice(start, end);
}

test('production Render services use isolated production Supabase reservations', () => {
  const api = serviceBlock('Peso-backend', 'peso-analysis-worker');
  const worker = serviceBlock('peso-analysis-worker');

  for (const block of [api, worker]) {
    assert.match(block, /PESO_DEPLOYMENT_ENVIRONMENT\n\s+value: production/);
    assert.match(block, /UPLOAD_RESERVATIONS_ENABLED\n\s+value: "true"/);
    assert.match(block, /UPLOAD_STORAGE_PROVIDER\n\s+value: supabase/);
    assert.match(block, /SUPABASE_URL\n\s+sync: false/);
    assert.match(block, /SUPABASE_SERVICE_ROLE_KEY\n\s+sync: false/);
    assert.doesNotMatch(block, /AZURE_BLOB_(?:ACCOUNT_URL|SOURCE_CONTAINER)/);
  }
});
