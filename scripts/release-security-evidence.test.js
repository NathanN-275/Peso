const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const YAML = require('yaml');
const jobs = YAML.parse(fs.readFileSync(path.join(__dirname, '../.github/workflows/security.yml'), 'utf8')).jobs;

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
  assert.match(audit.run, /pip-audit -r backend\/requirements.txt --format json --output artifacts\/python-audit\/report.json/);
  assert.equal(audit['continue-on-error'], undefined);
  assert.doesNotMatch(audit.run, /\|\| true|--ignore-vuln/);
  assert.match(retained(steps, 'artifacts/python-audit/').if, /steps.python_audit.outcome == 'failure'/);
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
