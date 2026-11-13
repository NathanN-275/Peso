const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-secret-scan-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const repo = path.join(root, 'repo');
  fs.mkdirSync(repo);
  function git(...args) {
    const result = spawnSync('git', args, { cwd: repo, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout.trim();
  }
  git('init', '-b', 'main');
  git('config', 'user.name', 'Scan fixture');
  git('config', 'user.email', 'scan@example.invalid');
  fs.writeFileSync(path.join(repo, 'base.txt'), 'base\n');
  git('add', '.');
  git('commit', '-m', 'Base');
  const base = git('rev-parse', 'HEAD');
  git('switch', '-c', 'feature');
  fs.writeFileSync(path.join(repo, 'feature.txt'), 'feature\n');
  git('add', '.');
  git('commit', '-m', 'Feature');
  git('switch', 'main');
  git('merge', '--no-ff', '--no-commit', 'feature');
  fs.writeFileSync(path.join(repo, 'merge-only.txt'), 'synthetic merge-only secret\n');
  git('add', '.');
  git('commit', '-m', 'Merge with additional content');
  return { root, repo, git, base, sha: git('rev-parse', 'HEAD') };
}

test('exact merged snapshot catches content omitted by first-parent no-merges', t => {
  const f = fixture(t);
  assert.equal(f.git('log', '--format=%H', '--no-merges', '--first-parent', `${f.base}..${f.sha}`), '');
  const { scanCommittedSource } = require('./scan-committed-source');
  // Only the external scanner is substituted; Git archive and filesystem coverage are real.
  const result = scanCommittedSource({ repo: f.repo, sha: f.sha,
    evidenceRoot: path.join(f.root, 'evidence'), runScanner(args, options) {
      assert.equal(options.cwd.startsWith(os.tmpdir()), true);
      assert.ok(args.includes('--ignore-gitleaks-allow'));
      const snapshot = args.at(-1);
      assert.equal(fs.readFileSync(path.join(snapshot, 'merge-only.txt'), 'utf8'), 'synthetic merge-only secret\n');
      assert.equal(fs.existsSync(path.join(snapshot, '.git')), false);
      fs.writeFileSync(args[args.indexOf('--report-path') + 1], JSON.stringify([{
        RuleID: 'fixture', File: path.join(snapshot, 'merge-only.txt'), StartLine: 1,
        Secret: 'must-not-be-retained', Match: 'must-not-be-retained',
      }]));
      return { status: 1, stderr: 'INF scanned ~48 bytes (48 B) in 1ms', stdout: '' };
    } });
  assert.equal(result.exitCode, 1);
  assert.equal(result.evidence.sourceSha, f.sha);
  assert.equal(result.evidence.sourceTree, f.git('rev-parse', 'HEAD^{tree}'));
  assert.equal(result.evidence.inputFiles, 3);
  assert.equal(result.evidence.scannedBytes, 48);
  assert.equal(result.evidence.findingCount, 1);
  assert.equal(result.evidence.outcome, 'findings');
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(result.directory, 'findings.json'))),
    [{ rule: 'fixture', file: 'merge-only.txt', startLine: 1, endLine: null, startColumn: null, endColumn: null }]);
  assert.doesNotMatch(fs.readFileSync(path.join(result.directory, 'coverage.json'), 'utf8'), /must-not-be-retained/);
});

test('zero-byte success, scanner errors, missing and malformed reports fail closed', t => {
  const f = fixture(t);
  const { scanCommittedSource } = require('./scan-committed-source');
  for (const mode of ['zero', 'error', 'missing', 'malformed', 'contradictory', 'no-coverage-log', 'missing-binary', 'outside-snapshot', 'unsafe-byte-count']) {
    const result = scanCommittedSource({ repo: f.repo, sha: f.sha,
      evidenceRoot: path.join(f.root, mode), runScanner(args) {
        if (mode !== 'missing') fs.writeFileSync(args[args.indexOf('--report-path') + 1],
          mode === 'malformed' ? '{}' : mode === 'contradictory' ? '[{"RuleID":"fixture","File":"base.txt","StartLine":1}]' :
            mode === 'outside-snapshot' ? '[{"RuleID":"fixture","File":"../private.env","StartLine":1}]' : '[]');
        return { status: mode === 'error' ? 2 : mode === 'missing-binary' ? null : 0, stdout: '',
          stderr: mode === 'no-coverage-log' ? '' : `INF scanned ~${mode === 'zero' ? 0 : mode === 'unsafe-byte-count' ? '999999999999999999999999' : 48} bytes (48 B) in 1ms` };
      } });
    assert.equal(result.exitCode, 1, mode);
    assert.equal(result.evidence.outcome, 'error', mode);
  }
});

test('CI requires snapshot scanning and always retains sanitized failure evidence', () => {
  const workflow = fs.readFileSync(path.join(__dirname, '../.github/workflows/security.yml'), 'utf8');
  const job = workflow.split('\n  secret-scan:\n')[1].split('\n  reservation-database-security:')[0];
  assert.match(job, /fetch-depth: 0/);
  assert.match(job, /run: node --test scripts\/scan-committed-source.test.js/);
  assert.match(job, /GITLEAKS_VERSION: "8.30.1"/);
  assert.match(job, /run: node --test scripts\/scan-committed-source.integration.cjs/);
  assert.match(job, /if: \$\{\{ always\(\) && !cancelled\(\) \}\}\s+run: node scripts\/scan-committed-source.js/);
  assert.match(job, /always\(\).*steps.source_secret_scan.outcome == 'failure'/);
  assert.match(job, /path: artifacts\/source-secret-scan\//);
  assert.match(job, /if-no-files-found: error/);
  assert.doesNotMatch(job, /continue-on-error/);
});

test('clean scan retains byte coverage and archive/report hashes', t => {
  const f = fixture(t);
  const { scanCommittedSource } = require('./scan-committed-source');
  const result = scanCommittedSource({ repo: f.repo, sha: f.sha,
    evidenceRoot: path.join(f.root, 'clean'), runScanner(args) {
      fs.writeFileSync(args[args.indexOf('--report-path') + 1], '[]');
      return { status: 0, stdout: '', stderr: 'INF scanned ~48 bytes (48 B) in 1ms' };
    } });
  assert.equal(result.exitCode, 0);
  assert.equal(result.evidence.outcome, 'clean');
  for (const key of ['archiveSha256', 'findingsSha256', 'scriptSha256']) assert.match(result.evidence[key], /^[a-f0-9]{64}$/);
});

test('invalid refs, empty source and symlinks cannot become accepted coverage', t => {
  const f = fixture(t);
  const { scanCommittedSource } = require('./scan-committed-source');
  const mismatch = spawnSync(process.execPath, [path.join(__dirname, 'scan-committed-source.js'),
    f.base, path.join(f.root, 'mismatched-ci')], { cwd: f.repo, encoding: 'utf8',
    env: { ...process.env, CI: 'true' } });
  assert.equal(mismatch.status, 1);
  assert.equal(fs.existsSync(path.join(f.root, 'mismatched-ci')), false);
  for (const sha of ['HEAD', '0'.repeat(40)]) {
    assert.throws(() => scanCommittedSource({ repo: f.repo, sha, evidenceRoot: path.join(f.root, 'invalid') }));
  }
  fs.symlinkSync('base.txt', path.join(f.repo, 'link'));
  f.git('add', '.');
  f.git('commit', '-m', 'Symlink');
  assert.throws(() => scanCommittedSource({ repo: f.repo, sha: f.git('rev-parse', 'HEAD'),
    evidenceRoot: path.join(f.root, 'symlink') }), /regular/);
  f.git('checkout', '--orphan', 'empty');
  f.git('rm', '-rf', '.');
  f.git('commit', '--allow-empty', '-m', 'Empty');
  assert.throws(() => scanCommittedSource({ repo: f.repo, sha: f.git('rev-parse', 'HEAD'),
    evidenceRoot: path.join(f.root, 'empty') }), /empty/);
});
