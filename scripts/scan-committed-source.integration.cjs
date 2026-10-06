const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { randomBytes, createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const script = path.join(__dirname, 'scan-committed-source.js');
const reviewedFiles = ['config/combined-web-release-binding.json', 'scripts/release-env.test.js'];
const original = new Map(reviewedFiles.map(file => {
  const result = spawnSync('git', ['show', `HEAD:${file}`], { cwd: path.join(__dirname, '..') });
  assert.equal(result.status, 0);
  return [file, result.stdout.toString()];
}));

function scanFixture(t, change, reportMutation, afterCommit) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-source-policy-cli-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const repo = path.join(root, 'repo');
  fs.mkdirSync(repo);
  const files = new Map(original);
  if (change) change(files);
  for (const [file, bytes] of files) {
    fs.mkdirSync(path.dirname(path.join(repo, file)), { recursive: true });
    fs.writeFileSync(path.join(repo, file), bytes);
  }
  function git(...args) {
    const result = spawnSync('git', args, { cwd: repo, encoding: 'utf8' });
    assert.equal(result.status, 0, 'fixture Git operation failed');
    return result.stdout.trim();
  }
  git('init', '-b', 'main');
  git('config', 'user.name', 'Policy fixture');
  git('config', 'user.email', 'policy@example.invalid');
  git('add', '.');
  git('commit', '-m', 'Private policy fixture');
  const sha = git('rev-parse', 'HEAD');
  if (afterCommit) afterCommit(repo);
  const evidenceRoot = path.join(root, 'evidence');
  const env = { ...process.env, CI: 'true', GITHUB_SHA: sha };
  if (reportMutation) {
    // Fault injection only at the external executable boundary: run real
    // Gitleaks, then mutate its redacted report. Production has no test flags.
    const real = spawnSync('which', ['gitleaks'], { encoding: 'utf8' }).stdout.trim();
    assert.ok(real);
    const bin = path.join(root, 'bin');
    fs.mkdirSync(bin);
    const shim = `#!${process.execPath}\nconst fs=require('node:fs');
const {spawnSync}=require('node:child_process');
const args=process.argv.slice(2);
const r=spawnSync(${JSON.stringify(real)},args,{encoding:'utf8'});
process.stdout.write(r.stdout||'');process.stderr.write(r.stderr||'');
if(args[0]==='dir'){
  const file=args[args.indexOf('--report-path')+1];
  const report=JSON.parse(fs.readFileSync(file,'utf8'));
  const change=${JSON.stringify(reportMutation)};
  if(change.appendNull)report.push(null);
  else if(change.duplicate)report.push({...report[0]});
  else if(change.deleteField)delete report[0][change.deleteField];
  else Object.assign(report[0],change);
  fs.writeFileSync(file,JSON.stringify(report));
}
process.exit(r.status??2);\n`;
    fs.writeFileSync(path.join(bin, 'gitleaks'), shim, { mode: 0o700 });
    env.PATH = bin + path.delimiter + process.env.PATH;
  }
  const result = spawnSync(process.execPath, [script, sha, evidenceRoot], { cwd: repo, encoding: 'utf8',
    env });
  const directory = path.join(evidenceRoot, fs.readdirSync(evidenceRoot)[0]);
  const read = name => JSON.parse(fs.readFileSync(path.join(directory, name), 'utf8'));
  return { result, sha, directory, coverage: read('coverage.json'),
    findings: fs.existsSync(path.join(directory, 'findings.json')) ? read('findings.json') : null,
    policy: fs.existsSync(path.join(directory, 'policy.json')) ? read('policy.json') : null };
}

test('CLI accepts only reviewed non-secret findings while preserving raw failure and evidence', t => {
  const scan = scanFixture(t);
  assert.equal(scan.result.status, 0);
  assert.equal(scan.coverage.scannerExitCode, 1);
  assert.equal(scan.coverage.findingCount, 2);
  assert.equal(scan.coverage.outcome, 'findings');
  assert.ok(scan.coverage.scannedBytes > 0);
  assert.equal(scan.policy.sourceSha, scan.sha);
  assert.equal(scan.policy.outcome, 'accepted-with-reviewed-nonsecret-findings');
  assert.equal(scan.policy.exitCode, 0);
  assert.equal(scan.policy.classifiedCount, 2);
  assert.equal(scan.policy.blockingCount, 0);
  assert.equal(scan.policy.findingsSha256, scan.coverage.findingsSha256);
  assert.equal(createHash('sha256').update(fs.readFileSync(path.join(scan.directory, 'policy.json'))).digest('hex'),
    scan.coverage.policySha256);
  assert.equal(scan.policy.reviewedOccurrences.length, 2);
  assert.deepEqual(scan.policy.findings.map(f => f.classification),
    ['reviewed-public-resource-id', 'reviewed-public-resource-id']);
  for (const name of ['coverage.json', 'findings.json', 'policy.json']) {
    assert.doesNotMatch(fs.readFileSync(path.join(scan.directory, name), 'utf8'), /"(?:Secret|Match)"/);
  }
});

const resourceId = ['srv', 'dak9ohfqj5pc73ac2ga0'].join('-');
const githubToken = () => 'ghp_' + randomBytes(18).toString('hex');
const genericToken = () => randomBytes(24).toString('base64url');
const bindingFile = reviewedFiles[0];
const controls = [
  ['credential substituted for resource ID', files => files.set(bindingFile, files.get(bindingFile).replace(resourceId, githubToken()))],
  ['generic credential with identical redacted match', files => files.set(bindingFile, files.get(bindingFile).replace(resourceId, genericToken()))],
  ['unreviewed srv-prefixed value', files => files.set(bindingFile, files.get(bindingFile).replace(resourceId, 'srv-' + genericToken()))],
  ['credential elsewhere in binding file', files => files.set(bindingFile, files.get(bindingFile) + '\napi_key = "' + githubToken() + '"\n')],
  ['credential on same line as resource ID', files => files.set(bindingFile, files.get(bindingFile).replace(resourceId + '",', resourceId + '", api_key: "' + githubToken() + '",'))],
  ['public ID copied to unreviewed path', files => files.set('other/config.json', original.get(bindingFile))],
  ['public ID used in credential field', files => files.set(bindingFile, files.get(bindingFile).replace('api_service_id', 'api_key'))],
  ['unrelated byte change to reviewed file', files => files.set(bindingFile, files.get(bindingFile) + '\n')],
  ['credential elsewhere in test file', files => files.set(reviewedFiles[1], files.get(reviewedFiles[1]) + '\nconst api_key = "' + githubToken() + '";\n')],
];
for (const [name, change] of controls) test(`CLI blocks ${name} without dropping findings`, t => {
  const scan = scanFixture(t, change);
  assert.equal(scan.result.status, 1);
  assert.equal(scan.coverage.scannerExitCode, 1);
  assert.ok(scan.coverage.scannedBytes > 0);
  assert.equal(scan.policy.outcome, 'blocked');
  assert.ok(scan.policy.blockingCount > 0);
  assert.equal(scan.policy.rawFindingCount, scan.findings.length);
  assert.equal(scan.policy.classifiedCount + scan.policy.blockingCount, scan.findings.length);
});

test('CLI blocks unsupported metadata, decoded tags and duplicate occurrences', t => {
  for (const change of [{ RuleID: 'github-pat' }, { StartLine: 8 }, { EndLine: 8 }, { StartColumn: 4 }, { EndColumn: 48 },
    { Secret: 'unredacted-fixture' }, { Match: 'different-redacted-assignment' },
    { Tags: ['decoded:base64'] }, { deleteField: 'Tags' }, { SymlinkFile: 'other/path' }, { duplicate: true }]) {
    const scan = scanFixture(t, null, change);
    assert.equal(scan.result.status, 1);
    assert.ok(scan.policy.blockingCount > 0);
    assert.equal(scan.coverage.scannerExitCode, 1);
    assert.equal(scan.policy.rawFindingCount, change.duplicate ? 3 : 2);
  }
});

test('CLI retains raw finding count and fails closed on malformed finding metadata', t => {
  const scan = scanFixture(t, null, { appendNull: true });
  assert.equal(scan.result.status, 1);
  assert.equal(scan.coverage.scannerExitCode, 1);
  assert.equal(scan.coverage.findingCount, 3);
  assert.equal(scan.policy.rawFindingCount, 3);
  assert.equal(scan.policy.outcome, 'error');
  assert.equal(scan.policy.exitCode, 1);
});

test('CLI classifies archived committed bytes, not modified local files', t => {
  const scan = scanFixture(t, null, null, repo => {
    fs.appendFileSync(path.join(repo, bindingFile), '\napi_key = "' + githubToken() + '"\n');
  });
  assert.equal(scan.result.status, 0);
  assert.equal(scan.policy.outcome, 'accepted-with-reviewed-nonsecret-findings');
  assert.equal(scan.policy.classifiedCount, 2);
  assert.equal(scan.policy.rawFindingCount, 2);
});

test('CLI reports a genuinely clean snapshot without using any classification', t => {
  const scan = scanFixture(t, files => {
    files.clear();
    files.set('README.md', 'Clean source fixture.\n');
  });
  assert.equal(scan.result.status, 0);
  assert.equal(scan.coverage.scannerExitCode, 0);
  assert.equal(scan.policy.outcome, 'clean');
  assert.equal(scan.policy.rawFindingCount, 0);
  assert.equal(scan.policy.classifiedCount, 0);
  assert.equal(scan.policy.blockingCount, 0);
  assert.ok(scan.policy.scannedBytes > 0);
});
