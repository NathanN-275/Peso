const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

const bootstrapBicep = read('infra/azure/bootstrap.bicep');
const studentBicep = read('infra/azure/student.bicep');
const studentBootstrapBicep = read('infra/azure/modules/student-bootstrap.bicep');
const deploymentWorkflow = read('.github/workflows/azure-backend-deploy.yml');
const workerControlWorkflow = read('.github/workflows/azure-worker-control.yml');
const costWorkflow = read('.github/workflows/azure-student-daily-cost.yml');
const costScript = read('scripts/check_azure_student_cost.sh');
const scalerMigration = read('supabase/migrations/202608300001_azure_analysis_queue_scaler.sql');

test('Azure bootstrap creates only the fixed Central US student resource group', () => {
  assert.match(bootstrapBicep, /param location string = 'centralus'/);
  assert.match(bootstrapBicep, /var resourceGroupName = 'peso-student-centralus-rg'/);
  assert.match(bootstrapBicep, /environment: 'student'/);
  assert.match(bootstrapBicep, /production: 'false'/);
  assert.doesNotMatch(bootstrapBicep, /stagingResourceGroup|productionResourceGroup|westus3/);
});

test('Student compute is Consumption-only, scale-to-zero, and strictly bounded', () => {
  assert.match(studentBicep, /param location string = 'centralus'/);
  assert.match(studentBicep, /name: 'peso-student-centralus-cae'/);
  assert.doesNotMatch(studentBicep, /workloadProfiles/);
  assert.match(studentBicep, /name: 'peso-student-api'[\s\S]*external: true/);
  assert.match(studentBicep, /name: 'BACKEND_CORS_ORIGINS'[\s\S]*value: netlifyTestOrigin/);
  assert.match(studentBicep, /minReplicas: 0[\s\S]*maxReplicas: 1/);
  assert.match(studentBicep, /triggerType: 'Event'/);
  assert.match(studentBicep, /replicaTimeout: 900/);
  assert.match(studentBicep, /@allowed\(\[1, 2\]\)[\s\S]*param maxAnalysisExecutions int = 1/);
  assert.match(studentBicep, /minExecutions: 0[\s\S]*maxExecutions: maxAnalysisExecutions/);
  assert.match(studentBicep, /parallelism: 1/);
  assert.match(studentBicep, /cpu: json\('0\.25'\)[\s\S]*memory: '0\.5Gi'/);
  assert.equal((studentBicep.match(/cpu: json\('0\.25'\)/g) ?? []).length, 3);
  assert.equal((studentBicep.match(/memory: '0\.5Gi'/g) ?? []).length, 3);
  assert.match(studentBicep, /'--once'/);
  assert.match(studentBicep, /SELECT azure_scaler\.analysis_queue_depth\(\)/);
  assert.match(studentBicep, /dailyQuotaGb: json\('0\.25'\)/);
  assert.match(studentBicep, /retentionInDays: 30/);
});

test('Runtime and deployment identities use Key Vault and resource-group-scoped OIDC', () => {
  assert.match(studentBootstrapBicep, /subject: 'repo:\$\{githubRepository\}:environment:student'/);
  assert.match(studentBootstrapBicep, /resource deploymentContributor/);
  assert.match(studentBootstrapBicep, /resource deploymentSecretsAccess/);
  assert.match(studentBootstrapBicep, /resource runtimeSecretsAccess/);
  assert.doesNotMatch(studentBicep, /ghcr-token|ghcrUsername|registries:/);
  assert.doesNotMatch(deploymentWorkflow, /GHCR_READ_TOKEN|GHCR_TOKEN|TRIVY_PASSWORD|docker login/);
  assert.match(studentBicep, /keyVaultUrl: '\$\{keyVault\.properties\.vaultUri\}secrets\/supabase-service-role-key'/);
  assert.doesNotMatch(deploymentWorkflow, /AZURE_CREDENTIALS|client-secret|client_secret/);
});

test('Resource-group budget is $10 with $5, $8, and $10 actual-cost alerts', () => {
  assert.match(studentBootstrapBicep, /name: 'peso-student-monthly-10-usd'/);
  assert.match(studentBootstrapBicep, /amount: 10/);
  assert.match(studentBootstrapBicep, /timeGrain: 'Monthly'/);
  for (const threshold of [50, 80, 100]) {
    assert.match(studentBootstrapBicep, new RegExp(`threshold: ${threshold}`));
  }
  assert.equal((studentBootstrapBicep.match(/thresholdType: 'Actual'/g) ?? []).length, 3);
});

test('Student deployment validates before a fixed-scope what-if and never publishes the website', () => {
  assert.match(deploymentWorkflow, /needs: validate/);
  assert.match(deploymentWorkflow, /environment: student/);
  assert.match(deploymentWorkflow, /id-token: write/);
  assert.match(deploymentWorkflow, /az deployment group what-if/);
  assert.match(deploymentWorkflow, /--resource-group peso-student-centralus-rg/);
  assert.match(deploymentWorkflow, /--template-file infra\/azure\/student\.bicep/);
  assert.match(deploymentWorkflow, /supabase db push --db-url "\$SUPABASE_DB_URL" --dry-run/);
  assert.match(deploymentWorkflow, /az keyvault secret set/);
  assert.match(deploymentWorkflow, /verify_azure_backend\.sh/);
  assert.match(deploymentWorkflow, /url\.origin !== origin/);
  assert.match(deploymentWorkflow, /url\.hostname\.endsWith\('\.netlify\.app'\)/);
  assert.match(deploymentWorkflow, /origin === productionOrigin/);
  assert.match(deploymentWorkflow, /needs: preview/);
  assert.doesNotMatch(deploymentWorkflow, /netlify deploy|deploy-production|environment: production/);
  assert.doesNotMatch(deploymentWorkflow, /\bpeso-rg\b/);
  assert.doesNotMatch(deploymentWorkflow, /(?:actions|checks|contents|deployments|packages|pull-requests|security-events): write/);
});

test('Student validation installs and checks both media tools before backend tests', () => {
  const validate = deploymentWorkflow.slice(
    deploymentWorkflow.indexOf('\n  validate:'),
    deploymentWorkflow.indexOf('\n  preview:')
  );
  const mediaStep = validate.match(/      - name: Install and verify backend media tools\n(?:(?!      - ).*\n)*/)?.[0];
  assert.ok(mediaStep, 'validation must explicitly install its media dependencies');
  assert.match(mediaStep, /shell: bash/);
  assert.match(mediaStep, /run: \|\n          set -euo pipefail\n          sudo apt-get update\n          sudo apt-get install --yes ffmpeg\n          ffmpeg -version\n          ffprobe -version\n/);
  assert.doesNotMatch(mediaStep, /continue-on-error:|\bif:/);

  const media = validate.indexOf(mediaStep);
  const backendTests = validate.indexOf('      - name: Validate backend behavior');
  assert.ok(media >= 0 && backendTests > media, 'media tools must be ready before backend tests');
  assert.match(validate.slice(backendTests), /run: python -m unittest discover -s tests/);
});

test('Daily cost check records required signals and enforces $8 and $10 controls', () => {
  assert.match(costWorkflow, /cron: "17 12 \* \* \*"/);
  assert.match(costWorkflow, /environment: student/);
  assert.match(costScript, /MonthToDate/);
  assert.match(costScript, /Projected monthly spend/);
  assert.match(costScript, /Worker executions this month/);
  assert.match(costScript, /Worker failures this month/);
  assert.match(costScript, /API readiness/);
  assert.match(costScript, /Compute restart count this month/);
  assert.match(costScript, /Number\(process\.argv\[1\]\) >= 8/);
  assert.match(costScript, /Number\(process\.argv\[1\]\) >= 10/);
  assert.match(costScript, /metadata\.query=SELECT 0/);
  assert.match(costScript, /az containerapp ingress disable/);
});

test('Manual controls pause and resume without deleting student resources', () => {
  assert.match(workerControlWorkflow, /environment: student/);
  assert.match(workerControlWorkflow, /pause-worker/);
  assert.match(workerControlWorkflow, /pause-all/);
  assert.match(workerControlWorkflow, /SELECT 0/);
  assert.match(workerControlWorkflow, /SELECT azure_scaler\.analysis_queue_depth\(\)/);
  assert.match(workerControlWorkflow, /az containerapp job stop/);
  assert.match(workerControlWorkflow, /az containerapp ingress disable/);
  assert.doesNotMatch(workerControlWorkflow, /az (?:containerapp|group|resource) delete/);
});

test('Supabase scaler change is additive and exposes only aggregate queue depth', () => {
  assert.match(scalerMigration, /create schema if not exists azure_scaler/);
  assert.match(scalerMigration, /alter default privileges in schema azure_scaler/);
  assert.match(scalerMigration, /create or replace function azure_scaler\.analysis_queue_depth\(\)/);
  assert.match(scalerMigration, /returns bigint/);
  assert.match(scalerMigration, /revoke all privileges[\s\S]*from public, anon, authenticated, service_role/);
  assert.doesNotMatch(scalerMigration, /\b(?:drop|truncate|delete|alter table)\b/i);
});

test('Student database identity is validated before migration or credential writes', () => {
  const checks = [...deploymentWorkflow.matchAll(/run: node scripts\/student-environment.js --verify-keys/g)];
  assert.equal(checks.length, 2);
  assert.ok(checks[0].index < deploymentWorkflow.indexOf('supabase migration list'));
  assert.ok(checks[1].index < deploymentWorkflow.indexOf('az keyvault secret set'));
  assert.match(deploymentWorkflow, /if: github.ref == 'refs\/heads\/main'/);
  assert.match(deploymentWorkflow, /verify_container_runtime.sh "\$IMAGE_REFERENCE"/);
  assert.match(deploymentWorkflow, /\^ghcr\\\.io\/nathann-275\/peso-backend@sha256:\[a-f0-9\]\{64\}\$/);
  assert.match(deploymentWorkflow, /POSE_COMPARISON_IMAGE_REFERENCE: \$\{\{ inputs\.pose_comparison_image_reference \}\}/);
  assert.match(deploymentWorkflow, /"\$POSE_COMPARISON_IMAGE_REFERENCE" != "\$IMAGE_REFERENCE"/);
  const previewStart = deploymentWorkflow.indexOf('  preview:');
  const deployStart = deploymentWorkflow.indexOf('  deploy:');
  const approvalStart = deploymentWorkflow.indexOf('Bind human pose approval and migration approval');
  assert.ok(previewStart < deployStart);
  assert.ok(deployStart < approvalStart, 'human approvals must happen only after preview artifacts exist');
  assert.match(studentBicep, /name: 'PESO_DEPLOYMENT_ENVIRONMENT'[\s\S]*value: 'student'/);
  assert.match(read('docs/adr/0012-define-student-environment.md'), /iseqgaewjpjcxrndibep/);
  assert.match(read('netlify.toml'), /\[context.main.environment\][\s\S]*PESO_RELEASE_ENV = "student"/);
});

test('Student release binds credentials, API origin, and migrations to independently verified evidence', () => {
  assert.doesNotMatch(
    deploymentWorkflow.match(/jobs:\n  validate:[\s\S]*?\n    steps:/)?.[0] ?? '',
    /secrets\./,
    'validation secrets must be scoped to the step that consumes them'
  );
  assert.doesNotMatch(deploymentWorkflow, /SUPABASE_JWT_SECRET|supabase-jwt-secret/);
  assert.match(deploymentWorkflow, /api_url=.*azure-student-deployment-outputs\.json/);
  assert.match(deploymentWorkflow, /student-api-release-binding\.json/);
  assert.match(deploymentWorkflow, /azure_deployment_outputs_sha256: \$outputs_sha256/);
  assert.match(deploymentWorkflow, /image_reference: \$image_reference/);
  assert.match(deploymentWorkflow, /source_workflow_run_id: \$run_id/);
  assert.doesNotMatch(deploymentWorkflow, /vars\.(?:STUDENT_API_URL|VERIFIED_STUDENT_API_URL)/);
  assert.match(read('scripts/release-env.js'), /config\/student-api-release-binding\.json/);

  const preview = deploymentWorkflow.indexOf('NO_COLOR=1 supabase db push --db-url "$SUPABASE_DB_URL" --dry-run 2>&1 | tee');
  const checksums = deploymentWorkflow.indexOf('sha256sum list.txt plan.txt > SHA256SUMS');
  const download = deploymentWorkflow.indexOf('actions/download-artifact@');
  const verifyChecksum = deploymentWorkflow.indexOf('sha256sum --check SHA256SUMS');
  const comparePlan = deploymentWorkflow.indexOf('cmp --silent reviewed-migrations/plan.txt current-migrations/plan.txt');
  const apply = deploymentWorkflow.lastIndexOf('supabase db push --db-url "$SUPABASE_DB_URL"');
  assert.ok(preview > 0 && checksums > preview && download > checksums && verifyChecksum > download);
  assert.ok(comparePlan > verifyChecksum && apply > comparePlan, 'only the revalidated migration plan may be applied');
});
