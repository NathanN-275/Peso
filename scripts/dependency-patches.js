const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');

const root = path.resolve(__dirname, '..');
// Repository-reviewed trust anchor. Updating this requires reviewing the manifest.
const MANIFEST_SHA256 = '1bae92dd0779b9cd026754c599c47508fd49f36a36c2c3decf07325f6728b6b0';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

function checkedPath(relative) {
  const parts = relative.split('/');
  if (path.isAbsolute(relative) || parts.some(p => !p || p === '.' || p === '..' || p.includes('\\'))) {
    throw new Error(`Unsafe path: ${relative}`);
  }
  let filename = root;
  for (const part of parts) {
    filename = path.join(filename, part);
    if (fs.lstatSync(filename).isSymbolicLink()) throw new Error(`Unsupported symbolic link: ${relative}`);
  }
  return filename;
}

function applyDiff(bytes, text, pins) {
  const sections = text.trimEnd().split(/^diff --git /m).slice(1);
  const results = new Map();
  for (const section of sections) {
    const lines = section.split('\n');
    const header = /^a\/(\S+) b\/\1$/.exec(lines.shift());
    if (!header) throw new Error('Unsupported patch header');
    const file = header[1];
    if (!pins[file] || pins[file].original === pins[file].patched || results.has(file)) {
      throw new Error(`Unexpected patch target: ${file}`);
    }
    if (!/^index [a-f0-9]+\.\.[a-f0-9]+(?: \d+)?$/.test(lines.shift()) ||
        lines.shift() !== `--- a/${file}` || lines.shift() !== `+++ b/${file}`) {
      throw new Error(`Unsupported patch format: ${file}`);
    }
    const source = bytes.get(file).toString('utf8');
    if (!source.endsWith('\n')) throw new Error(`Expected final newline: ${file}`);
    const input = source.slice(0, -1).split('\n');
    const output = [];
    let cursor = 0;
    while (lines.length) {
      // The final separator before the next diff is not part of a hunk.
      if (lines.length === 1 && lines[0] === '') break;
      const hunk = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(lines.shift());
      if (!hunk) throw new Error(`Unsupported patch hunk: ${file}`);
      const start = Number(hunk[1]) - 1;
      if (start < cursor || start > input.length) throw new Error(`Invalid hunk position: ${file}`);
      output.push(...input.slice(cursor, start));
      cursor = start;
      let removed = 0;
      let added = 0;
      while (lines.length && /^[ +\-]/.test(lines[0])) {
        const line = lines.shift();
        const value = line.slice(1);
        if (line[0] !== '+') {
          if (input[cursor++] !== value) throw new Error(`Patch context mismatch: ${file}`);
          removed++;
        }
        if (line[0] !== '-') { output.push(value); added++; }
      }
      if (removed !== Number(hunk[2] ?? 1) || added !== Number(hunk[4] ?? 1)) {
        throw new Error(`Patch hunk length mismatch: ${file}`);
      }
    }
    output.push(...input.slice(cursor));
    const result = Buffer.from(output.join('\n') + '\n');
    if (hash(result) !== pins[file].patched) throw new Error(`Patched hash mismatch: ${file}`);
    results.set(file, result);
  }
  const expected = Object.keys(pins).filter(f => pins[f].original !== pins[f].patched);
  if (results.size !== expected.length) throw new Error('Missing patch targets');
  return results;
}

function run(mode) {
  if (!['apply', 'verify'].includes(mode)) throw new Error('Choose apply or verify explicitly');
  const manifestBytes = fs.readFileSync(checkedPath('patches/dependencies/manifest.json'));
  if (hash(manifestBytes) !== MANIFEST_SHA256) throw new Error('Manifest integrity mismatch');
  const manifest = JSON.parse(manifestBytes);
  const lock = JSON.parse(fs.readFileSync(checkedPath('package-lock.json')));
  const actualCopies = new Map(manifest.packages.map(p => [p.name, []]));
  function scanModules(dir) {
    for (const entry of fs.readdirSync(checkedPath(dir), { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const packagePath = `${dir}/${entry.name}`;
      if (entry.isSymbolicLink()) throw new Error(`Unsupported symbolic package: ${packagePath}`);
      if (!entry.isDirectory()) continue;
      if (entry.name.startsWith('@')) {
        scanScope(packagePath);
      } else scanPackage(packagePath, entry.name);
    }
  }
  function scanScope(dir) {
    for (const entry of fs.readdirSync(checkedPath(dir), { withFileTypes: true })) {
      const packagePath = `${dir}/${entry.name}`;
      if (entry.isSymbolicLink()) throw new Error(`Unsupported symbolic package: ${packagePath}`);
      if (entry.isDirectory()) scanPackage(packagePath, entry.name);
    }
  }
  function scanPackage(packagePath, name) {
    actualCopies.get(name)?.push(packagePath);
    if (fs.existsSync(path.join(root, packagePath, 'node_modules'))) scanModules(`${packagePath}/node_modules`);
  }
  scanModules('node_modules');
  const plans = [];
  for (const pkg of manifest.packages) {
    if (JSON.stringify(actualCopies.get(pkg.name)) !== JSON.stringify([pkg.path])) {
      throw new Error(`Unexpected installed package paths: ${pkg.name}`);
    }
    const copies = Object.keys(lock.packages ?? {}).filter(p => p === pkg.path || p.endsWith(`/${pkg.path}`));
    const locked = lock.packages?.[pkg.path];
    if (copies.length !== 1 || copies[0] !== pkg.path ||
        locked.version !== pkg.version || locked.resolved !== pkg.resolved || locked.integrity !== pkg.integrity) {
      throw new Error(`Unexpected lockfile package: ${pkg.name}`);
    }
    const patchBytes = fs.readFileSync(checkedPath(`patches/dependencies/${pkg.patch.file}`));
    if (hash(patchBytes) !== pkg.patch.sha256) throw new Error(`Patch integrity mismatch: ${pkg.name}`);
    const inventory = [];
    function list(dir = '') {
      for (const entry of fs.readdirSync(checkedPath(dir ? `${pkg.path}/${dir}` : pkg.path), { withFileTypes: true })) {
        const file = path.posix.join(dir, entry.name);
        checkedPath(`${pkg.path}/${file}`);
        if (entry.isDirectory()) list(file);
        else inventory.push(file);
      }
    }
    list();
    if (JSON.stringify(inventory.sort()) !== JSON.stringify(Object.keys(pkg.files).sort())) {
      throw new Error(`Unexpected package inventory: ${pkg.name}`);
    }
    const bytes = new Map();
    let original = true;
    let patched = true;
    for (const [file, pin] of Object.entries(pkg.files)) {
      const data = fs.readFileSync(checkedPath(`${pkg.path}/${file}`));
      const digest = hash(data);
      if (digest !== pin.original && digest !== pin.patched) {
        throw new Error(`Installed integrity mismatch: ${pkg.name}/${file}`);
      }
      original &&= digest === pin.original;
      patched &&= digest === pin.patched;
      bytes.set(file, data);
    }
    if ((!original && !patched) || (mode === 'verify' && !patched)) {
      throw new Error(`Missing or partial patch: ${pkg.name}`);
    }
    plans.push({ pkg, changes: mode === 'apply' && !patched ? applyDiff(bytes, patchBytes.toString('utf8'), pkg.files) : new Map() });
  }
  // Validate and compute every package before writing any installed file.
  for (const { pkg, changes } of plans) {
    for (const [file, bytes] of changes) fs.writeFileSync(checkedPath(`${pkg.path}/${file}`), bytes);
    console.log(`${mode === 'apply' ? 'Applied' : 'Verified'} ${pkg.name}@${pkg.version} (${pkg.advisory}); npm audit policy unchanged.`);
  }
  if (mode === 'apply') run('verify');
}

if (require.main === module) {
  try { run(process.argv[2]); }
  catch (error) { console.error(`[dependency-patches] ${error.message}`); process.exitCode = 1; }
}
