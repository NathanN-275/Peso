const assert = require('node:assert/strict');
const test = require('node:test');
const { mkdtempSync, writeFileSync, readFileSync, rmSync, readdirSync, mkdirSync, copyFileSync, cpSync, symlinkSync, existsSync } = require('node:fs');
const { createHash } = require('node:crypto');
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

test('blocks a parent whose allowed leaf is a sibling of an advisory-free cycle', () => {
  const report = createReport();
  const node = (name, via) => ({ name, severity: 'high', nodes: [`node_modules/${name}`], via });
  report.vulnerabilities['react-native'].via.push('cycle-a');
  report.vulnerabilities['cycle-a'] = node('cycle-a', ['cycle-b']);
  report.vulnerabilities['cycle-b'] = node('cycle-b', ['cycle-a']);
  assert.deepEqual(findBlockingVulnerabilities(report, createLockfile()).map(v => v.name),
    ['react-native', 'cycle-a', 'cycle-b']);
});

test('blocks malformed identities and causes even beside an allowed advisory', () => {
  for (const change of [
    v => { v.name = 'another-package'; },
    v => { v.nodes = []; },
    v => { v.nodes = ['node_modules/another-package']; },
    v => { v.nodes = ['node_modules/../react-native']; },
    v => { v.via.push(null); },
    v => { v.via.push({ severity: 'moderate' }); },
    v => { v.via.push('missing-package'); },
  ]) {
    const report = createReport();
    change(report.vulnerabilities['react-native']);
    assert.ok(findBlockingVulnerabilities(report, createLockfile()).some(v => v.name === 'react-native'));
  }
});

test('rejects malformed audit report containers rather than treating them as clean', () => {
  for (const report of [{}, { vulnerabilities: [] }, { vulnerabilities: null }]) {
    assert.throws(() => findBlockingVulnerabilities(report, createLockfile()), /Malformed audit report/);
  }
});

test('blocks malformed or severity-masked side chains below the normal audit threshold', () => {
  for (const via of [['missing'], [{ name: 'uuid', severity: 'critical', url: 'https://github.com/advisories/GHSA-new' }]]) {
    const report = { vulnerabilities: { uuid: { name: 'uuid', severity: 'moderate', nodes: ['node_modules/uuid'], via } } };
    assert.deepEqual(findBlockingVulnerabilities(report, createLockfile()).map(v => v.name), ['uuid']);
  }
});

// Exercise the CLI boundary with the same error shape npm emits for a 503.
// No network is involved; each fake npm invocation consumes one response.
function runAuditCli(t, responses, prepare = () => {}, now = '2026-10-05T20:00:00Z') {
  const directory = mkdtempSync(path.join(tmpdir(), 'peso-audit-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const root = path.resolve(__dirname, '..');
  copyFileSync(path.join(root, 'package-lock.json'), path.join(directory, 'package-lock.json'));
  mkdirSync(path.join(directory, 'scripts'));
  copyFileSync(path.join(__dirname, 'dependency-patches.js'), path.join(directory, 'scripts/dependency-patches.js'));
  cpSync(path.join(root, 'patches'), path.join(directory, 'patches'), { recursive: true });
  for (const name of ['braces', 'node-forge']) {
    cpSync(path.join(root, 'node_modules', name), path.join(directory, 'node_modules', name), { recursive: true });
  }
  for (const file of [
    'node_modules/@expo/code-signing-certificates/build/main.js',
    'node_modules/expo/node_modules/@expo/cli/build/src/run/ios/codeSigning/Security.js',
    'node_modules/micromatch/index.js',
  ]) {
    mkdirSync(path.dirname(path.join(directory, file)), { recursive: true });
    copyFileSync(path.join(root, file), path.join(directory, file));
  }
  // Copy public frontend source/config fixtures only, never environment files,
  // generated bundles, media, or dependency trees.
  for (const entry of ['src', 'lib', 'web', 'dashboard', 'context', 'assets', 'app.config.js', 'metro.config.js',
    'babel.config.js', 'tailwind.config.js', 'postcss.config.js', 'index.ts', 'package.json', 'app.json', 'netlify.toml',
    'scripts/build-web.js', 'scripts/netlify-build.js', 'scripts/release-env.js', 'scripts/release-verify.js',
    'scripts/verify-marketing-build.js', 'scripts/web-build-budget.js',
    ...readdirSync(root).filter(f => /^App(?:\.[^.]+)?\.[cm]?[jt]sx?$/.test(f))]) {
    if (!existsSync(path.join(root, entry))) continue;
    cpSync(path.join(root, entry), path.join(directory, entry), { recursive: true, filter: filename => {
      const parts = path.relative(root, filename).split(path.sep);
      if (parts.some(p => p.startsWith('.') || ['node_modules', 'dist'].includes(p))) return false;
      return require('node:fs').lstatSync(filename).isDirectory() ||
        /\.(?:[cm]?js|jsx|[cm]?ts|tsx|json|astro|html|vue|svelte|mdx|toml)$/.test(filename);
    } });
  }
  // Time is an external boundary, frozen only in this subprocess fixture.
  writeFileSync(path.join(directory, 'clock.cjs'), `const RealDate = Date;
global.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : [${JSON.stringify(now)}])); }
  static now() { return new RealDate(${JSON.stringify(now)}).getTime(); }
};`);
  writeFileSync(path.join(directory, 'responses.json'), JSON.stringify(responses));
  // Git is an external metadata boundary; model an isolated CI checkout,
  // without creating a real repository or asserting installed patch status.
  writeFileSync(path.join(directory, 'git'), `#!${process.execPath}
if (process.argv.includes('rev-parse')) console.log('ca1b9cea7296d7baba4313b07b7547d20afdec25');
`, { mode: 0o755 });
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
  prepare(directory);
  const result = spawnSync(process.execPath, ['--require', path.join(directory, 'clock.cjs'), path.join(__dirname, 'npm-audit-ci.js')], {
    cwd: directory,
    env: { ...process.env, CI: 'true', PATH: `${directory}${path.delimiter}${process.env.PATH}` },
    encoding: 'utf8',
    timeout: 15000,
  });
  assert.ifError(result.error);
  return { ...result, directory, calls: existsSync(path.join(directory, 'calls')) ?
    Number(readFileSync(path.join(directory, 'calls'), 'utf8')) : 0 };
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

function backportAudit() {
  const leaf = (name, source, id, version) => ({
    name, severity: 'high', nodes: [`node_modules/${name}`],
    via: [{ source, name, dependency: name, severity: 'high', range: `<=${version}`,
      url: `https://github.com/advisories/${id}` }],
  });
  return { auditReportVersion: 2, vulnerabilities: {
    braces: leaf('braces', 1240992, 'GHSA-vfj7-8cjw-p6xm', '3.0.3'),
    'node-forge': leaf('node-forge', 1240912, 'GHSA-86w9-cpqp-85rv', '1.4.0'),
    expo: { name: 'expo', severity: 'high', nodes: ['node_modules/expo'], via: ['braces', 'node-forge'] },
  } };
}

test('audit CLI accepts only reviewed backport leaves and labels project-policy acceptance', t => {
  const result = runAuditCli(t, [{ stdout: JSON.stringify(backportAudit()), status: 1 }]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Project policy accepted with verified temporary backports/);
  assert.doesNotMatch(result.stdout, /Audit passed|clean registry|zero HIGH/);
});

test('audit CLI blocks a new frontend Forge consumer pending scope review', t => {
  const result = runAuditCli(t, [{ stdout: JSON.stringify(backportAudit()), status: 1 }], d => {
    mkdirSync(path.join(d, 'src'), { recursive: true });
    writeFileSync(path.join(d, 'src/new-consumer.ts'), "import forge from 'node-forge/dist/forge.min.js';\n");
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /consumer scope/);
});

test('audit CLI freezes root app entrypoints and newly introduced TypeScript module variants', t => {
  for (const file of ['App.web.tsx', 'src/new-consumer.mts']) {
    const result = runAuditCli(t, [{ stdout: JSON.stringify(backportAudit()), status: 1 }], d => {
      writeFileSync(path.join(d, file), "import forge from 'node-forge/dist/forge.min.js';\n");
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /consumer scope/);
  }
});

test('audit CLI blocks a changed export entrypoint pending artifact-path review', t => {
  const result = runAuditCli(t, [{ stdout: JSON.stringify(backportAudit()), status: 1 }], d => {
    writeFileSync(path.join(d, 'scripts/build-web.js'), "require('node-forge/dist/forge.min.js');\n");
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /consumer scope/);
});

test('audit CLI rejects altered checked consumer files', t => {
  const result = runAuditCli(t, [{ stdout: JSON.stringify(backportAudit()), status: 1 }], d => {
    writeFileSync(path.join(d, 'node_modules/@expo/code-signing-certificates/build/main.js'),
      "module.exports = require('node-forge/dist/forge.min.js');\n");
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /reviewed evidence mismatch/);
});

test('audit CLI rejects old, missing, and extra installed package copies', t => {
  for (const change of [
    d => {
      const file = path.join(d, 'node_modules/node-forge/lib/rsa.js');
      const previous = readFileSync(file, 'utf8')
        .replace('          // ASN.1 NULL parameters must also be empty, not unchecked bytes.\n', '')
        .replace("(('parameters' in capture) ? 2 : 1) ||\n            ('parameters' in capture && capture.parameters !== '')) {",
          "(('parameters' in capture) ? 2 : 1)) {");
      assert.equal(createHash('sha256').update(previous).digest('hex'),
        'acc22e5d36e27832c34e02dd3933aad7977d45b047eead5016520735efedc9c5');
      writeFileSync(file, previous);
    },
    d => rmSync(path.join(d, 'node_modules/braces/lib/parse.js')),
    d => cpSync(path.join(d, 'node_modules/node-forge'),
      path.join(d, 'node_modules/example/node_modules/node-forge'), { recursive: true }),
  ]) {
    const result = runAuditCli(t, [{ stdout: JSON.stringify(backportAudit()), status: 1 }], change);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /patch verification failed/);
  }
});

test('public evaluator cannot enable backport treatment with a caller assertion', () => {
  const report = backportAudit();
  const lock = JSON.parse(readFileSync(path.join(__dirname, '../package-lock.json')));
  for (const assertion of [undefined, true, { verified: true }, Symbol('verified temporary backports')]) {
    assert.deepEqual(findBlockingVulnerabilities(report, lock, 'high', assertion).map(v => v.name),
      ['braces', 'node-forge', 'expo']);
  }
});

test('audit CLI blocks changed advisory metadata and new causes alongside a reviewed leaf', t => {
  for (const change of [
    c => { c.source = 1240913; }, c => { c.name = 'another-package'; },
    c => { c.dependency = 'another-package'; }, c => { c.range = '<=1.4.1'; },
    c => { c.severity = 'critical'; }, c => { c.url = 'https://github.com/advisories/GHSA-new'; },
  ]) {
    const report = backportAudit();
    change(report.vulnerabilities['node-forge'].via[0]);
    const result = runAuditCli(t, [{ stdout: JSON.stringify(report), status: 1 }]);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /node-forge/);
  }
  const report = backportAudit();
  report.vulnerabilities.braces.via.push({ name: 'braces', dependency: 'braces', source: 999,
    severity: 'high', range: '<=3.0.3', url: 'https://github.com/advisories/GHSA-new' });
  assert.equal(runAuditCli(t, [{ stdout: JSON.stringify(report), status: 1 }]).status, 1);
});

test('audit CLI does not lend a verified backport to an advisory-free or dangling branch', t => {
  for (const dangling of [true, false]) {
    const report = backportAudit();
    report.vulnerabilities.expo.via.push('cycle-a');
    if (!dangling) {
      report.vulnerabilities['cycle-a'] = { name: 'cycle-a', severity: 'high', nodes: ['node_modules/cycle-a'], via: ['cycle-a'] };
    }
    const result = runAuditCli(t, [{ stdout: JSON.stringify(report), status: 1 }]);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /expo/);
  }
});

test('audit CLI retries a transient registry failure and evaluates the recovered report', (t) => {
  const result = runAuditCli(t, [unavailableAudit, cleanAudit]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.calls, 2);
  assert.match(result.stdout, /Project policy accepted/);
});

test('audit CLI rejects an unpatched installation even when the registry reports no findings', t => {
  const result = runAuditCli(t, [cleanAudit], d => {
    const file = path.join(d, 'node_modules/node-forge/lib/rsa.js');
    writeFileSync(file, readFileSync(file, 'utf8') + '\n// altered installed bytes\n');
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /patch verification failed/);
});

test('audit CLI rejects changed verifier or lockfile bytes instead of trusting a success assertion', t => {
  for (const [file, bytes] of [
    ['scripts/dependency-patches.js', 'process.exit(0);\n'],
    ['package-lock.json', readFileSync(path.join(__dirname, '../package-lock.json'), 'utf8') + '\n'],
  ]) {
    const result = runAuditCli(t, [cleanAudit], d => writeFileSync(path.join(d, file), bytes));
    assert.equal(result.status, 1);
    assert.match(result.stderr, /reviewed evidence mismatch/);
  }
});

test('audit CLI rejects a symlinked verifier instead of verifying a different installation', t => {
  const result = runAuditCli(t, [cleanAudit], d => {
    const file = path.join(d, 'scripts/dependency-patches.js');
    rmSync(file);
    symlinkSync(path.join(__dirname, 'dependency-patches.js'), file);
    writeFileSync(path.join(d, 'node_modules/node-forge/lib/rsa.js'), 'altered bytes');
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /symbolic/);
});

test('audit CLI refuses a redirected evidence directory before writing outside its artifact scope', t => {
  const result = runAuditCli(t, [cleanAudit], d => {
    mkdirSync(path.join(d, 'elsewhere'));
    symlinkSync(path.join(d, 'elsewhere'), path.join(d, 'artifacts'));
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /symbolic/);
  assert.deepEqual(readdirSync(path.join(result.directory, 'elsewhere')), []);
});

test('audit CLI blocks missing or invalid source-commit provenance in CI', t => {
  const result = runAuditCli(t, [cleanAudit], d => {
    writeFileSync(path.join(d, 'git'), `#!${process.execPath}\nconsole.log('not-a-commit');\n`, { mode: 0o755 });
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /source-commit provenance/);
});

test('audit CLI accepts the final pre-expiry instant but blocks at the approved expiry', t => {
  assert.equal(runAuditCli(t, [cleanAudit], undefined, '2026-10-12T23:59:58.999Z').status, 0);
  const expired = runAuditCli(t, [cleanAudit], undefined, '2026-10-12T23:59:59.000Z');
  assert.equal(expired.status, 1);
  assert.match(expired.stderr, /expired/);
});

test('audit CLI rechecks expiry before accepting a report evaluated across the boundary', t => {
  const result = runAuditCli(t, [cleanAudit], d => {
    writeFileSync(path.join(d, 'clock.cjs'), `let calls = 0;
Date.now = () => Date.parse(++calls <= 2 ? '2026-10-12T23:59:58.999Z' : '2026-10-12T23:59:59Z');`);
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /expired/);
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
  assert.doesNotMatch(result.stdout, /Project policy accepted/);
});

test('audit CLI retains exact raw output and a decision checksum on success and failure', t => {
  for (const response of [cleanAudit, { stdout: 'not JSON', status: 1 }]) {
    const result = runAuditCli(t, [response]);
    const base = path.join(result.directory, 'artifacts/npm-audit');
    const evidence = path.join(base, readdirSync(base)[0]);
    assert.equal(readFileSync(path.join(evidence, 'attempt-1.stdout'), 'utf8'), response.stdout);
    const decision = JSON.parse(readFileSync(path.join(evidence, 'decision.json')));
    assert.equal(decision.exitCode, response === cleanAudit ? 0 : 1);
    assert.equal(decision.attempts[0].stdoutSha256, createHash('sha256').update(response.stdout).digest('hex'));
    assert.equal(decision.expiresAt, '2026-10-12T23:59:59Z');
  }
});
