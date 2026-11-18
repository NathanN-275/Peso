const assert = require('node:assert/strict');
const { execFileSync, spawnSync } = require('node:child_process');
const test = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const YAML = require('yaml');
const workflow = YAML.parse(fs.readFileSync(path.join(__dirname, '../.github/workflows/security.yml'), 'utf8'));
const { jobs } = workflow;

function retained(steps, directory) {
  const step = steps.find(step => step.with?.path === directory);
  assert(step, `missing retention for ${directory}`);
  assert.match(step.if, /always\(\)/);
  assert.match(step.with.name, /github.sha/);
  assert.match(step.with.name, /github.run_attempt/);
  assert.equal(step.with['if-no-files-found'], 'error');
  assert.equal(step.with['retention-days'], 90);
  assert.equal(step['continue-on-error'], undefined);
  return step;
}

test('Python audit keeps raw reports without relaxing its exit status', () => {
  const steps = jobs['backend-security'].steps;
  const audit = steps.find(step => step.id === 'python_audit');
  assert.match(audit.run, /pip-audit --timeout 60 -r backend\/requirements.txt --format json --output artifacts\/python-audit\/report.json/);
  assert.equal(audit['continue-on-error'], undefined);
  assert.doesNotMatch(audit.run, /\|\| true|--ignore-vuln/);
  assert.match(retained(steps, 'artifacts/python-audit/').if, /steps.python_audit.outcome == 'failure'/);
});

test('frontend path scope gates only the dependency audit on PRs', () => {
  const steps = jobs['frontend-security'].steps;
  const scope = steps.find(step => step.id === 'frontend_audit_scope');
  const audit = steps.find(step => step.id === 'npm_audit');
  assert.equal(steps[0].with['fetch-depth'], 2);
  assert.equal(scope.if, "github.event_name == 'pull_request'");
  assert.equal(audit.if, "steps.frontend_audit_scope.outputs.skip_audit != 'true'");
  assert.equal(audit.run, 'npm run audit:ci');
  assert.deepEqual(workflow.on.push.branches, ['main', 'production']);
  for (const run of ['npm ci', 'npm --prefix web ci', 'npm run typecheck', 'npm run test:policy']) {
    assert.equal(steps.find(step => step.run === run).if, undefined);
  }
  assert.match(retained(steps, 'artifacts/npm-audit/').if, /steps.npm_audit.outcome == 'failure'/);
});

test('only a verified backend or docs change set can skip the frontend audit', async t => {
  const script = jobs['frontend-security'].steps.find(step => step.id === 'frontend_audit_scope').run;
  const cases = [
    { name: 'backend only', files: ['backend/app.py'], skips: true },
    { name: 'docs only', files: ['docs/guide.md', 'README.md'], skips: true },
    { name: 'mixed backend and frontend', files: ['backend/app.py', 'app/file.tsx'], skips: false },
    { name: 'lockfile', files: ['package-lock.json'], skips: false },
    { name: 'build script', files: ['scripts/build-web.js'], skips: false },
    { name: 'workflow', files: ['.github/workflows/security.yml'], skips: false },
    { name: 'frontend renamed into docs', files: ['docs/moved.tsx'], movesFrontend: true, skips: false },
    { name: 'unknown merge identity', files: ['backend/app.py'], wrongHead: true, skips: false },
    { name: 'empty change set', files: [], skips: false },
  ];
  for (const entry of cases) {
    await t.test(entry.name, t => {
      const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-audit-scope-test-'));
      t.after(() => fs.rmSync(cwd, { recursive: true, force: true }));
      const git = (...args) => execFileSync('git', ['-c', 'user.name=Test',
        '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', ...args],
      { cwd, encoding: 'utf8' }).trim();
      git('init', '--quiet');
      fs.writeFileSync(path.join(cwd, 'original.tsx'), 'fixture\n');
      git('add', '--', 'original.tsx');
      git('commit', '--quiet', '-m', 'base');
      const base = git('rev-parse', 'HEAD');
      for (const file of entry.files) {
        const target = path.join(cwd, file);
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, 'fixture\n');
      }
      if (entry.movesFrontend) fs.unlinkSync(path.join(cwd, 'original.tsx'));
      git('add', '-A');
      git('commit', '--quiet', '--allow-empty', '-m', 'PR head');
      const head = git('rev-parse', 'HEAD');
      const merge = git('commit-tree', 'HEAD^{tree}', '-p', base, '-p', head, '-m', 'PR test merge');
      git('checkout', '--quiet', '--detach', merge);
      const output = path.join(cwd, 'step-output');
      const result = spawnSync('bash', ['-e', '-o', 'pipefail', '-c', script], {
        cwd, encoding: 'utf8', env: {
          ...process.env, GITHUB_SHA: merge, GITHUB_OUTPUT: output,
          PR_BASE_SHA: base, PR_HEAD_SHA: entry.wrongHead ? base : head,
        },
      });
      assert.ifError(result.error);
      assert.equal(result.status, 0, result.stderr);
      const decision = fs.existsSync(output) ? fs.readFileSync(output, 'utf8') : '';
      assert.equal(decision, entry.skips ? 'skip_audit=true\n' : '');
    });
  }
});

test('offline runtime evidence preserves pipeline failure and exact image identity', () => {
  const steps = jobs['container-security'].steps;
  const identity = steps.findIndex(step => /docker image inspect/.test(step.run ?? ''));
  const runtime = steps.findIndex(step => step.id === 'offline_runtime');
  assert(identity >= 0 && identity < runtime);
  assert.match(steps[identity].run, /GITHUB_SHA/);
  assert.equal(steps[runtime].shell, 'bash');
  assert.match(steps[runtime].run, /set -o pipefail/);
  assert.match(steps[runtime].run, /verify_container_runtime.sh peso-backend:security-check 2>&1 \| tee artifacts\/container-security\/runtime.log/);
  assert.equal(steps[runtime]['continue-on-error'], undefined);
  assert.match(retained(steps, 'artifacts/container-security/').if, /steps.offline_runtime.outcome == 'failure'/);
});

test('container JSON report retains the existing blocking severity policy', () => {
  const scan = jobs['container-security'].steps.find(step => step.id === 'container_audit');
  assert.equal(scan.with.format, 'json');
  assert.equal(scan.with.output, 'artifacts/container-security/trivy.json');
  assert.equal(scan.with['exit-code'], '1');
  assert.equal(scan.with.severity, 'HIGH,CRITICAL');
  assert.equal(scan.with['ignore-unfixed'], false);
  assert.equal(scan['continue-on-error'], undefined);
  assert.match(scan.uses, /@ed142fd0673e97e23eac54620cfb913e5ce36c25$/);
});
