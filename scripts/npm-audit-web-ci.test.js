const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const clean = { auditReportVersion: 2, vulnerabilities: {}, metadata: {
  vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 },
  dependencies: { prod: 1, dev: 0, optional: 0, peer: 0, peerOptional: 0, total: 1 },
} };

function fixture(t, report = clean, options = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'peso-web-audit-test-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const dir of ['scripts', 'web', 'bin', 'caller']) fs.mkdirSync(path.join(root, dir));
  fs.copyFileSync(path.join(__dirname, 'npm-audit-web-ci.js'), path.join(root, 'scripts/npm-audit-web-ci.js'));
  fs.writeFileSync(path.join(root, 'web/package.json'), JSON.stringify({ name: 'fixture', dependencies: { sample: '1.0.0' } }));
  fs.writeFileSync(path.join(root, 'web/package-lock.json'), JSON.stringify({ lockfileVersion: 3,
    packages: { '': { name: 'fixture', dependencies: { sample: '1.0.0' } },
      'node_modules/sample': { version: '1.0.0', resolved: 'https://registry.npmjs.org/sample/-/sample-1.0.0.tgz', integrity: 'sha512-fixture' } } }));
  fs.writeFileSync(path.join(root, 'bin/git'), `#!${process.execPath}\nconst args=process.argv.slice(2);\nif(args.includes('rev-parse')) console.log(args.includes('HEAD^{tree}') ? '${'b'.repeat(40)}' : '${'a'.repeat(40)}');\nelse if(args.includes('status')) process.stdout.write(${JSON.stringify(options.dirty ? '?? scripts/new.js\n' : '')});\nelse if(args.includes('show')) process.stdout.write(require('node:fs').readFileSync(${JSON.stringify(path.join(root, 'scripts/npm-audit-web-ci.js'))}));\nelse process.exit(2);\n`, { mode: 0o755 });
  fs.writeFileSync(path.join(root, 'bin/npm'), `#!${process.execPath}\nconst fs=require('node:fs');\nconst args=process.argv.slice(2);\nif(args.includes('--version')) { console.log('12.0.0'); process.exit(0); }\nfs.writeFileSync(${JSON.stringify(path.join(root, 'invocation.json'))}, JSON.stringify({args,cwd:process.cwd(),omit:process.env.npm_config_omit}));\nprocess.stdout.write(${JSON.stringify(JSON.stringify(report))});\nprocess.exit(${options.exit ?? 0});\n`, { mode: 0o755 });
  const run = (extra = {}) => spawnSync(process.execPath, [path.join(root, 'scripts/npm-audit-web-ci.js')], {
    cwd: path.join(root, 'caller'), encoding: 'utf8', timeout: 15000,
    env: { ...process.env, CI: 'true', GITHUB_ACTIONS: 'false', GITHUB_SHA: 'a'.repeat(40),
      PATH: `${path.join(root, 'bin')}${path.delimiter}${process.env.PATH}`, ...extra },
  });
  const evidence = () => {
    const base = path.join(root, 'artifacts/npm-audit-web');
    const runDir = path.join(base, fs.readdirSync(base)[0]);
    return { runDir, decision: JSON.parse(fs.readFileSync(path.join(runDir, 'decision.json'))) };
  };
  return { root, run, evidence };
}

test('clean locked web audit passes from another cwd with attributable retained evidence', t => {
  const f = fixture(t);
  const result = f.run({ npm_config_omit: 'dev' });
  assert.equal(result.status, 0, result.stderr);
  const { runDir, decision } = f.evidence();
  assert.equal(decision.exitCode, 0);
  assert.equal(decision.source.commit, 'a'.repeat(40));
  assert.equal(decision.source.tree, 'b'.repeat(40));
  assert.equal(decision.source.dirty, false);
  assert.equal(decision.source.scriptMatchesCommit, true);
  assert.equal(decision.npmVersion, '12.0.0');
  assert.equal(decision.attempts[0].stdoutSha256, hash(fs.readFileSync(path.join(runDir, 'attempt-1.stdout'))));
  assert.equal(decision.reportSha256, hash(fs.readFileSync(path.join(runDir, 'npm-audit.json'))));
  assert.deepEqual(decision.inputs.before, decision.inputs.after);
  const invocation = JSON.parse(fs.readFileSync(path.join(f.root, 'invocation.json')));
  assert.equal(invocation.cwd, path.join(f.root, 'web'));
  assert(invocation.args.includes('--package-lock-only'));
  for (const type of ['prod', 'dev', 'optional', 'peer']) assert(invocation.args.includes(`--include=${type}`));
  assert.equal(invocation.omit, undefined);
});

function finding(severity = 'high', url = 'https://github.com/advisories/GHSA-vfj7-8cjw-p6xm') {
  const report = structuredClone(clean);
  report.vulnerabilities.sample = { name: 'sample', severity, isDirect: true,
    nodes: ['node_modules/sample'], range: '*', effects: [], fixAvailable: false,
    via: [{ source: 1234, name: 'sample', dependency: 'sample', title: 'Fixture finding',
      url, severity, range: '*' }] };
  report.metadata.vulnerabilities[severity] = 1;
  report.metadata.vulnerabilities.total = 1;
  return report;
}

test('HIGH findings fail without root exception inheritance and retain raw exit/report', t => {
  const f = fixture(t, finding(), { exit: 1 });
  assert.equal(f.run().status, 1);
  const { decision, runDir } = f.evidence();
  assert.equal(decision.exitCode, 1);
  assert.equal(decision.attempts[0].exitCode, 1);
  assert.deepEqual(decision.blockers, [{ name: 'sample', severity: 'high', nodes: ['node_modules/sample'] }]);
  assert.equal(decision.reportSha256, hash(fs.readFileSync(path.join(runDir, 'npm-audit.json'))));
});

test('a lower package severity cannot mask a HIGH cause', t => {
  const report = finding('moderate');
  report.vulnerabilities.sample.via[0].severity = 'high';
  const f = fixture(t, report);
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /severity/i);
});

test('audit metadata must agree with the complete vulnerability records', t => {
  const report = finding('moderate');
  report.metadata.vulnerabilities.total = 0;
  const f = fixture(t, report);
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /metadata/i);
});

test('unknown advisory identity cannot produce a moderate-only pass', t => {
  const report = finding('moderate');
  delete report.vulnerabilities.sample.via[0].source;
  const f = fixture(t, report);
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /advisory/i);
});

test('a vulnerability at an unlocked or redirected package path fails closed', t => {
  const report = finding('moderate');
  report.vulnerabilities.sample.nodes = ['node_modules/other'];
  const f = fixture(t, report);
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /path/i);
});

test('an error-shaped registry response is never a clean report', t => {
  const report = { ...structuredClone(clean), error: { code: 'EAUDITNOLOCK', summary: 'sensitive registry message' } };
  const f = fixture(t, report);
  const result = f.run();
  assert.equal(result.status, 1);
  assert(!result.stderr.includes('sensitive registry message'));
});

test('invalid subprocess exits cannot lend credibility to clean JSON', t => {
  const f = fixture(t, clean, { exit: 2 });
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /subprocess/i);
});

test('changed package bytes during the audit block acceptance and retain before/after hashes', t => {
  const f = fixture(t);
  const binary = path.join(f.root, 'bin/npm');
  const original = fs.readFileSync(binary, 'utf8');
  fs.writeFileSync(binary, original.replace('process.stdout.write(', `fs.appendFileSync(${JSON.stringify(path.join(f.root, 'web/package.json'))}, ' ');\nprocess.stdout.write(`), { mode: 0o755 });
  assert.equal(f.run().status, 1);
  const d = f.evidence().decision;
  assert.notEqual(d.inputs.before['web/package.json'], d.inputs.after['web/package.json']);
  assert.match(d.error, /changed/i);
});

test('missing Git provenance in CI cannot produce acceptance', t => {
  const f = fixture(t);
  fs.writeFileSync(path.join(f.root, 'bin/git'), `#!${process.execPath}\nprocess.exit(1);\n`, { mode: 0o755 });
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /provenance/i);
});

test('mismatched GitHub source SHA cannot produce acceptance', t => {
  const f = fixture(t);
  assert.equal(f.run({ GITHUB_SHA: 'c'.repeat(40) }).status, 1);
  assert.match(f.evidence().decision.error, /provenance/i);
});

test('uncommitted audit implementation cannot be represented as committed CI evidence', t => {
  const f = fixture(t, clean, { dirty: true });
  const git = path.join(f.root, 'bin/git');
  fs.writeFileSync(git, fs.readFileSync(git, 'utf8').replace("else if(args.includes('show'))", "else if(args.includes('show')) process.exit(1);\nelse if(false)"), { mode: 0o755 });
  assert.equal(f.run().status, 1);
  const d = f.evidence().decision;
  assert.equal(d.source.dirty, true);
  assert.equal(d.source.scriptMatchesCommit, false);
  assert.match(d.error, /CI/i);
});

test('dependency metadata cannot hide packages present in the complete lock', t => {
  const report = structuredClone(clean);
  report.metadata.dependencies.total = 0;
  const f = fixture(t, report);
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /dependency metadata/i);
});

test('transient registry failures retry with every attempt retained', t => {
  const f = fixture(t);
  const binary = path.join(f.root, 'bin/npm');
  const original = fs.readFileSync(binary, 'utf8');
  const countFile = path.join(f.root, 'attempt-count');
  fs.writeFileSync(binary, original.replace('process.stdout.write(', `const c=${JSON.stringify(countFile)}; const count=fs.existsSync(c)?Number(fs.readFileSync(c)):0; fs.writeFileSync(c,String(count+1));\nif(count===0) { process.stdout.write(JSON.stringify({error:{code:'E503'}})); process.exit(1); }\nprocess.stdout.write(`), { mode: 0o755 });
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  const { decision, runDir } = f.evidence();
  assert.equal(decision.attempts.length, 2);
  assert.equal(decision.attempts[0].stdoutSha256, hash(fs.readFileSync(path.join(runDir, 'attempt-1.stdout'))));
  assert.equal(decision.attempts[1].stdoutSha256, hash(fs.readFileSync(path.join(runDir, 'attempt-2.stdout'))));
});

test('invalid npm version output blocks the audit', t => {
  const f = fixture(t);
  const binary = path.join(f.root, 'bin/npm');
  fs.writeFileSync(binary, fs.readFileSync(binary, 'utf8').replace("console.log('12.0.0')", "console.log('unexpected')"), { mode: 0o755 });
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /npm version/i);
});

test('a manifest inconsistent with its lock cannot pass a registry audit', t => {
  const f = fixture(t);
  fs.writeFileSync(path.join(f.root, 'web/package.json'), JSON.stringify({ name: 'fixture', dependencies: { sample: '2.0.0' } }));
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /lock/i);
});

test('source drift during an audit cannot be bound to the original commit', t => {
  const f = fixture(t);
  const binary = path.join(f.root, 'bin/npm');
  const marker = path.join(f.root, 'source-changed');
  fs.writeFileSync(binary, fs.readFileSync(binary, 'utf8').replace('process.stdout.write(', `fs.writeFileSync(${JSON.stringify(marker)},'changed');\nprocess.stdout.write(`), { mode: 0o755 });
  const git = path.join(f.root, 'bin/git');
  fs.writeFileSync(git, fs.readFileSync(git, 'utf8').replace("if(args.includes('rev-parse'))", `if(args.includes('rev-parse') && require('node:fs').existsSync(${JSON.stringify(marker)})) console.log('${'c'.repeat(40)}');\nelse if(args.includes('rev-parse'))`), { mode: 0o755 });
  assert.equal(f.run().status, 1);
  assert.equal(f.evidence().decision.sourceAfter.commit, 'c'.repeat(40));
  assert.match(f.evidence().decision.error, /source.*changed/i);
});

test('CRITICAL fails while lower findings remain visible without blocking the HIGH threshold', async t => {
  for (const severity of ['critical', 'moderate', 'low', 'info']) {
    await t.test(severity, child => {
      const f = fixture(child, finding(severity), { exit: severity === 'critical' ? 1 : 0 });
      assert.equal(f.run().status, severity === 'critical' ? 1 : 0);
      assert.equal(f.evidence().decision.registryVulnerabilities[severity], 1);
    });
  }
});

test('all current root exception URLs are still blockers in the web audit', async t => {
  for (const [name, version, node, id] of [
    ['braces', '3.0.3', 'node_modules/braces', 'GHSA-vfj7-8cjw-p6xm'],
    ['node-forge', '1.4.0', 'node_modules/node-forge', 'GHSA-86w9-cpqp-85rv'],
    ['brace-expansion', '1.1.16', 'node_modules/glob/node_modules/brace-expansion', 'GHSA-mh99-v99m-4gvg'],
    ['image-size', '1.2.1', 'node_modules/image-size', 'GHSA-w3rx-r6r6-pgpr'],
    ['image-size', '1.2.1', 'node_modules/image-size', 'GHSA-5p2g-fcmc-qvqq'],
  ]) {
    const url = `https://github.com/advisories/${id}`;
    await t.test(url, child => {
      const report = finding('high', url);
      const v = report.vulnerabilities.sample;
      v.name = name; v.nodes = [node]; v.via[0].name = name; v.via[0].dependency = name;
      delete report.vulnerabilities.sample;
      report.vulnerabilities[name] = v;
      const f = fixture(child, report, { exit: 1 });
      fs.writeFileSync(path.join(f.root, 'web/package.json'), JSON.stringify({ name: 'fixture', dependencies: { [name]: version } }));
      fs.writeFileSync(path.join(f.root, 'web/package-lock.json'), JSON.stringify({ lockfileVersion: 3,
        packages: { '': { name: 'fixture', dependencies: { [name]: version } }, [node]: { version } } }));
      assert.equal(f.run().status, 1);
      assert.deepEqual(f.evidence().decision.blockers, [{ name, severity: 'high', nodes: [node] }]);
    });
  }
});

test('missing and symbolic inputs cannot be accepted', async t => {
  for (const input of ['web', 'web/package.json', 'web/package-lock.json']) {
    await t.test(input, child => {
      const f = fixture(child);
      const target = path.join(f.root, input);
      const saved = path.join(f.root, 'saved-input');
      fs.renameSync(target, saved);
      assert.equal(f.run().status, 1);
      fs.symlinkSync(saved, target);
      assert.equal(f.run().status, 1);
    });
  }
});

test('redirected or unwritable evidence destinations never produce acceptance', async t => {
  for (const kind of ['symlink', 'file', 'unwritable']) {
    await t.test(kind, child => {
      const f = fixture(child);
      const target = path.join(f.root, 'artifacts');
      if (kind === 'symlink') fs.symlinkSync(path.join(f.root, 'caller'), target);
      else if (kind === 'file') fs.writeFileSync(target, 'not a directory');
      else { fs.mkdirSync(target); fs.chmodSync(target, 0o000); }
      let result;
      try { result = f.run(); } finally { if (kind === 'unwritable') fs.chmodSync(target, 0o700); }
      assert.equal(result.status, 1);
      assert.match(result.stderr, /evidence.*blocked/i);
    });
  }
});

test('evidence runs are unique and never overwrite preceding decisions', t => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  const first = f.evidence();
  const bytes = fs.readFileSync(path.join(first.runDir, 'decision.json'));
  assert.equal(f.run().status, 0);
  assert.equal(fs.readdirSync(path.join(f.root, 'artifacts/npm-audit-web')).length, 2);
  assert.deepEqual(fs.readFileSync(path.join(first.runDir, 'decision.json')), bytes);
});

test('retry exhaustion fails with all three registry attempts retained', t => {
  const f = fixture(t, { error: { code: 'E503' } }, { exit: 1 });
  assert.equal(f.run().status, 1);
  const d = f.evidence().decision;
  assert.equal(d.attempts.length, 3);
  assert.equal(d.exitCode, 1);
});

test('process timeouts fail closed with bounded retries and retained failure evidence', t => {
  const f = fixture(t);
  const preload = path.join(f.root, 'timeout-boundary.cjs');
  fs.writeFileSync(preload, `const cp=require('node:child_process'); const real=cp.spawnSync;\ncp.spawnSync=function(command,args,options) {\nif(command==='npm' && args[0]==='audit') return {status:null, signal:'SIGTERM', error:Object.assign(new Error('fixture timeout'),{code:'ETIMEDOUT'}), stdout:Buffer.alloc(0), stderr:Buffer.from('fixture timeout')};\nreturn real(command,args,options); };\n`);
  assert.equal(f.run({ NODE_OPTIONS: `--require=${preload}` }).status, 1);
  const { decision, runDir } = f.evidence();
  assert.equal(decision.attempts.length, 3);
  for (const attempt of decision.attempts) {
    assert.equal(attempt.errorCode, 'ETIMEDOUT');
    assert.equal(attempt.signal, 'SIGTERM');
    assert.equal(attempt.stderrSha256, hash(fs.readFileSync(path.join(runDir, `attempt-${attempt.attempt}.stderr`))));
  }
});

test('malformed and unknown reports fail without echoing registry bodies', async t => {
  const reports = [null, [], {}, { ...clean, auditReportVersion: 3 },
    { ...clean, vulnerabilities: [] }, { ...clean, metadata: null },
    { ...clean, vulnerabilities: { sample: { ...finding('moderate').vulnerabilities.sample, severity: 'unknown' } } },
    { ...clean, vulnerabilities: { sample: { ...finding('moderate').vulnerabilities.sample, via: [] } } },
    { ...clean, vulnerabilities: { sample: { ...finding('moderate').vulnerabilities.sample, via: ['missing'] } } }];
  for (const [index, report] of reports.entries()) {
    await t.test(String(index), child => {
      const f = fixture(child, report);
      assert.equal(f.run().status, 1);
      assert.equal(f.evidence().decision.exitCode, 1);
    });
  }
  await t.test('invalid JSON', child => {
    const f = fixture(child);
    const npm = path.join(f.root, 'bin/npm');
    fs.writeFileSync(npm, fs.readFileSync(npm, 'utf8').replace(JSON.stringify(JSON.stringify(clean)), JSON.stringify('SENSITIVE_FIXTURE invalid JSON')), { mode: 0o755 });
    const result = f.run();
    assert.equal(result.status, 1);
    assert(!result.stderr.includes('SENSITIVE_FIXTURE'));
    const { runDir } = f.evidence();
    assert.match(fs.readFileSync(path.join(runDir, 'attempt-1.stdout'), 'utf8'), /SENSITIVE_FIXTURE/);
  });
});

test('an advisory-free dependency cycle is not valid moderate-only evidence', t => {
  const report = finding('moderate');
  report.vulnerabilities.sample.via = ['sample'];
  const f = fixture(t, report);
  assert.equal(f.run().status, 1);
  assert.match(f.evidence().decision.error, /advisory/i);
});
