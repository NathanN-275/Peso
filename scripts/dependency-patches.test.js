const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');

const root = path.resolve(__dirname, '..');
const assets = path.join(root, 'patches/dependencies');
const manifest = JSON.parse(fs.readFileSync(path.join(assets, 'manifest.json')));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

// Fixture construction only: restore published bytes if postinstall already ran.
// Independent recorded hashes prove this yields the exact registry baseline.
function pristineFile(bytes, patch, file, expected) {
  if (hash(bytes) === expected) return bytes;
  const source = bytes.toString().split('\n');
  const section = patch.split('diff --git ').find(s => s.startsWith(`a/${file} b/${file}\n`));
  assert.ok(section, `No fixture restoration patch for ${file}`);
  for (const hunk of section.split(/(?=^@@ )/m).slice(1).reverse()) {
    const lines = hunk.split('\n');
    const match = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/.exec(lines.shift());
    const body = lines.filter(l => /^[ +\-]/.test(l));
    const original = body.filter(l => l[0] !== '+').map(l => l.slice(1));
    const patched = body.filter(l => l[0] !== '-').map(l => l.slice(1));
    const start = Number(match[1]) - 1;
    assert.deepEqual(source.slice(start, start + patched.length), patched, `Fixture hunk absent for ${file}`);
    source.splice(start, patched.length, ...original);
  }
  const result = Buffer.from(source.join('\n'));
  assert.equal(hash(result), expected, `Fixture must match published ${file}`);
  return result;
}

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-patch-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.mkdirSync(path.join(dir, 'scripts'));
  if (fs.existsSync(path.join(__dirname, 'dependency-patches.js'))) {
    fs.copyFileSync(path.join(__dirname, 'dependency-patches.js'), path.join(dir, 'scripts/dependency-patches.js'));
  }
  fs.cpSync(assets, path.join(dir, 'patches/dependencies'), { recursive: true });
  const lock = JSON.parse(fs.readFileSync(path.join(root, 'package-lock.json')));
  fs.writeFileSync(path.join(dir, 'package-lock.json'), JSON.stringify(lock));
  fs.copyFileSync(path.join(root, 'package.json'), path.join(dir, 'package.json'));
  for (const pkg of manifest.packages) {
    const target = path.join(dir, pkg.path);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.cpSync(path.join(root, pkg.path), target, { recursive: true });
    const patch = fs.readFileSync(path.join(assets, pkg.patch.file), 'utf8');
    for (const [file, pin] of Object.entries(pkg.files)) {
      const filename = path.join(target, file);
      fs.writeFileSync(filename, pristineFile(fs.readFileSync(filename), patch, file, pin.original));
    }
  }
  return dir;
}

function cli(dir, mode) {
  return spawnSync(process.execPath, ['scripts/dependency-patches.js', mode], {
    cwd: dir, encoding: 'utf8', timeout: 10000,
  });
}

test('installer applies both pinned security patches to published packages', t => {
  const dir = fixture(t);
  const result = cli(dir, 'apply');
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /braces@3\.0\.3/);
  assert.match(result.stdout, /node-forge@1\.4\.0/);
});

test('read-only verifier accepts the exact installed patched packages', t => {
  const dir = fixture(t);
  assert.equal(cli(dir, 'apply').status, 0);
  const result = cli(dir, 'verify');
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Verified/);
});

test('reinstalling already verified patches succeeds without changing package bytes', t => {
  const dir = fixture(t);
  assert.equal(cli(dir, 'apply').status, 0);
  const filename = path.join(dir, 'node_modules/braces/lib/parse.js');
  const before = fs.readFileSync(filename);
  const result = cli(dir, 'apply');
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(fs.readFileSync(filename), before);
  assert.equal(cli(dir, 'verify').status, 0);
});

test('verifier rejects additional executable files inside a patched package', t => {
  const dir = fixture(t);
  assert.equal(cli(dir, 'apply').status, 0);
  fs.writeFileSync(path.join(dir, 'node_modules/braces/lib/extra.js'), 'module.exports = true;\n');
  const result = cli(dir, 'verify');
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /inventory/);
});

test('installer rejects changed lockfile identity before touching either package', t => {
  const dir = fixture(t);
  const lockPath = path.join(dir, 'package-lock.json');
  const lock = JSON.parse(fs.readFileSync(lockPath));
  lock.packages['node_modules/node-forge'].version = '1.4.1';
  fs.writeFileSync(lockPath, JSON.stringify(lock));
  const result = cli(dir, 'apply');
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /lockfile/);
  assert.equal(hash(fs.readFileSync(path.join(dir, 'node_modules/braces/lib/parse.js'))),
    manifest.packages[0].files['lib/parse.js'].original);
});

test('installer rejects a symlinked package file even when its bytes match', t => {
  const dir = fixture(t);
  const filename = path.join(dir, 'node_modules/braces/lib/parse.js');
  const outside = path.join(dir, 'original-parse.js');
  fs.renameSync(filename, outside);
  fs.symlinkSync(outside, filename);
  const result = cli(dir, 'apply');
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /symbolic/);
  assert.equal(hash(fs.readFileSync(outside)), manifest.packages[0].files['lib/parse.js'].original);
});

test('verifier rejects an untracked nested copy of a vulnerable package', t => {
  const dir = fixture(t);
  assert.equal(cli(dir, 'apply').status, 0);
  fs.cpSync(path.join(dir, 'node_modules/braces'), path.join(dir, 'node_modules/example/node_modules/braces'), { recursive: true });
  const result = cli(dir, 'verify');
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /package paths/);
});

for (const [name, change, error] of [
  ['unpatched installation', () => {}, /Missing or partial patch/],
  ['missing installed file', d => fs.unlinkSync(path.join(d, 'node_modules/braces/lib/parse.js')), /inventory/],
  ['altered package bytes', d => fs.appendFileSync(path.join(d, 'node_modules/node-forge/lib/rsa.js'), '\n// modified\n'), /integrity/],
  ['altered patch artifact', d => fs.appendFileSync(path.join(d, 'patches/dependencies/braces-3.0.3.patch'), '\n'), /Patch integrity/],
  ['missing patch artifact', d => fs.unlinkSync(path.join(d, 'patches/dependencies/node-forge-1.4.0.patch')), /ENOENT/],
  ['altered integrity manifest', d => fs.appendFileSync(path.join(d, 'patches/dependencies/manifest.json'), '\n'), /Manifest integrity/],
]) {
  test(`verifier rejects ${name}`, t => {
    const dir = fixture(t);
    if (name !== 'unpatched installation') assert.equal(cli(dir, 'apply').status, 0);
    change(dir);
    const result = cli(dir, 'verify');
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, error);
  });
}

test('installer refuses a partial brace patch rather than hiding an interrupted install', t => {
  const dir = fixture(t);
  const file = path.join(dir, 'node_modules/braces/lib/parse.js');
  const original = fs.readFileSync(file);
  assert.equal(cli(dir, 'apply').status, 0);
  fs.writeFileSync(file, original);
  const result = cli(dir, 'apply');
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /partial patch/);
});

test('installer checks both packages before writing the first patch', t => {
  const dir = fixture(t);
  fs.appendFileSync(path.join(dir, 'node_modules/node-forge/lib/rsa.js'), '\n// modified\n');
  assert.equal(cli(dir, 'apply').status, 1);
  assert.equal(hash(fs.readFileSync(path.join(dir, 'node_modules/braces/lib/parse.js'))),
    manifest.packages[0].files['lib/parse.js'].original);
});

test('npm postinstall applies the patches and the explicit verification command accepts them', t => {
  const dir = fixture(t);
  const run = script => spawnSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', script], {
    cwd: dir, encoding: 'utf8', timeout: 15000,
  });
  const install = run('postinstall');
  assert.equal(install.status, 0, install.stderr);
  assert.equal(run('deps:verify').status, 0);
});

test('typecheck rejects skipped postinstall even when npm lifecycle hooks are disabled', t => {
  const dir = fixture(t);
  const result = spawnSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', '--ignore-scripts', 'typecheck'], {
    cwd: dir, encoding: 'utf8', timeout: 15000,
  });
  assert.equal(result.status, 1);
  assert.match(result.stdout + result.stderr, /Missing or partial patch/);
});
