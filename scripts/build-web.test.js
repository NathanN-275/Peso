const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

function buildFixture(t, blocked = false) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'peso-build-web-test-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const repo = path.resolve(__dirname, '..');
  // Fixture module type must not inherit an unrelated ancestor package.json.
  fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ private: true, type: 'commonjs' }));
  for (const directory of ['scripts', 'web', 'bin', 'caller']) fs.mkdirSync(path.join(root, directory));
  for (const script of ['build-web.js', 'verify-marketing-build.js', 'dependency-patches.js', 'npm-audit-web-ci.js']) {
    fs.copyFileSync(path.join(__dirname, script), path.join(root, 'scripts', script));
  }
  fs.copyFileSync(path.join(repo, 'package-lock.json'), path.join(root, 'package-lock.json'));
  fs.cpSync(path.join(repo, 'patches/dependencies'), path.join(root, 'patches/dependencies'), { recursive: true });
  const patches = JSON.parse(fs.readFileSync(path.join(repo, 'patches/dependencies/manifest.json')));
  for (const pkg of patches.packages) {
    fs.cpSync(path.join(repo, pkg.path), path.join(root, pkg.path), { recursive: true });
  }
  const manifest = { name: 'fixture', dependencies: { sample: '1.0.0' } };
  fs.writeFileSync(path.join(root, 'web/package.json'), JSON.stringify(manifest));
  fs.writeFileSync(path.join(root, 'web/package-lock.json'), JSON.stringify({ lockfileVersion: 3,
    packages: { '': manifest, 'node_modules/sample': { version: '1.0.0' } } }));
  const report = { auditReportVersion: 2, vulnerabilities: blocked ? {
    sample: { name: 'sample', severity: 'high', isDirect: true, range: '*', nodes: ['node_modules/sample'],
      via: [{ source: 1234, name: 'sample', dependency: 'sample', title: 'Fixture finding',
        url: 'https://github.com/advisories/GHSA-vfj7-8cjw-p6xm', severity: 'high', range: '*' }],
      effects: [], fixAvailable: false },
  } : {}, metadata: {
    vulnerabilities: { info: 0, low: 0, moderate: 0, high: blocked ? 1 : 0, critical: 0, total: blocked ? 1 : 0 },
    dependencies: { prod: 1, dev: 0, optional: 0, peer: 0, peerOptional: 0, total: 1 },
  } };
  fs.writeFileSync(path.join(root, 'bin/git'), `#!${process.execPath}
const fs=require('node:fs'), args=process.argv.slice(2);
if(args.includes('rev-parse')) console.log(args.includes('HEAD^{tree}')?'${'b'.repeat(40)}':'${'a'.repeat(40)}');
else if(args.includes('status')) process.stdout.write('');
else if(args.includes('show')) process.stdout.write(fs.readFileSync(${JSON.stringify(path.join(root, 'scripts/npm-audit-web-ci.js'))}));
else process.exit(2);
`, { mode: 0o755 });
  fs.writeFileSync(path.join(root, 'bin/npm'), `#!${process.execPath}
const fs=require('node:fs'),path=require('node:path'),args=process.argv.slice(2),root=${JSON.stringify(root)};
if(args.includes('--version')) { console.log('12.0.2'); process.exit(0); }
const kind=args[0]==='audit'?'audit':args[0]==='--prefix'?'marketing':args.join(' ')==='run app:web:export'?'expo':'unknown';
fs.appendFileSync(path.join(root,'events.jsonl'),JSON.stringify({kind,mode:process.env.PESO_WEB_BUILD})+'\\n');
const dist=path.join(root,'dist');
if(kind==='audit') {
  if(${blocked}) { fs.mkdirSync(dist,{recursive:true}); fs.writeFileSync(path.join(dist,'partial'),'fixture'); }
  process.stdout.write(${JSON.stringify(JSON.stringify(report))}); process.exit(${blocked ? 1 : 0});
}
if(kind==='marketing') {
  for(const page of ['', 'beta','privacy','terms']) { const dir=path.join(dist,page); fs.mkdirSync(dir,{recursive:true}); fs.writeFileSync(path.join(dir,'index.html'),'<html><body>fixture</body></html>'); }
  fs.mkdirSync(path.join(dist,'auth'),{recursive:true}); fs.writeFileSync(path.join(dist,'auth/index.html'),'fixture auth');
  process.exit(0);
}
if(kind==='expo') { fs.mkdirSync(path.join(dist,'app'),{recursive:true}); fs.writeFileSync(path.join(dist,'app/index.html'),'fixture app'); process.exit(0); }
process.exit(2);
`, { mode: 0o755 });
  const dist = path.join(root, 'dist');
  fs.mkdirSync(path.join(dist, 'app'), { recursive: true });
  fs.writeFileSync(path.join(dist, 'app/stale.js'), 'fixture stale export');
  const run = mode => spawnSync(process.execPath, [path.join(root, 'scripts/build-web.js'), mode], {
    cwd: path.join(root, 'caller'), encoding: 'utf8', timeout: 15000,
    env: { ...process.env, CI: 'true', GITHUB_ACTIONS: 'false', GITHUB_SHA: 'a'.repeat(40),
      PATH: `${path.join(root, 'bin')}${path.delimiter}${process.env.PATH}` },
  });
  const events = () => fs.existsSync(path.join(root, 'events.jsonl'))
    ? fs.readFileSync(path.join(root, 'events.jsonl'), 'utf8').trim().split('\n').map(line => JSON.parse(line)) : [];
  return { root, dist, run, events };
}

test('blocked marketing audit prevents marketing/Expo execution and removes stale or partial output', t => {
  const f = buildFixture(t, true);
  const result = f.run('marketing');
  assert.equal(result.status, 1, result.stderr);
  assert.equal(fs.existsSync(f.dist), false);
  assert.deepEqual(f.events().map(event => event.kind), ['audit']);
  const base = path.join(f.root, 'artifacts/npm-audit-web');
  const decision = JSON.parse(fs.readFileSync(path.join(base, fs.readdirSync(base)[0], 'decision.json')));
  assert.equal(decision.exitCode, 1);
});

test('blocked private-beta audit prevents both exports and removes stale or partial output', t => {
  const f = buildFixture(t, true);
  const result = f.run('private-beta');
  assert.equal(result.status, 1, result.stderr);
  assert.equal(fs.existsSync(f.dist), false);
  assert.deepEqual(f.events().map(event => event.kind), ['audit']);
});

test('clean marketing audit preserves four-page verification and stale app/auth cleanup', t => {
  const f = buildFixture(t);
  const result = f.run('marketing');
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(f.events().map(event => event.kind), ['audit', 'marketing']);
  assert.equal(f.events().at(-1).mode, 'marketing');
  assert.equal(fs.existsSync(path.join(f.dist, 'app')), false);
  assert.equal(fs.existsSync(path.join(f.dist, 'auth')), false);
  assert.deepEqual(fs.readdirSync(f.dist).sort(), ['_redirects', 'beta', 'index.html', 'privacy', 'terms']);
  assert.match(result.stdout, /Marketing output verified/);
});

test('clean private-beta audit preserves sequential combined export and removes stale app bytes', t => {
  const f = buildFixture(t);
  const result = f.run('private-beta');
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(f.events().map(event => event.kind), ['audit', 'marketing', 'expo']);
  assert(f.events().filter(event => event.kind !== 'audit').every(event => event.mode === 'private-beta'));
  assert.equal(fs.readFileSync(path.join(f.dist, 'app/index.html'), 'utf8'), 'fixture app');
  assert.equal(fs.existsSync(path.join(f.dist, 'app/stale.js')), false);
});

test('missing audit program cannot fall through to either exporter or leave stale output', t => {
  const f = buildFixture(t);
  fs.unlinkSync(path.join(f.root, 'scripts/npm-audit-web-ci.js'));
  const result = f.run('private-beta');
  assert.equal(result.status, 1);
  assert.equal(fs.existsSync(f.dist), false);
  assert.deepEqual(f.events(), []);
});

test('unretainable audit evidence blocks the build and clears generated output', t => {
  const f = buildFixture(t);
  fs.writeFileSync(path.join(f.root, 'artifacts'), 'fixture obstruction');
  const result = f.run('marketing');
  assert.equal(result.status, 1);
  assert.match(result.stderr, /evidence.*blocked/i);
  assert.equal(fs.existsSync(f.dist), false);
  assert.deepEqual(f.events(), []);
});

test('Marketing generation failure after an accepted audit removes partial output and prevents Expo', t => {
  const f = buildFixture(t);
  const npm = path.join(f.root, 'bin/npm');
  fs.writeFileSync(npm, fs.readFileSync(npm, 'utf8').replace("  process.exit(0);\n}\nif(kind==='expo')", "  process.exit(2);\n}\nif(kind==='expo')"), { mode: 0o755 });
  const result = f.run('private-beta');
  assert.equal(result.status, 1);
  assert.deepEqual(f.events().map(event => event.kind), ['audit', 'marketing']);
  assert.equal(fs.existsSync(f.dist), false);
});
