const assert = require('node:assert/strict');
const test = require('node:test');
const { mkdtempSync, writeFileSync, readFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const { findBlockingVulnerabilities } = require('./npm-audit-ci');

const allowedNode =
  'node_modules/glob/node_modules/brace-expansion';
const allowedImageSizeNode = 'node_modules/image-size';
const imageSizeAdvisories = [
  'https://github.com/advisories/GHSA-w3rx-r6r6-pgpr',
  'https://github.com/advisories/GHSA-5p2g-fcmc-qvqq',
];

function createLockfile(version = '1.1.16', node = allowedNode) {
  return {
    packages: {
      [node]: { version },
    },
  };
}

function createReport({
  advisoryUrl = 'https://github.com/advisories/GHSA-mh99-v99m-4gvg',
  node = allowedNode,
  severity = 'high',
} = {}) {
  return {
    vulnerabilities: {
      'brace-expansion': {
        name: 'brace-expansion',
        severity,
        nodes: [node],
        via: [
          {
            name: 'brace-expansion',
            severity,
            url: advisoryUrl,
          },
        ],
      },
      minimatch: {
        name: 'minimatch',
        severity,
        nodes: ['node_modules/react-native/node_modules/minimatch'],
        via: ['brace-expansion'],
      },
      'react-native': {
        name: 'react-native',
        severity,
        nodes: ['node_modules/react-native'],
        via: ['minimatch'],
      },
    },
  };
}

function createImageSizeReport({
  advisoryUrls = imageSizeAdvisories,
  node = allowedImageSizeNode,
} = {}) {
  return {
    vulnerabilities: {
      'image-size': {
        name: 'image-size',
        severity: 'high',
        nodes: [node],
        via: advisoryUrls.map((url) => ({
          name: 'image-size',
          severity: 'high',
          url,
        })),
      },
      metro: {
        name: 'metro',
        severity: 'high',
        nodes: ['node_modules/metro'],
        via: ['image-size', 'metro-config', 'metro-transform-worker'],
      },
      'metro-config': {
        name: 'metro-config',
        severity: 'high',
        nodes: ['node_modules/metro-config'],
        via: ['metro'],
      },
      'metro-transform-worker': {
        name: 'metro-transform-worker',
        severity: 'high',
        nodes: ['node_modules/metro-transform-worker'],
        via: ['metro'],
      },
      expo: {
        name: 'expo',
        severity: 'high',
        nodes: ['node_modules/expo'],
        via: ['metro'],
      },
    },
  };
}

test('allows the known brace-expansion advisory through verified build-tool paths', () => {
  assert.deepEqual(
    findBlockingVulnerabilities(createReport(), createLockfile()),
    [],
  );
});

test('blocks advisories that are not explicitly allowed', () => {
  const blockers = findBlockingVulnerabilities(
    createReport({
      advisoryUrl: 'https://github.com/advisories/GHSA-unknown',
    }),
    createLockfile(),
  );

  assert.deepEqual(
    blockers.map(({ name }) => name),
    ['brace-expansion', 'minimatch', 'react-native'],
  );
});

test('blocks the allowed advisory at an unexpected dependency path', () => {
  const unexpectedNode = 'node_modules/application-runtime/brace-expansion';
  const blockers = findBlockingVulnerabilities(
    createReport({ node: unexpectedNode }),
    createLockfile('1.1.16', unexpectedNode),
  );

  assert.equal(blockers.length, 3);
});

test('blocks the allowed advisory when the installed version changes', () => {
  const blockers = findBlockingVulnerabilities(
    createReport(),
    createLockfile('1.1.15'),
  );

  assert.equal(blockers.length, 3);
});

test('ignores moderate findings at the configured high audit level', () => {
  const report = createReport({
    advisoryUrl: 'https://github.com/advisories/GHSA-unknown',
    severity: 'moderate',
  });

  assert.deepEqual(
    findBlockingVulnerabilities(report, createLockfile()),
    [],
  );
});

test('ignores moderate side chains attached to an allowed high-severity chain', () => {
  const report = createReport();
  report.vulnerabilities.uuid = {
    name: 'uuid',
    severity: 'moderate',
    nodes: ['node_modules/uuid'],
    via: [
      {
        name: 'uuid',
        severity: 'moderate',
        url: 'https://github.com/advisories/GHSA-moderate',
      },
    ],
  };
  report.vulnerabilities['react-native'].via.push('uuid');

  assert.deepEqual(
    findBlockingVulnerabilities(report, createLockfile()),
    [],
  );
});

test('fails closed when npm returns an unknown advisory severity', () => {
  const report = createReport();
  report.vulnerabilities['brace-expansion'].via.push({
    name: 'brace-expansion',
    url: 'https://github.com/advisories/GHSA-unknown',
  });

  const blockers = findBlockingVulnerabilities(report, createLockfile());

  assert.equal(blockers.length, 3);
});

test('allows both unpatched image-size advisories only through Metro build tooling', () => {
  const lockfile = {
    packages: {
      [allowedImageSizeNode]: { version: '1.2.1' },
    },
  };

  assert.deepEqual(
    findBlockingVulnerabilities(createImageSizeReport(), lockfile),
    [],
  );
});

test('blocks image-size when an advisory is not explicitly allowed', () => {
  const lockfile = {
    packages: {
      [allowedImageSizeNode]: { version: '1.2.1' },
    },
  };
  const blockers = findBlockingVulnerabilities(
    createImageSizeReport({
      advisoryUrls: [...imageSizeAdvisories, 'https://github.com/advisories/GHSA-unknown'],
    }),
    lockfile,
  );

  assert.deepEqual(
    blockers.map(({ name }) => name),
    ['image-size', 'metro', 'metro-config', 'metro-transform-worker', 'expo'],
  );
});

test('blocks image-size when the installed version changes', () => {
  const lockfile = {
    packages: {
      [allowedImageSizeNode]: { version: '1.2.0' },
    },
  };

  assert.equal(
    findBlockingVulnerabilities(createImageSizeReport(), lockfile).length,
    5,
  );
});

test('blocks high-severity dependency cycles with no concrete advisory', () => {
  const report = {
    vulnerabilities: {
      metro: {
        name: 'metro',
        severity: 'high',
        nodes: ['node_modules/metro'],
        via: ['metro-config'],
      },
      'metro-config': {
        name: 'metro-config',
        severity: 'high',
        nodes: ['node_modules/metro-config'],
        via: ['metro'],
      },
    },
  };

  assert.deepEqual(
    findBlockingVulnerabilities(report, { packages: {} }).map(({ name }) => name),
    ['metro', 'metro-config'],
  );
});

// Exercise the CLI boundary with the same error shape npm emits for a 503.
// No network is involved; each fake npm invocation consumes one response.
function runAuditCli(t, responses) {
  const directory = mkdtempSync(path.join(tmpdir(), 'peso-audit-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  writeFileSync(path.join(directory, 'package-lock.json'), JSON.stringify(createLockfile()));
  writeFileSync(path.join(directory, 'responses.json'), JSON.stringify(responses));
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
  const result = spawnSync(process.execPath, [path.join(__dirname, 'npm-audit-ci.js')], {
    cwd: directory,
    env: { ...process.env, PATH: `${directory}${path.delimiter}${process.env.PATH}` },
    encoding: 'utf8',
    timeout: 15000,
  });
  assert.ifError(result.error);
  return { ...result, calls: Number(readFileSync(path.join(directory, 'calls'), 'utf8')) };
}

const unavailableAudit = {
  stdout: JSON.stringify({ error: { code: 'E503', summary: 'Service Unavailable' } }),
  stderr: 'npm warn audit 503 Service Unavailable',
  status: 1,
};
const cleanAudit = {
  stdout: JSON.stringify({ auditReportVersion: 2, vulnerabilities: {} }),
  status: 0,
};

test('audit CLI retries a transient registry failure and evaluates the recovered report', (t) => {
  const result = runAuditCli(t, [unavailableAudit, cleanAudit]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.calls, 2);
  assert.match(result.stdout, /Audit passed/);
});

test('audit CLI fails closed after bounded registry retries', (t) => {
  const result = runAuditCli(t, [unavailableAudit]);
  assert.equal(result.status, 1);
  assert.equal(result.calls, 3);
  assert.match(result.stderr, /usable vulnerability report/);
});

test('audit CLI does not retry or accept malformed reports', (t) => {
  const result = runAuditCli(t, [{ stdout: '<html>unavailable</html>', status: 1 }, cleanAudit]);
  assert.equal(result.status, 1);
  assert.equal(result.calls, 1);
  assert.match(result.stderr, /valid JSON/);
});

test('audit CLI blocks real vulnerabilities even after registry recovery', (t) => {
  const report = createReport({ advisoryUrl: 'https://github.com/advisories/GHSA-unknown' });
  const result = runAuditCli(t, [unavailableAudit, {
    stdout: JSON.stringify({ auditReportVersion: 2, ...report }),
    status: 1,
  }, cleanAudit]);
  assert.equal(result.status, 1);
  assert.equal(result.calls, 2);
  assert.match(result.stderr, /Unapproved high or critical npm vulnerabilities/);
});

test('audit CLI does not retry non-transient npm errors', (t) => {
  const result = runAuditCli(t, [{
    stdout: JSON.stringify({ error: { code: 'E401', summary: 'Unauthorized' } }),
    status: 1,
  }, cleanAudit]);
  assert.equal(result.status, 1);
  assert.equal(result.calls, 1);
});

test('audit CLI rejects errors attached to otherwise usable reports', (t) => {
  const result = runAuditCli(t, [{
    stdout: JSON.stringify({
      auditReportVersion: 2,
      vulnerabilities: {},
      error: { code: 'E503', summary: 'Incomplete audit' },
    }),
    status: 1,
  }]);
  assert.equal(result.status, 1);
  assert.doesNotMatch(result.stdout, /Audit passed/);
});
