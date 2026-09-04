const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');

test('all GitHub Actions are pinned to immutable commit SHAs', () => {
  for (const name of fs.readdirSync(path.join(root, '.github/workflows'))) {
    if (!name.endsWith('.yml')) continue;
    for (const match of read(`.github/workflows/${name}`).matchAll(/uses:\s*([^\s#]+)/g)) {
      assert.match(match[1], /^[^@]+@[a-f0-9]{40}$/, `${name}: ${match[1]}`);
    }
  }
});

test('source uploads use reservations and no direct client storage mutation', () => {
  const client = read('lib/videoUpload.ts');
  assert.match(client, /createUploadReservation/);
  assert.match(client, /completeUploadReservation/);
  assert.doesNotMatch(client, /supabase\.storage/);
  const storage = read('backend/app/services/azure_blob_storage.py');
  assert.match(storage, /BlobSasPermissions\(create=True\)/);
  assert.doesNotMatch(storage, /BlobSasPermissions\([^)]*write=True/);
  assert.match(storage, /protocol="https"/);
  assert.match(storage, /user_delegation_key=delegation_key/);
});

test('source infrastructure disallows anonymous and shared-key access with least-scoped delegation', () => {
  const storage = read('infra/azure/modules/source-storage.bicep');
  assert.match(storage, /allowBlobPublicAccess: false/);
  assert.match(storage, /allowSharedKeyAccess: false/);
  assert.match(storage, /publicAccess: 'None'/);
  assert.match(storage, /scope: sources/);
  assert.match(storage, /scope: storage/);
  const student = read('infra/azure/student.bicep');
  assert.match(student, /param enableUploadReservations bool = false/);
  assert.match(student, /cronExpression: '\*\/5 \* \* \* \*'/);
  assert.doesNotMatch(student, /Microsoft.Authorization\/roleAssignments/);
});

test('credit alerts invoke a secret-protected persistent admission shutdown at 90 percent', () => {
  const budget = read('infra/azure/modules/budget-admission.bicep');
  for (const threshold of [50, 75, 90]) assert.match(budget, new RegExp(`threshold: ${threshold}`));
  assert.match(budget, /param studentCreditAmount int = 100/);
  assert.match(budget, /\/internal\/budget-admission\/disable/);
  assert.match(budget, /secureData/);
  assert.match(budget, /contactGroups: \[budgetActionGroup.id\]/);
  assert.match(read('backend/app/routes/budget_admission.py'), /hmac.compare_digest/);
  assert.match(read('supabase/migrations/202609030001_upload_reservations.sql'), /Upload admission is disabled/);
});

test('database tests and container scanning are mandatory CI jobs', () => {
  const workflow = read('.github/workflows/security.yml');
  assert.match(workflow, /reservation-database-security:/);
  assert.match(workflow, /test_upload_reservations_postgres.py/);
  assert.match(workflow, /container-security:/);
  assert.match(workflow, /aquasecurity\/trivy-action@[a-f0-9]{40}/);
  assert.match(workflow, /exit-code: "1"/);
  assert.match(read('Dockerfile'), /USER 10001:10001/);
  const ignore = read('.dockerignore');
  assert.match(ignore, /^\*\*$/m);
  assert.match(ignore, /^backend\/\*\*$/m);
  assert.match(ignore, /^!backend\/app\/\*\*$/m);
  assert.doesNotMatch(ignore, /^!(?:\.env|backend\/test_videos)/m);
});

test('PR and deployment scans explicitly select the same Trivy release and blocking policy', () => {
  const scans = ['.github/workflows/security.yml', '.github/workflows/azure-backend-deploy.yml'].map((name) => {
    const workflow = read(name);
    const start = workflow.indexOf('uses: aquasecurity/trivy-action@');
    assert.notEqual(start, -1, `${name}: missing container scanner`);
    const scan = workflow.slice(start).split('\n      - ')[0];
    const version = scan.match(/^\s+version: (v\d+\.\d+\.\d+)\s*$/m)?.[1];
    assert.ok(version, `${name}: explicitly pin Trivy instead of inheriting the action's release default`);
    assert.match(scan, /exit-code: "1"/);
    assert.match(scan, /severity: HIGH,CRITICAL/);
    assert.match(scan, /ignore-unfixed: false/);
    return { version, action: scan.match(/trivy-action@([a-f0-9]{40})/)[1] };
  });
  assert.deepEqual(scans[0], scans[1], 'PR and deployment gates must use the same scanner');
});
