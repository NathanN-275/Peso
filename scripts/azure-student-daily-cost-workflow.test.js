const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(
  path.join(__dirname, '../.github/workflows/azure-student-daily-cost.yml'),
  'utf8',
);

test('Daily cost workflow resolves Azure OIDC identifiers from vars or secrets', () => {
  assert.match(source, /client-id: \$\{\{ vars\.AZURE_CLIENT_ID \|\| secrets\.AZURE_CLIENT_ID \}\}/);
  assert.match(source, /tenant-id: \$\{\{ vars\.AZURE_TENANT_ID \|\| secrets\.AZURE_TENANT_ID \}\}/);
  assert.match(source, /subscription-id: \$\{\{ vars\.AZURE_SUBSCRIPTION_ID \|\| secrets\.AZURE_SUBSCRIPTION_ID \}\}/);
});
