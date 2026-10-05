const { readFileSync, mkdirSync, mkdtempSync, writeFileSync, lstatSync, readdirSync } = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');

const AUDIT_LEVEL = 'high';
const BACKPORT_EXPIRY = '2026-10-12T23:59:59Z';
const REVIEWED_INPUTS = {
  'scripts/dependency-patches.js': '9df792cf971d23fc2500471e93d9b66fb40070f9df441ab45144efea63030ff9',
  'package-lock.json': '0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c',
  'patches/dependencies/manifest.json': '1bae92dd0779b9cd026754c599c47508fd49f36a36c2c3decf07325f6728b6b0',
  'patches/dependencies/braces-3.0.3.patch': 'e07abe26dbd330daea0e448ca1382327322dd5eccc08c5dd1a9b9f7bf5a6d699',
  'patches/dependencies/node-forge-1.4.0.patch': 'be39d6da41ca04aed6ae697f65000184083b8a4c1b9874ab759fd2cfd4dc70fe',
  'node_modules/@expo/code-signing-certificates/build/main.js': '3670cfbd69934b475257649886517d0314890ca4139708d2c812efaab04bc6d1',
  'node_modules/expo/node_modules/@expo/cli/build/src/run/ios/codeSigning/Security.js': 'af3f12dfb57ef87ae4cb3903af4398eeb034750c08d4fe523bc6a7d3062998b2',
  'node_modules/micromatch/index.js': '6a56366fcf3ae8e678e574900a0acb2ea6f118ea030d09bcc1b1053ccab916bb',
};
const FRONTEND_SCOPE = ['src', 'lib', 'web', 'dashboard', 'context', 'assets', 'app.config.js', 'metro.config.js',
  'babel.config.js', 'tailwind.config.js', 'postcss.config.js', 'index.ts', 'package.json', 'app.json', 'netlify.toml',
  'scripts/build-web.js', 'scripts/netlify-build.js', 'scripts/release-env.js', 'scripts/release-verify.js',
  'scripts/verify-marketing-build.js', 'scripts/web-build-budget.js'];
const FRONTEND_SCOPE_SHA256 = '6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242';
const SEVERITY_RANK = {
  info: 0,
  low: 1,
  moderate: 2,
  high: 3,
  critical: 4,
};

const IMAGE_SIZE_ALLOWANCE = {
  dependency: 'image-size',
  version: '1.2.1',
  nodes: new Set(['node_modules/image-size']),
  reason:
    'Expo 57 Metro 0.84 pins image-size 1.x, both advisories have no patched release, and Metro uses it only for repository-owned build assets rather than user-uploaded runtime media.',
};

const ALLOWED_ADVISORIES = {
  'https://github.com/advisories/GHSA-mh99-v99m-4gvg': {
    dependency: 'brace-expansion',
    version: '1.1.16',
    nodes: new Set([
      'node_modules/expo/node_modules/brace-expansion',
      'node_modules/glob/node_modules/brace-expansion',
      'node_modules/test-exclude/node_modules/brace-expansion',
    ]),
    reason:
      'Expo 55 and React Native 0.83 build tooling pin minimatch 3, which cannot consume the patched brace-expansion 5 release.',
  },
  'https://github.com/advisories/GHSA-w3rx-r6r6-pgpr': IMAGE_SIZE_ALLOWANCE,
  'https://github.com/advisories/GHSA-5p2g-fcmc-qvqq': IMAGE_SIZE_ALLOWANCE,
};

// A module-private capability: only the CLI's successful real preflight can
// enable these treatments. Public classification helpers cannot assert it.
const VERIFIED_BACKPORTS = Symbol('verified temporary backports');
const BACKPORT_ADVISORIES = {
  'https://github.com/advisories/GHSA-vfj7-8cjw-p6xm': {
    dependency: 'braces', version: '3.0.3', source: 1240992, range: '<=3.0.3',
    nodes: new Set(['node_modules/braces']),
    reason: 'Verified Peso recursion/cycle backport; scope and expiry are documented, not an upstream patched release.',
  },
  'https://github.com/advisories/GHSA-86w9-cpqp-85rv': {
    dependency: 'node-forge', version: '1.4.0', source: 1240912, range: '<=1.4.0',
    nodes: new Set(['node_modules/node-forge']),
    reason: 'Verified Peso DigestAlgorithm element-count/NULL-content backport in lib/rsa.js only; prebuilt dist bundles are excluded.',
  },
};

const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const knownSeverity = value => Object.hasOwn(SEVERITY_RANK, value);
function validVulnerability(name, v) {
  return isRecord(v) && v.name === name && knownSeverity(v.severity) &&
    Array.isArray(v.nodes) && v.nodes.length > 0 &&
    v.nodes.every(n => typeof n === 'string' && n.startsWith('node_modules/') &&
      n.endsWith(`node_modules/${name}`) &&
      !n.split('/').some(p => !p || p === '.' || p === '..' || p.includes('\\'))) &&
    Array.isArray(v.via) && v.via.length > 0 &&
    v.via.every(c => typeof c === 'string' ? c.length > 0 :
      isRecord(c) && typeof c.name === 'string' && typeof c.url === 'string' && knownSeverity(c.severity));
}
function validCauses(name, vulnerabilities) {
  const v = vulnerabilities[name];
  return Object.hasOwn(vulnerabilities, name) && validVulnerability(name, v) && v.via.every(c => {
    if (typeof c === 'string') {
      return Object.hasOwn(vulnerabilities, c) && validVulnerability(c, vulnerabilities[c]) &&
        SEVERITY_RANK[vulnerabilities[c].severity] <= SEVERITY_RANK[v.severity];
    }
    return c.name === name && (!Object.hasOwn(c, 'dependency') || c.dependency === name) &&
      SEVERITY_RANK[c.severity] <= SEVERITY_RANK[v.severity];
  });
}

function isAllowedAdvisory(advisory, vulnerability, lockfile, authorization) {
  const backport = authorization === VERIFIED_BACKPORTS ? BACKPORT_ADVISORIES[advisory.url] : undefined;
  const allowance = backport ?? ALLOWED_ADVISORIES[advisory.url];
  if (!allowance || vulnerability.name !== allowance.dependency) {
    return false;
  }
  if (backport && (advisory.source !== backport.source || advisory.name !== backport.dependency ||
      advisory.dependency !== backport.dependency || advisory.range !== backport.range ||
      advisory.severity !== 'high' || vulnerability.severity !== 'high' ||
      vulnerability.nodes?.length !== 1)) return false;

  if (
    !Array.isArray(vulnerability.nodes) ||
    vulnerability.nodes.length === 0 ||
    vulnerability.nodes.some((node) => !allowance.nodes.has(node))
  ) {
    return false;
  }

  return vulnerability.nodes.every(
    (node) => lockfile.packages?.[node]?.version === allowance.version,
  );
}

function isAllowedVulnerability(
  name,
  vulnerabilities,
  lockfile,
  auditLevel = AUDIT_LEVEL,
  authorization,
) {
  const graph = new Map();
  const pending = [name];
  const minimumRank = SEVERITY_RANK[auditLevel];
  while (pending.length) {
    const current = pending.pop();
    if (graph.has(current)) continue;
    const v = vulnerabilities[current];
    if (!validCauses(current, vulnerabilities)) return false;
    if (v.via.some(c => typeof c === 'string' &&
        !validCauses(c, vulnerabilities))) return false;
    const causes = v.via.filter(c => {
      const rank = SEVERITY_RANK[typeof c === 'string' ? vulnerabilities[c]?.severity : c?.severity];
      return rank === undefined || rank >= minimumRank;
    });
    if (!causes.length) return false;
    const children = [];
    let grounded = false;
    for (const cause of causes) {
      if (typeof cause === 'string') { children.push(cause); pending.push(cause); }
      else {
        if (!cause || !isAllowedAdvisory(cause, v, lockfile, authorization)) return false;
        grounded = true;
      }
    }
    graph.set(current, { children, grounded });
  }
  // Every reachable branch needs its own concrete advisory evidence. This
  // fixed point supports genuine dependency cycles without lending sibling
  // evidence to a disconnected, advisory-free component.
  let changed;
  do {
    changed = false;
    for (const node of graph.values()) {
      if (!node.grounded && node.children.some(c => graph.get(c).grounded)) {
        node.grounded = true;
        changed = true;
      }
    }
  } while (changed);
  return [...graph.values()].every(node => node.grounded);
}

function findBlockingVulnerabilities(report, lockfile, auditLevel = AUDIT_LEVEL, authorization) {
  if (!isRecord(report) || !isRecord(report.vulnerabilities) ||
      !isRecord(lockfile?.packages) || !knownSeverity(auditLevel)) {
    throw new Error('Malformed audit report or lockfile');
  }
  const vulnerabilities = report.vulnerabilities;
  const minimumRank = SEVERITY_RANK[auditLevel];

  return Object.entries(vulnerabilities)
    .filter(([name, vulnerability]) => {
      const severityRank = SEVERITY_RANK[vulnerability?.severity];
      return !validCauses(name, vulnerabilities) || severityRank >= minimumRank;
    })
    .filter(
      ([name]) =>
        !isAllowedVulnerability(name, vulnerabilities, lockfile, auditLevel, authorization),
    )
    .map(([name, vulnerability]) => ({
      name,
      severity: vulnerability?.severity ?? 'unknown',
      nodes: Array.isArray(vulnerability?.nodes) ? vulnerability.nodes : [],
    }));
}

const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
function checkedFile(relative) {
  let current = process.cwd();
  for (const part of relative.split('/')) {
    current = path.join(current, part);
    if (lstatSync(current).isSymbolicLink()) throw new Error(`Unsupported symbolic audit evidence: ${relative}`);
  }
  return current;
}

function frontendScope() {
  const records = [];
  function walk(relative) {
    let stat;
    try { stat = lstatSync(relative); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
    if (stat.isSymbolicLink()) throw new Error(`Unsupported symbolic consumer scope: ${relative}`);
    if (stat.isDirectory()) {
      for (const entry of readdirSync(relative)) {
        if (entry.startsWith('.') || ['node_modules', 'dist'].includes(entry)) continue;
        walk(path.posix.join(relative, entry));
      }
    } else if (/\.(?:[cm]?js|jsx|[cm]?ts|tsx|json|astro|html|vue|svelte|mdx|toml)$/.test(relative)) {
      records.push(`${relative}\0${sha256(readFileSync(relative))}`);
    }
  }
  FRONTEND_SCOPE.forEach(walk);
  readdirSync('.').filter(f => /^App(?:\.[^.]+)?\.[cm]?[jt]sx?$/.test(f)).forEach(walk);
  return { fileCount: records.length, sha256: sha256(JSON.stringify(records.sort())) };
}

async function readAuditReport(evidence, decision) {
  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const maxAttempts = 3;
  const transientErrors = new Set([
    'E429', 'E500', 'E502', 'E503', 'E504',
    'ETIMEDOUT', 'ECONNRESET', 'EAI_AGAIN',
  ]);

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const result = spawnSync(
      npmCommand,
      [
        'audit', '--json', `--audit-level=${AUDIT_LEVEL}`,
        '--fetch-retries=0', '--fetch-timeout=20000',
      ],
      { encoding: 'utf8', timeout: 45000 },
    );
    const stdout = result.stdout ?? '';
    const stderr = result.stderr ?? '';
    writeFileSync(path.join(evidence, `attempt-${attempt}.stdout`), stdout, { flag: 'wx' });
    writeFileSync(path.join(evidence, `attempt-${attempt}.stderr`), stderr, { flag: 'wx' });
    decision.attempts.push({ attempt, exitCode: result.status, errorCode: result.error?.code ?? null,
      stdoutSha256: sha256(stdout), stderrSha256: sha256(stderr) });

    let report;
    try {
      report = JSON.parse(result.stdout);
    } catch {
      // Classify subprocess timeouts below; all other invalid output fails closed.
    }

    const usable = report?.auditReportVersion === 2 &&
      typeof report.vulnerabilities === 'object' &&
      report.vulnerabilities !== null &&
      !Array.isArray(report.vulnerabilities);
    const transient = transientErrors.has(
      result.error?.code ?? report?.error?.code,
    );
    if (!usable && transient && attempt < maxAttempts) {
      const waitMs = 1000 * 2 ** (attempt - 1);
      console.warn(`npm audit service unavailable (attempt ${attempt}/${maxAttempts}); retrying in ${waitMs}ms.`);
      await delay(waitMs);
      continue;
    }

    if (result.error) throw result.error;
    if (!report) {
      throw new Error('npm audit did not return valid JSON; raw output retained in audit evidence.');
    }
    if (!usable || report.error || ![0, 1].includes(result.status)) {
      throw new Error('npm audit did not return a usable vulnerability report; raw output retained in audit evidence.');
    }
    writeFileSync(path.join(evidence, 'npm-audit.json'), stdout, { flag: 'wx' });
    return report;
  }
}

async function runAudit() {
  const base = path.resolve('artifacts/npm-audit');
  for (const dir of ['artifacts', 'artifacts/npm-audit']) {
    try { mkdirSync(dir); } catch (error) { if (error.code !== 'EEXIST') throw error; }
    const stat = lstatSync(dir);
    if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Unsupported symbolic/non-directory audit artifact: ${dir}`);
  }
  const evidence = mkdtempSync(path.join(base, 'run-'));
  const git = spawnSync('git', ['-C', path.resolve(__dirname, '..'), 'rev-parse', 'HEAD'], { encoding: 'utf8' });
  const status = spawnSync('git', ['-C', path.resolve(__dirname, '..'), 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' });
  const decision = { sourceCommit: git.status === 0 ? git.stdout.trim() : null,
    sourceTreeDirty: status.status === 0 ? Boolean(status.stdout.trim()) : null,
    auditScriptSha256: sha256(readFileSync(__filename)),
    startedAt: new Date().toISOString(), expiresAt: BACKPORT_EXPIRY, attempts: [], exitCode: 1 };
  console.log(`Audit evidence: ${evidence}`);
  try {
    const report = await readAuditReport(evidence, decision);
    if ((process.env.CI === 'true' || process.env.GITHUB_ACTIONS === 'true') &&
        (!/^[a-f0-9]{40}$/.test(decision.sourceCommit ?? '') || decision.sourceTreeDirty === null)) {
      throw new Error('Audit source-commit provenance is missing or invalid in CI.');
    }
    decision.inputHashes = {};
    for (const [file, expected] of Object.entries(REVIEWED_INPUTS)) {
      const actual = sha256(readFileSync(checkedFile(file)));
      decision.inputHashes[file] = actual;
      if (actual !== expected) throw new Error(`Audit reviewed evidence mismatch: ${file}`);
    }
    const verification = spawnSync(process.execPath, [checkedFile('scripts/dependency-patches.js'), 'verify'],
      { encoding: 'utf8', timeout: 15000 });
    if (verification.status !== 0 || verification.error) {
      throw new Error(`Installed dependency patch verification failed: ${verification.stderr || verification.error?.message}`);
    }
    decision.patchVerification = 'passed';
    decision.frontendScope = frontendScope();
    if (decision.frontendScope.sha256 !== FRONTEND_SCOPE_SHA256) {
      throw new Error('Audit consumer scope changed; a fresh review is required.');
    }
    if (!Number.isFinite(Date.now()) || Date.now() >= Date.parse(BACKPORT_EXPIRY)) {
      throw new Error(`Temporary dependency backport policy expired at ${BACKPORT_EXPIRY}`);
    }
    const lockfile = JSON.parse(readFileSync('package-lock.json', 'utf8'));
    const blockers = findBlockingVulnerabilities(report, lockfile, AUDIT_LEVEL, VERIFIED_BACKPORTS);
    decision.blockers = blockers;
    decision.registryVulnerabilities = report.metadata?.vulnerabilities ?? null;
    decision.treatedAdvisories = [];
    for (const vulnerability of Object.values(report.vulnerabilities)) {
      for (const cause of Array.isArray(vulnerability?.via) ? vulnerability.via : []) {
        if (isRecord(cause) && isAllowedAdvisory(cause, vulnerability, lockfile, VERIFIED_BACKPORTS)) {
          decision.treatedAdvisories.push({ url: cause.url, package: vulnerability.name,
            nodes: vulnerability.nodes, treatment: BACKPORT_ADVISORIES[cause.url] ? 'verified-backport' : 'existing-allowance' });
        }
      }
    }

    if (blockers.length > 0) {
      console.error('Unapproved high or critical npm vulnerabilities:');
      for (const blocker of blockers) {
        console.error(
          `- ${blocker.name} (${blocker.severity}): ${blocker.nodes.join(', ')}`,
        );
      }
      return 1;
    }

    if (!Number.isFinite(Date.now()) || Date.now() >= Date.parse(BACKPORT_EXPIRY)) {
      throw new Error(`Temporary dependency backport policy expired at ${BACKPORT_EXPIRY}`);
    }
    console.log('Project policy accepted with verified temporary backports; registry findings are retained.');
    for (const { url } of decision.treatedAdvisories) {
      const allowance = BACKPORT_ADVISORIES[url] ?? ALLOWED_ADVISORIES[url];
      console.warn(
        `Project treatment: ${allowance.dependency}@${allowance.version} (${url}). ${allowance.reason}`,
      );
    }
    decision.exitCode = 0;
    return 0;
  } catch (error) {
    decision.error = error instanceof Error ? error.message : String(error);
    throw error;
  } finally {
    decision.completedAt = new Date().toISOString();
    writeFileSync(path.join(evidence, 'decision.json'), JSON.stringify(decision, null, 2) + '\n', { flag: 'wx' });
  }
}

if (require.main === module) {
  runAudit().then((exitCode) => {
    process.exitCode = exitCode;
  }).catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}

module.exports = {
  findBlockingVulnerabilities,
  isAllowedAdvisory,
  isAllowedVulnerability,
};
