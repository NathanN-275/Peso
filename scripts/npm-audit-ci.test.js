const assert = require('node:assert/strict');
const test = require('node:test');

const { findBlockingVulnerabilities } = require('./npm-audit-ci');

const allowedNode =
  'node_modules/glob/node_modules/brace-expansion';

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
