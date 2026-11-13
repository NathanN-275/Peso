const assert = require('node:assert/strict');
const test = require('node:test');
const { mkdtempSync, writeFileSync, readFileSync, rmSync, readdirSync, mkdirSync, copyFileSync, cpSync, symlinkSync, existsSync } = require('node:fs');
const { createHash } = require('node:crypto');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { findBlockingVulnerabilities } = require('./npm-audit-ci');

const root = path.resolve(__dirname, '..');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const lock = { packages: {} };
const formerFindings = [
  ['brace-expansion', '1.1.16', 'GHSA-mh99-v99m-4gvg', 'node_modules/glob/node_modules/brace-expansion'],
  ['image-size', '1.2.1', 'GHSA-w3rx-r6r6-pgpr', 'node_modules/image-size'],
  ['image-size', '1.2.1', 'GHSA-5p2g-fcmc-qvqq', 'node_modules/image-size'],
  ['braces', '3.0.3', 'GHSA-vfj7-8cjw-p6xm', 'node_modules/braces', 1240992],
  ['node-forge', '1.4.0', 'GHSA-86w9-cpqp-85rv', 'node_modules/node-forge', 1240912],
];
const node = (name, via, severity = 'high') => ({ name, severity, nodes: [`node_modules/${name}`], via });
function report(severity = 'high', name = 'sample', id = 'GHSA-new') {
  return { auditReportVersion: 2, vulnerabilities: {
    [name]: node(name, [{ name, dependency: name, severity, url: `https://github.com/advisories/${id}` }], severity),
  } };
}
function formerReport([name, version, id, location, source]) {
  const result = report('high', name, id);
  result.vulnerabilities[name].nodes = [location];
  Object.assign(result.vulnerabilities[name].via[0], { source, range: `<=${version}` });
  result.vulnerabilities.parent = node('parent', [name]);
  return result;
}
const names = result => result.map(v => v.name);

test('only the strict classifier is exported; allowance capabilities are retired', () => {
  assert.deepEqual(Object.keys(require('./npm-audit-ci')), ['findBlockingVulnerabilities']);
  assert.deepEqual(findBlockingVulnerabilities({ vulnerabilities: {} }, lock), []);
});

test('all formerly treated exact HIGH records and their parents block regardless of caller assertions', () => {
  for (const finding of formerFindings) {
    const fixtureLock = { packages: { [finding[3]]: { version: finding[1] } } };
    for (const assertion of [undefined, true, { verified: true }, Symbol('verified temporary backports')]) {
      assert.deepEqual(names(findBlockingVulnerabilities(formerReport(finding), fixtureLock, 'high', assertion)), [finding[0], 'parent']);
    }
  }
});

test('valid lower findings remain below the HIGH threshold without hiding HIGH or CRITICAL branches', () => {
  for (const severity of ['info', 'low', 'moderate']) {
    const value = report(severity);
    value.vulnerabilities.parent = node('parent', ['sample'], severity);
    assert.deepEqual(findBlockingVulnerabilities(value, lock), []);
    value.vulnerabilities.critical = node('critical', [{ name: 'critical', severity: 'critical', url: 'https://example.invalid/advisory' }], 'critical');
    assert.deepEqual(names(findBlockingVulnerabilities(value, lock)), ['critical']);
  }
});

test('HIGH and CRITICAL block without relying on audit metadata totals', () => {
  for (const severity of ['high', 'critical']) {
    const value = report(severity); value.metadata = { vulnerabilities: { high: 0, critical: 0, total: 0 } };
    assert.deepEqual(names(findBlockingVulnerabilities(value, lock)), ['sample']);
  }
});

test('malformed package identities, locations and causes fail even below the threshold', () => {
  for (const change of [
    v => { v.name = 'different'; }, v => { v.severity = 'unknown'; }, v => { delete v.severity; },
    v => { v.nodes = []; }, v => { v.nodes = ['node_modules/different']; },
    v => { v.nodes = ['node_modules/../node_modules/sample']; }, v => { v.nodes = ['node_modules\\sample']; },
    v => { v.via = []; }, v => { v.via.push(null); }, v => { v.via.push({ severity: 'moderate' }); },
    v => { v.via.push('missing'); }, v => { v.via[0].name = 'different'; },
    v => { v.via[0].dependency = 'different'; }, v => { delete v.via[0].severity; },
  ]) {
    const value = report('moderate'); change(value.vulnerabilities.sample);
    value.vulnerabilities.parent = node('parent', ['sample'], 'moderate');
    assert.deepEqual(names(findBlockingVulnerabilities(value, lock)), ['sample', 'parent']);
  }
});

test('masked direct or transitive severity cannot downgrade a dangerous cause', () => {
  const direct = report('moderate'); direct.vulnerabilities.sample.via[0].severity = 'critical';
  assert.deepEqual(names(findBlockingVulnerabilities(direct, lock)), ['sample']);
  const transitive = report('critical'); transitive.vulnerabilities.parent = node('parent', ['sample'], 'moderate');
  transitive.vulnerabilities.grandparent = node('grandparent', ['parent'], 'moderate');
  assert.deepEqual(names(findBlockingVulnerabilities(transitive, lock)), ['sample', 'parent', 'grandparent']);
});

test('advisory-free cycles and dangling branches fail without borrowing sibling evidence', () => {
  for (const severity of ['high', 'moderate']) {
    const value = report(severity);
    value.vulnerabilities.a = node('a', ['b'], severity);
    value.vulnerabilities.b = node('b', ['a'], severity);
    value.vulnerabilities.parent = node('parent', ['sample', 'a'], severity);
    assert.deepEqual(names(findBlockingVulnerabilities(value, lock)), severity === 'high' ? ['sample', 'a', 'b', 'parent'] : ['a', 'b', 'parent']);
    value.vulnerabilities.b.via = ['missing'];
    assert.ok(names(findBlockingVulnerabilities(value, lock)).includes('parent'));
  }
});

test('valid cyclic lower dependency propagation can reach a concrete advisory', () => {
  const value = report('moderate');
  value.vulnerabilities.a = node('a', ['sample', 'b'], 'moderate');
  value.vulnerabilities.b = node('b', ['a'], 'moderate');
  assert.deepEqual(findBlockingVulnerabilities(value, lock), []);
});

test('malformed reports, lockfiles and audit thresholds are rejected', () => {
  for (const value of [{}, null, [], { vulnerabilities: [] }, { vulnerabilities: null }]) {
    assert.throws(() => findBlockingVulnerabilities(value, lock), /Malformed audit report/);
  }
  for (const value of [null, {}, { packages: [] }]) {
    assert.throws(() => findBlockingVulnerabilities(report(), value), /Malformed audit report/);
  }
  assert.throws(() => findBlockingVulnerabilities(report(), lock, 'unknown'), /Malformed audit report/);
});

function runAuditCli(t, responses, prepare = () => {}, now = '2026-10-27T20:00:00Z') {
  const directory = mkdtempSync(path.join(tmpdir(), 'peso-audit-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  copyFileSync(path.join(root, 'package-lock.json'), path.join(directory, 'package-lock.json'));
  mkdirSync(path.join(directory, 'scripts'));
  copyFileSync(path.join(__dirname, 'dependency-patches.js'), path.join(directory, 'scripts/dependency-patches.js'));
  cpSync(path.join(root, 'patches'), path.join(directory, 'patches'), { recursive: true });
  const manifest = JSON.parse(readFileSync(path.join(root, 'patches/dependencies/manifest.json')));
  for (const pkg of manifest.packages) cpSync(path.join(root, pkg.path), path.join(directory, pkg.path), { recursive: true });
  // Clock, Git and registry output are external boundaries; patch verification is real.
  writeFileSync(path.join(directory, 'clock.cjs'), `const RealDate = Date;
global.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : [${JSON.stringify(now)}])); }
  static now() { return new RealDate(${JSON.stringify(now)}).getTime(); }
};`);
  writeFileSync(path.join(directory, 'responses.json'), JSON.stringify(responses));
  writeFileSync(path.join(directory, 'git'), `#!${process.execPath}
if (process.argv.includes('rev-parse')) console.log('ca1b9cea7296d7baba4313b07b7547d20afdec25');
`, { mode: 0o755 });
  writeFileSync(path.join(directory, 'npm'), `#!${process.execPath}
const fs = require('node:fs');
const count = fs.existsSync('calls') ? Number(fs.readFileSync('calls', 'utf8')) : 0;
fs.writeFileSync('calls', String(count + 1));
const responses = JSON.parse(fs.readFileSync('responses.json', 'utf8'));
const response = responses[Math.min(count, responses.length - 1)];
process.stdout.write(response.stdout);
process.stderr.write(response.stderr || '');
process.exitCode = response.status;
`, { mode: 0o755 });
  prepare(directory);
  const result = spawnSync(process.execPath, ['--require', path.join(directory, 'clock.cjs'), path.join(__dirname, 'npm-audit-ci.js')], {
    cwd: directory, env: { ...process.env, CI: 'true', PATH: `${directory}${path.delimiter}${process.env.PATH}` },
    encoding: 'utf8', timeout: 15000,
  });
  assert.ifError(result.error);
  return { ...result, directory, calls: existsSync(path.join(directory, 'calls')) ? Number(readFileSync(path.join(directory, 'calls'), 'utf8')) : 0 };
}
function evidence(result) {
  const base = path.join(result.directory, 'artifacts/npm-audit');
  const dir = path.join(base, readdirSync(base)[0]);
  return { dir, decision: JSON.parse(readFileSync(path.join(dir, 'decision.json'))) };
}
const cleanAudit = { stdout: JSON.stringify({ auditReportVersion: 2, vulnerabilities: {} }), status: 0 };
const unavailableAudit = { stdout: JSON.stringify({ error: { code: 'E503', summary: 'Service Unavailable' } }), stderr: 'npm warn audit 503 Service Unavailable', status: 1 };

test('audit CLI accepts only a verified installation with no HIGH/CRITICAL and labels lower findings honestly', t => {
  const lower = report('moderate'); lower.metadata = { vulnerabilities: { high: 0, critical: 0, moderate: 1, total: 1 } };
  const result = runAuditCli(t, [{ stdout: JSON.stringify(lower), status: 0 }]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /no HIGH or CRITICAL findings; lower findings retained/);
  assert.doesNotMatch(result.stdout, /temporary backport|Project treatment|zero vulnerabilities/);
  assert.equal(evidence(result).decision.registryVulnerabilities.moderate, 1);
});

test('audit CLI blocks every formerly allowed record and parent even on status0 and misleading clean totals', t => {
  for (const finding of formerFindings) {
    const value = formerReport(finding); value.metadata = { vulnerabilities: { high: 0, critical: 0, total: 0 } };
    const result = runAuditCli(t, [{ stdout: JSON.stringify(value), status: 0 }]);
    assert.equal(result.status, 1, result.stderr);
    assert.deepEqual(names(evidence(result).decision.blockers), [finding[0], 'parent']);
  }
  const result = runAuditCli(t, [{ stdout: JSON.stringify(report('critical')), status: 0 }]);
  assert.equal(result.status, 1); assert.match(result.stderr, /sample/);
});

test('audit CLI blocks malformed and masked lower findings through real command evaluation', t => {
  for (const change of [v => { v.via[0].dependency = 'different'; }, v => { v.via[0].severity = 'critical'; }, v => { v.via = ['missing']; }]) {
    const value = report('moderate'); change(value.vulnerabilities.sample);
    const result = runAuditCli(t, [{ stdout: JSON.stringify(value), status: 0 }]);
    assert.equal(result.status, 1); assert.deepEqual(names(evidence(result).decision.blockers), ['sample']);
  }
});

test('audit CLI pins every reviewed input and rejects altered bytes before trusting verification', t => {
  for (const file of ['scripts/dependency-patches.js', 'package-lock.json', 'patches/dependencies/manifest.json',
    'patches/dependencies/braces-3.0.3.patch', 'patches/dependencies/metro-0.84.4-image-size-2.patch']) {
    const result = runAuditCli(t, [cleanAudit], d => writeFileSync(path.join(d, file), readFileSync(path.join(d, file), 'utf8') + '\n'));
    assert.equal(result.status, 1); assert.match(result.stderr, /reviewed evidence mismatch/);
  }
});

test('audit CLI rejects symlinked reviewed inputs even when bytes match', t => {
  for (const file of ['scripts/dependency-patches.js', 'package-lock.json', 'patches/dependencies/manifest.json',
    'patches/dependencies/braces-3.0.3.patch', 'patches/dependencies/metro-0.84.4-image-size-2.patch']) {
    const result = runAuditCli(t, [cleanAudit], d => {
      const filename = path.join(d, file); const outside = path.join(d, 'outside');
      copyFileSync(filename, outside); rmSync(filename); symlinkSync(outside, filename);
    });
    assert.equal(result.status, 1); assert.match(result.stderr, /symbolic/);
  }
});

test('audit CLI rejects missing verifier and failed physical package checks even with a clean report', t => {
  for (const change of [
    d => rmSync(path.join(d, 'scripts/dependency-patches.js')),
    d => writeFileSync(path.join(d, 'node_modules/braces/lib/parse.js'), 'altered bytes'),
    d => rmSync(path.join(d, 'node_modules/metro/src/Assets.js')),
    d => cpSync(path.join(d, 'node_modules/braces'), path.join(d, 'node_modules/example/node_modules/braces'), { recursive: true }),
    d => { const file = path.join(d, 'node_modules/braces/lib/parse.js'); const outside = path.join(d, 'outside.js'); copyFileSync(file, outside); rmSync(file); symlinkSync(outside, file); },
  ]) {
    const result = runAuditCli(t, [cleanAudit], change);
    assert.equal(result.status, 1); assert.match(result.stderr, /ENOENT|patch verification failed/);
  }
});

test('audit CLI refuses redirected artifact directories before writing outside the evidence scope', t => {
  for (const directory of ['artifacts', 'artifacts/npm-audit']) {
    const result = runAuditCli(t, [cleanAudit], d => {
      mkdirSync(path.join(d, 'elsewhere')); if (directory.includes('/')) mkdirSync(path.join(d, 'artifacts'));
      symlinkSync(path.join(d, 'elsewhere'), path.join(d, directory));
    });
    assert.equal(result.status, 1); assert.match(result.stderr, /symbolic/);
    assert.deepEqual(readdirSync(path.join(result.directory, 'elsewhere')), []);
  }
});

test('audit CLI requires usable source commit and status provenance in CI', t => {
  for (const body of ["console.log('not-a-commit');", "if(process.argv.includes('rev-parse')) console.log('ca1b9cea7296d7baba4313b07b7547d20afdec25'); else process.exitCode=1;"]) {
    const result = runAuditCli(t, [cleanAudit], d => writeFileSync(path.join(d, 'git'), `#!${process.execPath}\n${body}\n`, { mode: 0o755 }));
    assert.equal(result.status, 1); assert.match(result.stderr, /source-commit provenance/);
  }
});

test('audit CLI retains dirty-tree provenance rather than claiming a protected release checkout', t => {
  const result = runAuditCli(t, [cleanAudit], d => writeFileSync(path.join(d, 'git'), `#!${process.execPath}\nif(process.argv.includes('rev-parse')) console.log('ca1b9cea7296d7baba4313b07b7547d20afdec25'); else console.log(' M sample.js');\n`, { mode: 0o755 }));
  assert.equal(result.status, 0, result.stderr); assert.equal(evidence(result).decision.sourceTreeDirty, true);
});

test('no date renews a HIGH exception or expires a clean strict policy', t => {
  for (const now of ['2026-10-05T20:00:00Z', '2026-10-12T23:59:59Z', '2030-01-01T00:00:00Z']) {
    const clean = runAuditCli(t, [cleanAudit], undefined, now); assert.equal(clean.status, 0, clean.stderr);
    const denied = runAuditCli(t, [{ stdout: JSON.stringify(formerReport(formerFindings[4])), status: 1 }], undefined, now);
    assert.equal(denied.status, 1); assert.match(denied.stderr, /node-forge/);
    assert.equal(Object.hasOwn(evidence(clean).decision, 'expiresAt'), false);
  }
});

test('audit CLI retries a transient registry failure then evaluates the recovered report', t => {
  const result = runAuditCli(t, [unavailableAudit, cleanAudit]);
  assert.equal(result.status, 0, result.stderr); assert.equal(result.calls, 2); assert.match(result.stdout, /Root dependency audit accepted/);
});

test('audit CLI fails closed after exactly three transient attempts', t => {
  const result = runAuditCli(t, [unavailableAudit]);
  assert.equal(result.status, 1); assert.equal(result.calls, 3); assert.match(result.stderr, /usable vulnerability report/);
});

test('audit CLI blocks actual findings after service recovery', t => {
  const result = runAuditCli(t, [unavailableAudit, { stdout: JSON.stringify(report()), status: 1 }, cleanAudit]);
  assert.equal(result.status, 1); assert.equal(result.calls, 2); assert.match(result.stderr, /Unapproved high or critical/);
});

test('audit CLI does not retry malformed reports or nontransient errors', t => {
  for (const response of [
    { stdout: '<html>unavailable</html>', status: 1 },
    { stdout: JSON.stringify({ error: { code: 'E401' } }), status: 1 },
    { stdout: JSON.stringify({ auditReportVersion: 1, vulnerabilities: {} }), status: 0 },
    { stdout: JSON.stringify({ auditReportVersion: 2, vulnerabilities: [] }), status: 0 },
    { stdout: cleanAudit.stdout, status: 2 },
    { stdout: JSON.stringify({ auditReportVersion: 2, vulnerabilities: {}, error: { code: 'E503' } }), status: 1 },
  ]) {
    const result = runAuditCli(t, [response, cleanAudit]);
    assert.equal(result.status, 1); assert.equal(result.calls, 1); assert.doesNotMatch(result.stdout, /Root dependency audit accepted/);
  }
});

test('audit CLI retains exact raw output, hashes, reviewed inputs and decisions on success and failure', t => {
  for (const response of [cleanAudit, { stdout: 'not JSON', stderr: 'synthetic failure detail', status: 1 }]) {
    const result = runAuditCli(t, [response]); const { dir, decision } = evidence(result);
    assert.equal(readFileSync(path.join(dir, 'attempt-1.stdout'), 'utf8'), response.stdout);
    assert.equal(readFileSync(path.join(dir, 'attempt-1.stderr'), 'utf8'), response.stderr || '');
    assert.equal(decision.exitCode, response === cleanAudit ? 0 : 1);
    assert.equal(decision.attempts[0].stdoutSha256, hash(response.stdout));
    assert.equal(decision.attempts[0].stderrSha256, hash(response.stderr || ''));
    assert.equal(decision.auditScriptSha256, hash(readFileSync(path.join(__dirname, 'npm-audit-ci.js'))));
    assert.equal(decision.sourceCommit, 'ca1b9cea7296d7baba4313b07b7547d20afdec25');
    assert.equal(decision.auditLevel, 'high');
    assert.equal(readFileSync(path.join(dir, 'decision.sha256'), 'utf8'), hash(readFileSync(path.join(dir, 'decision.json'))) + '  decision.json\n');
    assert.equal(Object.hasOwn(decision, 'expiresAt'), false); assert.equal(Object.hasOwn(decision, 'treatedAdvisories'), false);
    assert.ok(decision.startedAt); assert.ok(decision.completedAt);
    if (response === cleanAudit) {
      assert.equal(decision.patchVerification, 'passed');
      assert.equal(Object.keys(decision.inputHashes).length, 5);
      for (const [file, digest] of Object.entries(decision.inputHashes)) assert.equal(digest, hash(readFileSync(path.join(root, file))));
      assert.equal(readFileSync(path.join(dir, 'npm-audit.json'), 'utf8'), response.stdout);
    }
  }
});
