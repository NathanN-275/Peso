const { readFileSync, mkdirSync, mkdtempSync, writeFileSync, lstatSync } = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');

const AUDIT_LEVEL = 'high';
// Exact-policy treatment: activation is restricted to the reviewed main-branch push.
const PICOMATCH_REVIEW_STATUS = 'approved-by-nathan';
const PICOMATCH_REVIEW_EXPIRES = '2026-11-20T00:00:00Z';
const PICOMATCH_BLOCKING_RECORDS_SHA256 = '54b6c3922391bb78794c5242b184cae77c6121464878a8149ab0dce8c13ab389';
const REVIEWED_INPUTS = {
  'patches/dependencies/picomatch-4.0.4-nested-repetition.patch': '47461054457152aa69556acfe3cc64374382a472783ccd6380268e1d95675b21',
  'patches/dependencies/picomatch-2.3.2-nested-repetition.patch': '5df5dcccbb2c572f1de8876a33f90b2938e1dc753742fe42af46b5d50778d094',
  'scripts/dependency-patches.js': '93de8dbd9dff796be4a46f0f4b769a8aa62a4395acfeedf9df6a2f7cc8dd8534',
  'package-lock.json': '2ee6c3ef9744c9b0668119d147022037cafef21d084044192d8223fd1f4fe0c9',
  'patches/dependencies/manifest.json': '21a3e08d71f28e0c1156ea5ba5ffed0f375fbb492d5a99da8f600f1e0a727262',
  'patches/dependencies/braces-3.0.3.patch': 'e07abe26dbd330daea0e448ca1382327322dd5eccc08c5dd1a9b9f7bf5a6d699',
  'patches/dependencies/metro-0.84.4-image-size-2.patch': 'a2d3f781d7779ccba3aa961500fbb7c80724e10793dd9e7358fbe5be1f68cd25',
};
const SEVERITY_RANK = {
  info: 0,
  low: 1,
  moderate: 2,
  high: 3,
  critical: 4,
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

function validGraph(name, vulnerabilities) {
  const graph = new Map();
  const pending = [name];
  while (pending.length) {
    const current = pending.pop();
    if (graph.has(current)) continue;
    if (!validCauses(current, vulnerabilities)) return false;
    const via = vulnerabilities[current].via;
    const children = via.filter(c => typeof c === 'string');
    graph.set(current, { children, grounded: via.some(c => typeof c !== 'string') });
    pending.push(...children);
  }
  // A cycle may propagate a concrete advisory, but cannot invent one or borrow
  // a sibling's evidence for a separate advisory-free branch.
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

function findBlockingVulnerabilities(report, lockfile, auditLevel = AUDIT_LEVEL) {
  if (!isRecord(report) || !isRecord(report.vulnerabilities) ||
      !isRecord(lockfile?.packages) || !knownSeverity(auditLevel)) {
    throw new Error('Malformed audit report or lockfile');
  }
  const vulnerabilities = report.vulnerabilities;
  const minimumRank = SEVERITY_RANK[auditLevel];
  return Object.entries(vulnerabilities)
    .filter(([name, vulnerability]) => !validGraph(name, vulnerabilities) ||
      SEVERITY_RANK[vulnerability.severity] >= minimumRank)
    .map(([name, vulnerability]) => ({
      name,
      severity: vulnerability?.severity ?? 'unknown',
      nodes: Array.isArray(vulnerability?.nodes) ? vulnerability.nodes : [],
    }));
}

// Private to the CLI: callers of the exported strict classifier cannot mint treatment.
function reviewPicomatchFindings(report, strictBlockers, decision) {
  const unchanged = { blockers: strictBlockers, treated: [] };
  const now = Date.now();
  const env = process.env;
  if (PICOMATCH_REVIEW_STATUS !== 'approved-by-nathan' || !Number.isFinite(now) ||
      now >= Date.parse(PICOMATCH_REVIEW_EXPIRES) || decision.sourceTreeDirty !== false ||
      !/^[a-f0-9]{40}$/.test(decision.sourceCommit ?? '') || decision.patchVerification !== 'passed' ||
      env.GITHUB_ACTIONS !== 'true' || env.GITHUB_REPOSITORY !== 'NathanN-275/Peso' ||
      env.GITHUB_WORKFLOW !== 'Security Checks' || env.GITHUB_EVENT_NAME !== 'push' ||
      env.GITHUB_REF !== 'refs/heads/main' || env.GITHUB_SHA !== decision.sourceCommit) return unchanged;
  const vulnerabilities = report.vulnerabilities;
  const leaf = vulnerabilities.picomatch;
  const expectedPaths = [
    'node_modules/anymatch/node_modules/picomatch',
    'node_modules/jest-util/node_modules/picomatch',
    'node_modules/micromatch/node_modules/picomatch',
    'node_modules/picomatch',
    'node_modules/readdirp/node_modules/picomatch',
  ];
  if (!leaf || !validGraph('picomatch', vulnerabilities) || leaf.severity !== 'high' ||
      JSON.stringify([...leaf.nodes].sort()) !== JSON.stringify(expectedPaths) || leaf.via.length !== 1 ||
      !isRecord(leaf.via[0])) return unchanged;
  // Pin every blocking package, path, severity and cause, including observed cycles.
  // npm's upgrade suggestions, reverse edges and derived package ranges can vary.
  if (strictBlockers.some(({ name, severity }) => severity !== 'high' ||
      !validGraph(name, vulnerabilities))) return unchanged;
  const records = Object.fromEntries(strictBlockers.map(({ name }) => {
    const { severity, nodes, via } = vulnerabilities[name];
    return [name, { name, severity, nodes: [...nodes].sort(), via }];
  }));
  const canonical = JSON.stringify(records, (key, value) => isRecord(value)
    ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : value);
  if (sha256(canonical) !== PICOMATCH_BLOCKING_RECORDS_SHA256) return unchanged;
  return { blockers: [], treated: strictBlockers };
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
    startedAt: new Date().toISOString(), auditLevel: AUDIT_LEVEL, attempts: [], exitCode: 1 };
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
    const lockfile = JSON.parse(readFileSync('package-lock.json', 'utf8'));
    const strictBlockers = findBlockingVulnerabilities(report, lockfile);
    const { blockers, treated } = reviewPicomatchFindings(report, strictBlockers, decision);
    decision.strictBlockers = strictBlockers;
    decision.blockers = blockers;
    decision.registryVulnerabilities = report.metadata?.vulnerabilities ?? null;
    if (treated.length) decision.projectTreatment = {
      authority: PICOMATCH_REVIEW_STATUS, expiresAt: PICOMATCH_REVIEW_EXPIRES,
      blockingRecordsSha256: PICOMATCH_BLOCKING_RECORDS_SHA256, treated,
    };

    if (blockers.length > 0) {
      console.error('Unapproved high or critical npm vulnerabilities:');
      for (const blocker of blockers) {
        console.error(
          `- ${blocker.name} (${blocker.severity}): ${blocker.nodes.join(', ')}`,
        );
      }
      return 1;
    }

    console.log(treated.length
      ? 'Root dependency audit accepted with temporary project treatment; registry HIGH findings remain visible.'
      : 'Root dependency audit accepted: no HIGH or CRITICAL findings; lower findings retained.');
    decision.exitCode = 0;
    return 0;
  } catch (error) {
    decision.error = error instanceof Error ? error.message : String(error);
    throw error;
  } finally {
    decision.completedAt = new Date().toISOString();
    const bytes = JSON.stringify(decision, null, 2) + '\n';
    writeFileSync(path.join(evidence, 'decision.json'), bytes, { flag: 'wx' });
    writeFileSync(path.join(evidence, 'decision.sha256'), sha256(bytes) + '  decision.json\n', { flag: 'wx' });
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
};
