const { readFileSync } = require('node:fs');
const { spawnSync } = require('node:child_process');

const AUDIT_LEVEL = 'high';
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

function isAllowedAdvisory(advisory, vulnerability, lockfile) {
  const allowance = ALLOWED_ADVISORIES[advisory.url];
  if (!allowance || vulnerability.name !== allowance.dependency) {
    return false;
  }

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

function evaluateAllowedVulnerability(
  name,
  vulnerabilities,
  lockfile,
  auditLevel,
  visiting,
  evidence,
) {
  if (visiting.has(name)) {
    return true;
  }

  const vulnerability = vulnerabilities[name];
  if (!vulnerability || !Array.isArray(vulnerability.via) || vulnerability.via.length === 0) {
    return false;
  }

  const nextVisiting = new Set(visiting);
  nextVisiting.add(name);
  const minimumRank = SEVERITY_RANK[auditLevel];
  const relevantCauses = vulnerability.via.filter((cause) => {
    const severity =
      typeof cause === 'string'
        ? vulnerabilities[cause]?.severity
        : cause.severity;
    const severityRank = SEVERITY_RANK[severity];
    return severityRank === undefined || severityRank >= minimumRank;
  });

  return relevantCauses.length > 0 && relevantCauses.every((cause) =>
    typeof cause === 'string'
      ? evaluateAllowedVulnerability(
          cause,
          vulnerabilities,
          lockfile,
          auditLevel,
          nextVisiting,
          evidence,
        )
      : (() => {
          const allowed = isAllowedAdvisory(cause, vulnerability, lockfile);
          if (allowed) {
            evidence.allowedAdvisories += 1;
          }
          return allowed;
        })(),
  );
}

function isAllowedVulnerability(
  name,
  vulnerabilities,
  lockfile,
  auditLevel = AUDIT_LEVEL,
  visiting = new Set(),
) {
  const evidence = { allowedAdvisories: 0 };
  return (
    evaluateAllowedVulnerability(
      name,
      vulnerabilities,
      lockfile,
      auditLevel,
      visiting,
      evidence,
    ) && evidence.allowedAdvisories > 0
  );
}

function findBlockingVulnerabilities(report, lockfile, auditLevel = AUDIT_LEVEL) {
  const vulnerabilities = report.vulnerabilities ?? {};
  const minimumRank = SEVERITY_RANK[auditLevel];

  return Object.entries(vulnerabilities)
    .filter(([, vulnerability]) => {
      const severityRank = SEVERITY_RANK[vulnerability.severity];
      return severityRank === undefined || severityRank >= minimumRank;
    })
    .filter(
      ([name]) =>
        !isAllowedVulnerability(name, vulnerabilities, lockfile, auditLevel),
    )
    .map(([name, vulnerability]) => ({
      name,
      severity: vulnerability.severity,
      nodes: vulnerability.nodes ?? [],
    }));
}

function runAudit() {
  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const result = spawnSync(
    npmCommand,
    ['audit', '--json', `--audit-level=${AUDIT_LEVEL}`],
    { encoding: 'utf8' },
  );

  if (result.error) {
    throw result.error;
  }

  let report;
  try {
    report = JSON.parse(result.stdout);
  } catch {
    throw new Error(
      `npm audit did not return valid JSON.\n${result.stderr || result.stdout}`,
    );
  }

  if (
    report.auditReportVersion !== 2 ||
    typeof report.vulnerabilities !== 'object' ||
    report.vulnerabilities === null
  ) {
    throw new Error(
      `npm audit did not return a usable vulnerability report.\n${result.stderr || result.stdout}`,
    );
  }

  const lockfile = JSON.parse(readFileSync('package-lock.json', 'utf8'));
  const blockers = findBlockingVulnerabilities(report, lockfile);

  if (blockers.length > 0) {
    console.error('Unapproved high or critical npm vulnerabilities:');
    for (const blocker of blockers) {
      console.error(
        `- ${blocker.name} (${blocker.severity}): ${blocker.nodes.join(', ')}`,
      );
    }
    return 1;
  }

  console.log('Audit passed: no unapproved high or critical vulnerabilities.');
  for (const [url, allowance] of Object.entries(ALLOWED_ADVISORIES)) {
    console.warn(
      `Allowed temporarily: ${allowance.dependency}@${allowance.version} (${url}). ${allowance.reason}`,
    );
  }
  return 0;
}

if (require.main === module) {
  try {
    process.exitCode = runAudit();
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}

module.exports = {
  findBlockingVulnerabilities,
  isAllowedAdvisory,
  isAllowedVulnerability,
};
