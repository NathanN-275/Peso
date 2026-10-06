const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');

const SCANNER_VERSION = '8.30.1';
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
// Approved by Nathan: docs/deployment/public-resource-id-treatment-proposal-20261005.md.
// Immutable occurrence pins, not a prefix/rule/file allowlist. Any byte change
// requires review; never reconstruct these pins from the current source.
const REVIEWED_OCCURRENCES = [
  { file: 'config/combined-web-release-binding.json', line: 7, startColumn: 5, endColumn: 47,
    fileSha256: 'd2c36edc9d6a72297fec9dce2ea4ff73459dd99f66b7d3f5d28d7ba908f0e822',
    lineSha256: '989652b57f02f72f851a492ef9a6ac494c797ef2a24c9df55a64c8fdb1ca3f35',
    redactedMatch: 'api_service_id": "REDACTED"' },
  { file: 'scripts/release-env.test.js', line: 214, startColumn: 6, endColumn: 47,
    fileSha256: 'ef2d8ba079e855743266032e54a7204141f273adcbe866884e731e4f5bc60fe4',
    lineSha256: '3057af47f29c1e45a9b0f25135916d359468fdaad7ea6d96721d3d51deebc36a',
    redactedMatch: "api_service_id: 'REDACTED'" },
];

function isReviewedOccurrence(finding, file, snapshot, version) {
  const reviewed = REVIEWED_OCCURRENCES.find(entry => entry.file === file);
  if (version !== SCANNER_VERSION || !reviewed || finding.RuleID !== 'generic-api-key' ||
      finding.StartLine !== reviewed.line || finding.EndLine !== reviewed.line ||
      finding.StartColumn !== reviewed.startColumn || finding.EndColumn !== reviewed.endColumn ||
      finding.Secret !== 'REDACTED' || finding.Match !== reviewed.redactedMatch ||
      !Array.isArray(finding.Tags) || finding.Tags.length > 0 || finding.SymlinkFile !== '') return false;
  const bytes = fs.readFileSync(path.join(snapshot, file));
  const line = bytes.toString('utf8').split('\n')[reviewed.line - 1];
  return sha256(bytes) === reviewed.fileSha256 && typeof line === 'string' && sha256(line) === reviewed.lineSha256;
}

// Scan committed bytes, never local dotenv files, dependencies or untracked notes.
// This supplements history scanning; it does not certify rotated credentials or purged refs.
function scanCommittedSource({ repo, sha, evidenceRoot, runScanner }) {
  if (!/^[a-f0-9]{40}$/.test(sha ?? '')) throw new Error('An exact source SHA is required.');
  function git(...args) {
    const result = spawnSync('git', ['-C', repo, ...args], { maxBuffer: 128 * 1024 * 1024 });
    if (result.status !== 0) throw new Error('Cannot read the selected source commit.');
    return result.stdout;
  }
  if (git('rev-parse', `${sha}^{commit}`).toString().trim() !== sha) throw new Error('Source is not a commit.');
  const sourceTree = git('rev-parse', `${sha}^{tree}`).toString().trim();
  const entries = git('ls-tree', '-r', '-z', '--long', sha).toString().split('\0').filter(Boolean);
  if (entries.length === 0) throw new Error('Source snapshot is empty.');
  const inventory = entries.map(entry => {
    const match = entry.match(/^(100644|100755) blob [a-f0-9]{40}\s+(\d+)\t(.+)$/s);
    if (!match) throw new Error('Source snapshot must contain only regular files.');
    return { bytes: Number(match[2]), file: match[3] };
  });
  const archive = git('archive', '--format=tar', sha);
  fs.mkdirSync(evidenceRoot, { recursive: true, mode: 0o700 });
  const directory = fs.mkdtempSync(path.join(evidenceRoot, 'run-'));
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-committed-source-'));
  const evidence = {
    schemaVersion: 2, sourceSha: sha, sourceTree, archiveSha256: sha256(archive),
    scriptSha256: sha256(fs.readFileSync(__filename)),
    inputFiles: inventory.length, inputBytes: inventory.reduce((n, entry) => n + entry.bytes, 0),
    scannedBytes: null, findingCount: null, scannerExitCode: null, outcome: 'error',
  };
  const policy = {
    schemaVersion: 1, sourceSha: sha, sourceTree, archiveSha256: evidence.archiveSha256,
    scriptSha256: evidence.scriptSha256, outcome: 'error', exitCode: 1,
    classifiedCount: 0, blockingCount: null, findings: [],
    authority: 'Nathan approved docs/deployment/public-resource-id-treatment-proposal-20261005.md',
    reviewedOccurrences: REVIEWED_OCCURRENCES.map(({ redactedMatch, ...entry }) => ({ rule: 'generic-api-key', ...entry })),
  };
  try {
    const snapshot = path.join(temporary, 'source');
    fs.mkdirSync(snapshot);
    const archivePath = path.join(temporary, 'source.tar');
    fs.writeFileSync(archivePath, archive);
    if (spawnSync('tar', ['-xf', archivePath, '-C', snapshot]).status !== 0) throw new Error('Archive extraction failed.');
    for (const entry of inventory) {
      const stat = fs.lstatSync(path.join(snapshot, entry.file));
      if (!stat.isFile() || stat.size !== entry.bytes) throw new Error('Archive coverage differs from the source tree.');
    }
    // Explicit defaults and empty ignore file: snapshot scanning must not inherit
    // local config, historical fingerprints, baselines or inline allow comments.
    const config = path.join(temporary, 'defaults.toml');
    const ignore = path.join(temporary, 'empty.ignore');
    fs.writeFileSync(config, '[extend]\nuseDefault = true\n');
    fs.writeFileSync(ignore, '');
    const env = { ...process.env, NO_COLOR: '1' };
    delete env.GITLEAKS_CONFIG;
    delete env.GITLEAKS_CONFIG_TOML;
    let scanner = runScanner;
    if (scanner) evidence.scannerVersion = 'test-double';
    else {
      const version = spawnSync('gitleaks', ['version'], { encoding: 'utf8', env });
      if (version.status !== 0 || version.stdout.trim() !== SCANNER_VERSION) throw new Error('Required scanner version is unavailable.');
      evidence.scannerVersion = version.stdout.trim();
      scanner = (args, options) => spawnSync('gitleaks', args, options);
    }
    const report = path.join(temporary, 'redacted-report.json');
    const args = ['dir', '--redact=100', '--no-banner', '--no-color', '--ignore-gitleaks-allow',
      '--config', config, '--gitleaks-ignore-path', ignore,
      '--report-format', 'json', '--report-path', report, snapshot];
    const result = scanner(args, { cwd: temporary, encoding: 'utf8', env, maxBuffer: 16 * 1024 * 1024 });
    evidence.scannerExitCode = result.status;
    evidence.scannedBytes = Number((result.stderr ?? '').match(/scanned ~(\d+) bytes\b/)?.[1] ?? 0);
    if (![0, 1].includes(result.status)) throw new Error('Scanner execution failed.');
    const reportBytes = fs.readFileSync(report);
    evidence.scannerReportSha256 = sha256(reportBytes);
    const findings = JSON.parse(reportBytes.toString('utf8'));
    if (!Array.isArray(findings)) throw new Error('Invalid scanner report.');
    evidence.findingCount = findings.length;
    // Do not retain Match, Secret, commits/messages or raw scanner output in CI artifacts.
    const sanitized = findings.map(finding => {
      if (!finding || typeof finding.RuleID !== 'string' || !finding.RuleID ||
          typeof finding.File !== 'string' || !Number.isSafeInteger(finding.StartLine) || finding.StartLine <= 0) {
        throw new Error('Invalid finding metadata.');
      }
      const file = path.isAbsolute(finding.File) ? path.relative(snapshot, finding.File) : finding.File;
      if (!inventory.some(entry => entry.file === file)) throw new Error('Finding outside the committed snapshot.');
      return { rule: finding.RuleID, file, startLine: finding.StartLine,
        endLine: Number.isSafeInteger(finding.EndLine) ? finding.EndLine : null,
        startColumn: Number.isSafeInteger(finding.StartColumn) ? finding.StartColumn : null,
        endColumn: Number.isSafeInteger(finding.EndColumn) ? finding.EndColumn : null };
    });
    const findingsBytes = JSON.stringify(sanitized, null, 2) + '\n';
    fs.writeFileSync(path.join(directory, 'findings.json'), findingsBytes);
    evidence.findingsSha256 = sha256(findingsBytes);
    if (!Number.isSafeInteger(evidence.scannedBytes) || evidence.scannedBytes <= 0) {
      throw new Error('Scanner returned invalid byte coverage.');
    }
    if ((result.status === 0) !== (findings.length === 0)) throw new Error('Scanner result contradicts its report.');
    evidence.outcome = findings.length ? 'findings' : 'clean';
    const classifiedOccurrences = new Set();
    policy.findings = sanitized.map((metadata, index) => {
      const occurrence = `${metadata.file}:${metadata.startLine}`;
      const reviewed = !classifiedOccurrences.has(occurrence) &&
        isReviewedOccurrence(findings[index], metadata.file, snapshot, evidence.scannerVersion);
      if (reviewed) classifiedOccurrences.add(occurrence);
      return { ...metadata, classification: reviewed ? 'reviewed-public-resource-id' : 'blocking' };
    });
    policy.classifiedCount = policy.findings.filter(f => f.classification === 'reviewed-public-resource-id').length;
    policy.blockingCount = policy.findings.length - policy.classifiedCount;
    policy.outcome = policy.blockingCount ? 'blocked' : findings.length
      ? 'accepted-with-reviewed-nonsecret-findings' : 'clean';
    policy.exitCode = policy.blockingCount ? 1 : 0;
  } catch {
    // Errors and malformed outputs never become successful empty scans. No raw
    // provider/scanner content is copied into an error string or console output.
    policy.outcome = 'error';
    policy.exitCode = 1;
  } finally {
    Object.assign(policy, { scannerVersion: evidence.scannerVersion ?? null,
      scannerExitCode: evidence.scannerExitCode, rawFindingCount: evidence.findingCount,
      scannedBytes: evidence.scannedBytes, scannerReportSha256: evidence.scannerReportSha256 ?? null,
      findingsSha256: evidence.findingsSha256 ?? null });
    const policyBytes = JSON.stringify(policy, null, 2) + '\n';
    fs.writeFileSync(path.join(directory, 'policy.json'), policyBytes);
    evidence.policySha256 = sha256(policyBytes);
    evidence.policyOutcome = policy.outcome;
    evidence.policyExitCode = policy.exitCode;
    fs.writeFileSync(path.join(directory, 'coverage.json'), JSON.stringify(evidence, null, 2) + '\n');
    fs.rmSync(temporary, { recursive: true, force: true });
  }
  return { exitCode: policy.exitCode, directory, evidence };
}

if (require.main === module) {
  try {
    const repo = process.cwd();
    const head = spawnSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).stdout.trim();
    const sha = process.argv[2] ?? process.env.GITHUB_SHA ?? head;
    if (process.env.CI && sha !== head) throw new Error('CI checkout does not match the source SHA.');
    const result = scanCommittedSource({ repo, sha,
      evidenceRoot: process.argv[3] ?? path.join(repo, 'artifacts', 'source-secret-scan') });
    console.log(JSON.stringify({ sourceSha: sha, outcome: result.evidence.outcome,
      rawScannerExitCode: result.evidence.scannerExitCode,
      policyOutcome: result.evidence.policyOutcome, policyExitCode: result.exitCode,
      scannedBytes: result.evidence.scannedBytes, findings: result.evidence.findingCount, evidence: result.directory }));
    process.exitCode = result.exitCode;
  } catch {
    console.error('Committed-source secret scan failed before producing accepted coverage.');
    process.exitCode = 1;
  }
}

module.exports = { scanCommittedSource };
