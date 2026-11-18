const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash } = require('node:crypto');

const source = fs.readFileSync(path.join(__dirname, 'npm-audit-ci.js'), 'utf8');
const paths = [
  'node_modules/anymatch/node_modules/picomatch', 'node_modules/jest-util/node_modules/picomatch',
  'node_modules/micromatch/node_modules/picomatch', 'node_modules/picomatch',
  'node_modules/readdirp/node_modules/picomatch',
];
function fixture() {
  return { vulnerabilities: {
    picomatch: { name: 'picomatch', severity: 'high', nodes: [...paths], via: [{
      source: 1247710, name: 'picomatch', dependency: 'picomatch',
      title: 'picomatch vulnerable to ReDoS through single-branch repeated extglobs',
      url: 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf', severity: 'high',
      cwe: ['CWE-1333'], cvss: { score: 7.5, vectorString: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H' },
      range: '<=4.0.7',
    }] },
    parent: { name: 'parent', severity: 'high', nodes: ['node_modules/parent'], via: ['picomatch'] },
  } };
}
const candidate = 'd454c8a4350b1f855bee9b4bbfb8e8eda390d6af';
const fixtureRecords = JSON.stringify(fixture().vulnerabilities, (key, value) =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : value);
const fixtureDigest = createHash('sha256').update(fixtureRecords).digest('hex');
function proposal({ active = false, now = Date.parse('2026-11-18T12:00:00Z'), context = {} } = {}) {
  const module = { exports: {} };
  class Clock extends Date { static now() { return now; } }
  // Activation exists only in this isolated VM; the source checkout stays pending.
  const status = active ? 'approved-by-nathan' : 'proposal-not-approved';
  const code = source.replace(/const PICOMATCH_REVIEW_STATUS = '[^']+';/,
    `const PICOMATCH_REVIEW_STATUS = '${status}';`).replace(
    /const PICOMATCH_BLOCKING_RECORDS_SHA256 = '[a-f0-9]{64}';/,
    `const PICOMATCH_BLOCKING_RECORDS_SHA256 = '${fixtureDigest}';`);
  const env = {
    GITHUB_ACTIONS: 'true', GITHUB_REPOSITORY: 'NathanN-275/Peso', GITHUB_WORKFLOW: 'Security Checks',
    GITHUB_EVENT_NAME: 'push', GITHUB_REF: 'refs/heads/main', GITHUB_SHA: candidate, ...context,
  };
  vm.runInNewContext(code + '\nmodule.exports.testReview = reviewPicomatchFindings;', {
    module, require, __dirname, process: { env, cwd: process.cwd }, Date: Clock,
  });
  return module.exports;
}
function review(report, options = {}, changes = {}) {
  const api = proposal(options);
  const blockers = api.findBlockingVulnerabilities(report, { packages: {} });
  return JSON.parse(JSON.stringify(api.testReview(report, blockers, {
    sourceCommit: candidate, sourceTreeDirty: false,
    patchVerification: 'passed', ...changes,
  })));
}
const names = findings => findings.map(finding => finding.name);

test('unapproved audit proposal blocks its exact reviewed leaf and every parent', () => {
  assert.deepEqual(names(review(fixture()).blockers), ['picomatch', 'parent']);
  assert.deepEqual(review(fixture()).treated, []);
});

test('isolated activation simulation rejects every mismatched workflow identity field', () => {
  for (const key of ['GITHUB_ACTIONS', 'GITHUB_REPOSITORY', 'GITHUB_WORKFLOW', 'GITHUB_EVENT_NAME',
    'GITHUB_REF', 'GITHUB_SHA']) {
    assert.equal(review(fixture(), { active: true, context: { [key]: 'mismatch' } }).blockers.length, 2);
  }
});

test('isolated activation simulation treats only the exact leaf and its derived HIGH causes', () => {
  const result = review(fixture(), { active: true });
  assert.deepEqual(result.blockers, []);
  assert.deepEqual(names(result.treated), ['picomatch', 'parent']);
  const api = proposal({ active: true });
  assert.equal(api.findBlockingVulnerabilities(fixture(), { packages: {} }, 'high', true).length, 2);
});

test('recovery PR treatment is limited to the exact merge ref, head, and base before expiry', () => {
  const context = {
    GITHUB_EVENT_NAME: 'pull_request', GITHUB_REF: 'refs/pull/56/merge',
    GITHUB_HEAD_REF: 'fix/staging-password-recovery', GITHUB_BASE_REF: 'main',
  };
  const options = { active: true, context };
  assert.deepEqual(names(review(fixture(), options).treated), ['picomatch', 'parent']);
  assert.equal(review(fixture(), { ...options, active: false }).blockers.length, 2);
  assert.equal(review(fixture(), { ...options, now: Date.parse('2026-11-20T00:00:00Z') }).blockers.length, 2);

  for (const [key, value] of Object.entries({
    GITHUB_EVENT_NAME: 'pull_request_target',
    GITHUB_REF: 'refs/pull/57/merge',
    GITHUB_HEAD_REF: 'other',
    GITHUB_BASE_REF: 'production',
  })) {
    assert.equal(review(fixture(), { ...options, context: { ...context, [key]: value } }).blockers.length, 2);
  }
});

test('proposal fails closed at expiry, with invalid time, dirty source or missing verified provenance', () => {
  for (const now of [Date.parse('2026-11-20T00:00:00Z'), Date.parse('2030-01-01'), NaN]) {
    assert.equal(review(fixture(), { active: true, now }).blockers.length, 2);
  }
  for (const changes of [{ sourceTreeDirty: true }, { sourceTreeDirty: null },
    { sourceCommit: 'main' }, { sourceCommit: null }, { patchVerification: 'missing' }]) {
    assert.equal(review(fixture(), { active: true }, changes).blockers.length, 2);
  }
});

test('changed advisory metadata, additional causes or changed copy sets cannot receive treatment', () => {
  for (const mutate of [
    r => r.vulnerabilities.picomatch.via[0].source++,
    r => { r.vulnerabilities.picomatch.via[0].range = '<=5'; },
    r => { r.vulnerabilities.picomatch.via[0].severity = 'critical'; },
    r => { r.vulnerabilities.picomatch.via[0].cvss.score = 9.9; },
    r => { r.vulnerabilities.picomatch.via[0].url += '#changed'; },
    r => { r.vulnerabilities.picomatch.via[0].newField = true; },
    r => { r.vulnerabilities.picomatch.nodes.pop(); },
    r => { r.vulnerabilities.picomatch.nodes.push('node_modules/new/node_modules/picomatch'); },
    r => { r.vulnerabilities.picomatch.via.push({ name: 'picomatch', severity: 'high', url: 'https://example.invalid/new' }); },
  ]) {
    const report = fixture(); mutate(report);
    assert.equal(review(report, { active: true }).blockers.length, 2);
  }
});

test('unrelated HIGH, CRITICAL, malformed and cyclic causes remain blocked without borrowing treatment', () => {
  for (const severity of ['high', 'critical']) {
    const report = fixture();
    report.vulnerabilities.other = { name: 'other', severity, nodes: ['node_modules/other'],
      via: [{ name: 'other', severity, url: 'https://example.invalid/new' }] };
    report.vulnerabilities.parent.via.push('other');
    report.vulnerabilities.parent.severity = severity;
    assert.deepEqual(names(review(report, { active: true }).blockers), ['picomatch', 'parent', 'other']);
  }
  for (const mutate of [
    r => { r.vulnerabilities.parent.via.push('missing'); },
    r => { r.vulnerabilities.parent.via.push('parent'); },
    r => { r.vulnerabilities.parent.nodes = ['node_modules/../parent']; },
    r => { r.vulnerabilities.parent.severity = 'critical'; },
  ]) {
    const report = fixture(); mutate(report);
    assert.deepEqual(names(review(report, { active: true }).blockers), ['picomatch', 'parent']);
  }
});

test('lower findings retain their ordinary threshold and complete raw audit data stays unchanged', () => {
  const report = fixture();
  report.vulnerabilities.lower = { name: 'lower', severity: 'moderate', nodes: ['node_modules/lower'],
    via: [{ name: 'lower', severity: 'moderate', url: 'https://example.invalid/lower' }] };
  const before = JSON.stringify(report);
  assert.deepEqual(review(report, { active: true }).blockers, []);
  assert.equal(JSON.stringify(report), before);
});

test('registry upgrade hints and derived package ranges do not alter pinned security records', () => {
  const report = fixture();
  Object.assign(report.vulnerabilities.parent, { effects: ['other'], range: '*', fixAvailable: true });
  Object.assign(report.vulnerabilities.picomatch, { range: '<=4.0.7', fixAvailable: false });
  assert.deepEqual(review(report, { active: true }).blockers, []);
});
