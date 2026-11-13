const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const YAML = require('yaml');

test('marketing CI blocks all generated builds on the independent locked web audit', () => {
  const workflow = YAML.parse(fs.readFileSync(path.join(__dirname, '../.github/workflows/security.yml'), 'utf8'));
  const steps = workflow.jobs['marketing-build'].steps;
  const audit = steps.findIndex(step => step.run === 'node scripts/npm-audit-web-ci.js');
  assert(audit >= 0, 'marketing job must run the independent audit');
  assert.equal(steps[audit].id, 'web_audit');
  assert.equal(steps[audit].if, undefined);
  assert.equal(steps[audit]['continue-on-error'], undefined);
  const generated = steps.map((step, index) => /(?:web:build|app:web:export)/.test(step.run ?? '') ? index : -1).filter(index => index >= 0);
  assert(generated.length >= 3);
  assert(generated.every(index => index > audit));
  assert(generated.every(index => !steps[index].if && !steps[index]['continue-on-error']));
  assert(steps.slice(0, audit).some(step => step.run === 'npm --prefix web ci'));
  const retention = steps.find(step => step.with?.path === 'artifacts/npm-audit-web/');
  assert(retention, 'attempted audit evidence must be uploaded');
  assert(steps.indexOf(retention) > Math.max(...generated), 'retain audit attempts from every build wrapper');
  assert.equal(retention.uses, 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02');
  assert.equal(retention.if, "${{ always() && (steps.web_audit.outcome == 'success' || steps.web_audit.outcome == 'failure') }}");
  assert.equal(retention.with.name, 'marketing-node-audit-${{ github.sha }}-${{ github.run_attempt }}');
  assert.equal(retention.with['retention-days'], 90);
  assert.equal(retention.with['if-no-files-found'], 'error');
  assert.equal(retention['continue-on-error'], undefined);
});
