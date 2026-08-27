const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const mainSource = fs.readFileSync(
  path.join(__dirname, '../infra/azure/staging/main.bicep'),
  'utf8'
);
const workloadsSource = fs.readFileSync(
  path.join(__dirname, '../infra/azure/staging/workloads.bicep'),
  'utf8'
);

test('Azure staging resources stay isolated, disabled by default, and budgeted', () => {
  assert.match(mainSource, /targetScope = 'subscription'/);
  assert.match(mainSource, /param location string = 'westus2'/);
  assert.match(mainSource, /param enableWorkloads bool = false/);
  assert.match(mainSource, /rg-peso-staging-westus2/);
  assert.match(mainSource, /name: 'peso-staging-monthly'[\s\S]*amount: 1/);
  assert.match(mainSource, /threshold: 50/);
  assert.match(mainSource, /threshold: 80/);
  assert.match(mainSource, /threshold: 100/);
  assert.match(mainSource, /name: 'ResourceGroupName'/);
});

test('Container Apps API uses the locked scale, probes, CORS, and image digest', () => {
  assert.match(workloadsSource, /log-peso-staging-westus2/);
  assert.match(workloadsSource, /retentionInDays: 30/);
  assert.match(workloadsSource, /cae-peso-staging-westus2/);
  assert.doesNotMatch(workloadsSource, /ApplicationInsights|components@/i);
  assert.match(workloadsSource, /peso-backend-staging/);
  assert.match(workloadsSource, /imageReference = '\$\{imageRepository\}@\$\{imageDigest\}'/);
  assert.match(workloadsSource, /external: true[\s\S]*targetPort: 10000/);
  assert.match(workloadsSource, /ingress: enableWorkloads \?/);
  assert.match(workloadsSource, /minReplicas: 0[\s\S]*maxReplicas: 1/);
  assert.match(workloadsSource, /type: 'Startup'[\s\S]*path: '\/health'/);
  assert.match(workloadsSource, /type: 'Liveness'[\s\S]*path: '\/health'/);
  assert.match(workloadsSource, /type: 'Readiness'[\s\S]*path: '\/health\/ready'/);
  assert.match(workloadsSource, /cpu: json\('0\.25'\)[\s\S]*memory: '0\.5Gi'/);
  assert.match(workloadsSource, /BACKEND_CORS_ORIGINS'[\s\S]*https:\/\/main--peso-webapp\.netlify\.app/);
  assert.match(workloadsSource, /BACKEND_CORS_ALLOW_PRIVATE_NETWORK'[\s\S]*value: 'false'/);
});

test('event worker polls PostgreSQL once at a time without Azure retries', () => {
  assert.match(workloadsSource, /peso-analysis-worker-staging/);
  assert.match(workloadsSource, /triggerType: 'Event'/);
  assert.match(workloadsSource, /replicaTimeout: 900/);
  assert.match(workloadsSource, /replicaRetryLimit: 0/);
  assert.match(workloadsSource, /parallelism: 1/);
  assert.match(workloadsSource, /replicaCompletionCount: 1/);
  assert.match(workloadsSource, /pollingInterval: 30/);
  assert.match(workloadsSource, /minExecutions: 0/);
  assert.match(workloadsSource, /maxExecutions: enableWorkloads \? 1 : 0/);
  assert.match(workloadsSource, /type: 'postgresql'/);
  assert.match(workloadsSource, /SELECT public\.pending_video_analysis_job_count\(\)/);
  assert.match(workloadsSource, /secretRef: 'scaler-db-url'[\s\S]*triggerParameter: 'connection'/);
  assert.match(
    workloadsSource,
    /command: \[[\s\S]*'python'[\s\S]*'-m'[\s\S]*'app\.jobs\.analysis_worker'[\s\S]*'--once'/
  );
});

test('GitHub deploy identity has resource-scoped image-update access without secret reads', () => {
  assert.match(workloadsSource, /id-peso-staging-deploy/);
  assert.match(workloadsSource, /issuer: 'https:\/\/token\.actions\.githubusercontent\.com'/);
  assert.match(workloadsSource, /subject: 'repo:\$\{githubRepository\}:ref:refs\/heads\/main'/);
  assert.match(mainSource, /Microsoft\.App\/containerApps\/read/);
  assert.match(mainSource, /Microsoft\.App\/containerApps\/write/);
  assert.match(mainSource, /Microsoft\.App\/jobs\/read/);
  assert.match(mainSource, /Microsoft\.App\/jobs\/write/);
  assert.doesNotMatch(mainSource, /listSecrets|\/delete|roleAssignments\/write/i);
  assert.match(workloadsSource, /scope: api/);
  assert.match(workloadsSource, /scope: workerJob/);
});

test('Bicep references short pre-seeded secrets without managing their values', () => {
  assert.match(workloadsSource, /secretRef: 'sb-url'/);
  assert.match(workloadsSource, /secretRef: 'sb-service'/);
  assert.match(workloadsSource, /secretRef: 'sb-jwt'/);
  assert.match(workloadsSource, /secretRef: 'cleanup-token'/);
  assert.match(workloadsSource, /secretRef: 'scaler-db-url'/);
  assert.doesNotMatch(workloadsSource, /secrets\s*:/);
  assert.doesNotMatch(workloadsSource, /sb_secret_|postgres(?:ql)?:\/\//i);
  assert.doesNotMatch(mainSource, /sb_secret_|postgres(?:ql)?:\/\//i);
});
