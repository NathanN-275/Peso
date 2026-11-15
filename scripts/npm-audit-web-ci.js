const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');

const root = path.resolve(__dirname, '..');
const web = path.join(root, 'web');
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const auditArgs = ['audit', '--json', '--audit-level=high', '--package-lock-only',
  '--include=prod', '--include=dev', '--include=optional', '--include=peer',
  '--fetch-retries=0', '--fetch-timeout=20000'];
const ranks = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 };
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const natural = value => Number.isSafeInteger(value) && value >= 0;

function validate(report, lock) {
  if (!record(report) || report.auditReportVersion !== 2 || Object.hasOwn(report, 'error') ||
      !record(report.vulnerabilities) || !record(report.metadata?.vulnerabilities)) {
    throw new Error('Unusable audit v2 report or registry error');
  }
  const counts = Object.fromEntries(Object.keys(ranks).map(s => [s, 0]));
  for (const [name, v] of Object.entries(report.vulnerabilities)) {
    if (!/^(?:@[a-z0-9._~-]+\/)?[a-z0-9._~-]+$/.test(name) || !record(v) || v.name !== name ||
        !Object.hasOwn(ranks, v.severity) || typeof v.isDirect !== 'boolean' || typeof v.range !== 'string' || !v.range ||
        !Array.isArray(v.via) || !v.via.length || !Array.isArray(v.effects) ||
        v.effects.some(effect => typeof effect !== 'string' || !Object.hasOwn(report.vulnerabilities, effect))) {
      throw new Error('Malformed vulnerability record');
    }
    if (!Array.isArray(v.nodes) || !v.nodes.length || new Set(v.nodes).size !== v.nodes.length || v.nodes.some(node =>
      typeof node !== 'string' || !node.startsWith('node_modules/') || !node.endsWith(`node_modules/${v.name}`) ||
      node.split('/').some(part => !part || part === '.' || part === '..' || part.includes('\\')) ||
      !Object.hasOwn(lock.packages, node) || typeof lock.packages[node].version !== 'string')) {
      throw new Error('Invalid or unlocked vulnerability path');
    }
    counts[v.severity] += 1;
    for (const cause of v.via) {
      const severity = typeof cause === 'string' ? report.vulnerabilities[cause]?.severity : cause?.severity;
      if (ranks[severity] === undefined || ranks[v.severity] === undefined || ranks[severity] > ranks[v.severity]) {
        throw new Error('Invalid or masked vulnerability severity');
      }
      if (typeof cause !== 'string' && (!Number.isSafeInteger(cause.source) || cause.source <= 0 ||
          cause.name !== v.name || cause.dependency !== v.name || typeof cause.title !== 'string' || !cause.title ||
          typeof cause.range !== 'string' || !cause.range ||
          !/^https:\/\/github\.com\/advisories\/GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$/.test(cause.url))) {
        throw new Error('Invalid advisory identity');
      }
    }
  }
  const grounded = new Set(Object.entries(report.vulnerabilities)
    .filter(([, v]) => v.via.some(cause => typeof cause !== 'string')).map(([name]) => name));
  let changed;
  do {
    changed = false;
    for (const [name, v] of Object.entries(report.vulnerabilities)) {
      if (!grounded.has(name) && v.via.some(cause => typeof cause === 'string' && grounded.has(cause))) {
        grounded.add(name); changed = true;
      }
    }
  } while (changed);
  if (grounded.size !== Object.keys(report.vulnerabilities).length) throw new Error('Unresolved advisory identity in dependency graph');
  const expected = { ...counts, total: Object.values(counts).reduce((a, b) => a + b, 0) };
  if (Object.entries(expected).some(([key, value]) => report.metadata?.vulnerabilities?.[key] !== value)) {
    throw new Error('Vulnerability metadata is inconsistent with records');
  }
  if (Object.keys(report.metadata.vulnerabilities).some(key => !Object.hasOwn(expected, key))) {
    throw new Error('Unknown vulnerability metadata');
  }
  const dependencies = report.metadata.dependencies;
  if (!record(dependencies) || !record(lock?.packages) ||
      dependencies.total !== Object.keys(lock.packages).filter(key => key !== '').length ||
      ['prod', 'dev', 'optional', 'peer', 'peerOptional', 'total'].some(key =>
        !natural(dependencies[key]) || dependencies[key] > dependencies.total + 1)) {
    throw new Error('Invalid or incomplete dependency metadata');
  }
}

function checked(relative, directory = false) {
  let current = root;
  for (const part of relative.split('/')) {
    current = path.join(current, part);
    if (fs.lstatSync(current).isSymbolicLink()) throw new Error(`Symbolic audit path rejected: ${relative}`);
  }
  const stat = fs.lstatSync(current);
  if (directory ? !stat.isDirectory() : !stat.isFile()) throw new Error(`Invalid audit path type: ${relative}`);
  return current;
}
function write(evidence, name, bytes) {
  checked(path.relative(root, evidence).split(path.sep).join('/'), true);
  fs.writeFileSync(path.join(evidence, name), bytes, { flag: 'wx', mode: 0o600 });
}
function inputs() {
  return Object.fromEntries(['web/package.json', 'web/package-lock.json'].map(file => [file, sha256(fs.readFileSync(checked(file)))]));
}
function lockedInputs() {
  let manifest, lock;
  try {
    manifest = JSON.parse(fs.readFileSync(checked('web/package.json'), 'utf8'));
    lock = JSON.parse(fs.readFileSync(checked('web/package-lock.json'), 'utf8'));
  } catch { throw new Error('Malformed package/lock input'); }
  if (!record(manifest) || !record(lock) || ![2, 3].includes(lock.lockfileVersion) || !record(lock.packages) ||
      !record(lock.packages['']) || manifest.name !== lock.packages[''].name) throw new Error('Invalid package/lock input');
  for (const field of ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']) {
    const a = manifest[field] ?? {}, b = lock.packages[''][field] ?? {};
    if (!record(a) || !record(b) || Object.keys(a).length !== Object.keys(b).length ||
        Object.entries(a).some(([name, range]) => typeof range !== 'string' || range !== b[name])) {
      throw new Error('Manifest dependency declarations do not match lock');
    }
  }
  return lock;
}
function git(args) {
  const result = spawnSync('git', ['-C', root, ...args], { timeout: 15000, maxBuffer: 8 * 1024 * 1024 });
  return result.status === 0 && !result.error ? result.stdout : null;
}
function source() {
  const commit = git(['rev-parse', 'HEAD'])?.toString().trim() ?? null;
  const tree = git(['rev-parse', 'HEAD^{tree}'])?.toString().trim() ?? null;
  const status = git(['status', '--porcelain', '--untracked-files=all']);
  const script = fs.readFileSync(checked('scripts/npm-audit-web-ci.js'));
  const committedScript = git(['show', 'HEAD:scripts/npm-audit-web-ci.js']);
  return { commit, tree, dirty: status === null ? null : Boolean(status.length),
    scriptSha256: sha256(script), scriptMatchesCommit: committedScript === null ? false : committedScript.equals(script) };
}
function environment() {
  const env = { ...process.env };
  // CLI includes override .npmrc omissions; remove inherited omit configuration too.
  for (const key of Object.keys(env)) if (/^npm_config_(omit|only|production|include|package_lock)$/i.test(key)) delete env[key];
  return env;
}

async function run() {
  for (const relative of ['artifacts', 'artifacts/npm-audit-web']) {
    try { fs.mkdirSync(path.join(root, relative), { mode: 0o700 }); } catch (error) { if (error.code !== 'EEXIST') throw error; }
    checked(relative, true);
  }
  const evidence = fs.mkdtempSync(path.join(root, 'artifacts/npm-audit-web/run-'));
  const decision = { startedAt: new Date().toISOString(), exitCode: 1, attempts: [], inputs: {}, auditArgs };
  console.log(`Web audit evidence: ${evidence}`);
  try {
    decision.source = source();
    if (!/^[a-f0-9]{40}$/.test(decision.source.commit ?? '') || !/^[a-f0-9]{40}$/.test(decision.source.tree ?? '') ||
        decision.source.dirty === null) throw new Error('Missing or invalid Git source provenance');
    if ((process.env.CI === 'true' || process.env.GITHUB_ACTIONS === 'true') &&
        (decision.source.dirty || !decision.source.scriptMatchesCommit ||
          (process.env.GITHUB_SHA && process.env.GITHUB_SHA !== decision.source.commit))) {
      throw new Error('CI audit requires clean committed implementation and matching source provenance');
    }
    decision.inputs.before = inputs();
    const lock = lockedInputs();
    const version = spawnSync(npm, ['--version'], { cwd: web, env: environment(), encoding: 'utf8', timeout: 15000 });
    if (version.status !== 0 || version.error) throw new Error('Cannot establish npm version');
    decision.npmVersion = version.stdout.trim();
    if (!/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/.test(decision.npmVersion)) throw new Error('Invalid npm version');
    let result, stdout, report;
    const transient = new Set(['E429', 'E500', 'E502', 'E503', 'E504', 'ETIMEDOUT', 'ECONNRESET', 'EAI_AGAIN']);
    for (let attempt = 1; attempt <= 3; attempt++) {
      result = spawnSync(npm, auditArgs, { cwd: web, env: environment(), timeout: 45000, maxBuffer: 32 * 1024 * 1024 });
      stdout = result.stdout ?? Buffer.alloc(0);
      const stderr = result.stderr ?? Buffer.alloc(0);
      write(evidence, `attempt-${attempt}.stdout`, stdout);
      write(evidence, `attempt-${attempt}.stderr`, stderr);
      decision.attempts.push({ attempt, exitCode: result.status, errorCode: result.error?.code ?? null,
        signal: result.signal ?? null, stdoutSha256: sha256(stdout), stderrSha256: sha256(stderr) });
      report = undefined;
      try { report = JSON.parse(stdout.toString()); } catch { /* raw bytes retained, classified below */ }
      const retry = transient.has(result.error?.code ?? report?.error?.code) &&
        (result.error?.code === 'ETIMEDOUT' || (!result.error && !result.signal && [0, 1].includes(result.status))) &&
        !(report?.auditReportVersion === 2 && record(report.vulnerabilities));
      if (retry && attempt < 3) { await delay(1000 * 2 ** (attempt - 1)); continue; }
      if (!report) throw new Error('Audit output is not valid JSON; raw bytes retained');
      break;
    }
    write(evidence, 'npm-audit.json', stdout);
    decision.reportSha256 = sha256(stdout);
    decision.registryVulnerabilities = report.metadata?.vulnerabilities;
    if (result.error || result.signal || ![0, 1].includes(result.status)) throw new Error('Audit subprocess failed');
    validate(report, lock);
    decision.blockers = Object.entries(report.vulnerabilities).filter(([, v]) => ['high', 'critical'].includes(v.severity))
      .map(([name, v]) => ({ name, severity: v.severity, nodes: v.nodes }));
    if (result.status !== (decision.blockers.length ? 1 : 0)) throw new Error('Audit subprocess exit is inconsistent with HIGH threshold');
    if (decision.blockers.length) throw new Error('HIGH/CRITICAL web dependencies require remediation; no exceptions');
    decision.exitCode = 0;
  } catch (error) {
    // Only sanitized categories are printed; raw npm output belongs in retained files.
    decision.error = error.message;
    console.error(`Web audit blocked: ${error.message}`);
  } finally {
    try {
      if (decision.inputs.before) {
        decision.inputs.after = inputs();
        if (JSON.stringify(decision.inputs.before) !== JSON.stringify(decision.inputs.after)) throw new Error('Audit inputs changed during execution');
      }
      if (decision.source) {
        decision.sourceAfter = source();
        if (JSON.stringify(decision.source) !== JSON.stringify(decision.sourceAfter)) throw new Error('Audit source changed during execution');
      }
    } catch (error) {
      decision.exitCode = 1;
      decision.error = error.message;
      console.error(`Web audit blocked: ${error.message}`);
    }
    decision.completedAt = new Date().toISOString();
    write(evidence, 'decision.json', JSON.stringify(decision, null, 2) + '\n');
  }
  return decision.exitCode;
}

if (require.main === module) run().then(code => { process.exitCode = code; }).catch(() => {
  console.error('Web audit evidence could not be retained safely; gate blocked.');
  process.exitCode = 1;
});
