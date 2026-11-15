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
  assert.doesNotMatch(workflow, /ignore-vuln/);
  assert.match(read('Dockerfile'), /USER 10001:10001/);
  const ignore = read('.dockerignore');
  assert.match(ignore, /^\*\*$/m);
  assert.match(ignore, /^backend\/\*\*$/m);
  assert.match(ignore, /^!backend\/app\/\*\*$/m);
  assert.doesNotMatch(ignore, /^!(?:\.env|backend\/test_videos)/m);
  assert.equal(fs.existsSync(path.join(root, '.trivyignore')), false);
});

test('PR and deployment scans explicitly select the same Trivy release and blocking policy', () => {
  const scans = [
    '.github/workflows/security.yml',
    '.github/workflows/azure-backend-deploy.yml',
    '.github/workflows/azure-staging.yml',
  ].map((name) => {
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


test('required database security waits for every private media SQL suite', () => {
  const workflow = read('.github/workflows/security.yml');
  const reservation = workflow.split('\n  reservation-database-security:\n')[1].split('\n  private-media-database-security:\n')[0];
  assert.match(reservation, /needs: private-media-database-security/);
  assert.match(reservation, /if: \$\{\{ always\(\) \}\}/);
  assert.match(reservation, /MEDIA_DATABASE_RESULT: \$\{\{ needs\.private-media-database-security\.result \}\}/);
  assert.match(reservation, /run: test "\$MEDIA_DATABASE_RESULT" = success/);
  assert.doesNotMatch(reservation, /continue-on-error|\|\| true/);
  const media = workflow.split('\n  private-media-database-security:\n')[1].split('\n  container-security:\n')[0];
  for (const suite of ['test_us_signup_hook_postgres.py', 'test_private_media_sessions_postgres.py', 'test_private_media_grants_postgres.py', 'test_private_media_session_replacement_postgres.py', 'test_profile_owner_postgres.py', 'test_source_write_attempts_postgres.py', 'test_generated_media_writes_postgres.py', 'test_analyzed_export_writes_postgres.py', 'test_avatar_writes_postgres.py', 'test_avatar_reads_postgres.py', 'test_browser_media_cookie_inventory_postgres.py', 'test_archive_writes_postgres.py', 'test_video_revocation_postgres.py', 'test_archive_publication_postgres.py', 'test_analysis_publication_postgres.py', 'test_saved_deletion_postgres.py']) {
    assert.match(media, new RegExp(`suite: ${suite.replaceAll('.', '\\.')}\\s`));
  }
  assert.match(media, /fail-fast: false/);
  assert.match(media, /--health-cmd "pg_isready -h 127\.0\.0\.1"/);
  assert.match(media, /env "\$DATABASE_ENV=.*127\.0\.0\.1:5432\/\$DATABASE_NAME" python - <<'PYTHON'/);
  assert.match(media, /suite\.countTestCases\(\) == 0/);
  assert.match(media, /result\.wasSuccessful\(\) and not result\.skipped else 1/);
  for (const [suite, database, environment] of [
    ['us_signup_hook', 'peso_us_signup_hook_test', 'US_SIGNUP_HOOK_TEST_DATABASE_URL'],
    ['private_media_sessions', 'peso_private_media_session_test', 'PRIVATE_MEDIA_SESSION_TEST_DATABASE_URL'],
    ['private_media_grants', 'peso_media_grants_test', 'PRIVATE_MEDIA_GRANT_TEST_DATABASE_URL'],
    ['private_media_session_replacement', 'peso_media_grants_test', 'PRIVATE_MEDIA_GRANT_TEST_DATABASE_URL'],
    ['profile_owner', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['source_write_attempts', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['generated_media_writes', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['analyzed_export_writes', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['avatar_writes', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['browser_media_cookie_inventory', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['archive_writes', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['video_revocation', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['archive_publication', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['analysis_publication', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
    ['saved_deletion', 'peso_revocation_test', 'VIDEO_REVOCATION_TEST_DATABASE_URL'],
  ]) {
    assert.ok(media.includes(`suite: test_${suite}_postgres.py\n            database: ${database}\n            database_env: ${environment}`), `${suite}: isolated database and environment mapping`);
  }
  assert.doesNotMatch(media, /continue-on-error|if:|\|\| true/);
});
