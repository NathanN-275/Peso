const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const {
  buildExpoEnv,
  createDevEnvironment,
  parseDotenv,
} = require('./start-dev-env');

function withTempDir(callback) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-start-dev-'));

  try {
    return callback(tempDir);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

test('parseDotenv reads common root env entries', () => {
  assert.deepEqual(
    parseDotenv(`
      # comment
      EXPO_PUBLIC_BACKEND_URL=http://10.0.0.221:8000
      export EXPO_PUBLIC_BACKEND_TARGET=physical-device
      QUOTED_VALUE="hello"
    `),
    {
      EXPO_PUBLIC_BACKEND_URL: 'http://10.0.0.221:8000',
      EXPO_PUBLIC_BACKEND_TARGET: 'physical-device',
      QUOTED_VALUE: 'hello',
    }
  );
});

test('createDevEnvironment preserves root .env backend URL', () => {
  withTempDir((rootDir) => {
    fs.writeFileSync(
      path.join(rootDir, '.env'),
      [
        'EXPO_PUBLIC_BACKEND_URL=http://10.0.0.221:8000',
        'EXPO_PUBLIC_BACKEND_PORT=8000',
      ].join('\n')
    );

    const environment = createDevEnvironment({ rootDir, baseEnv: {} });

    assert.equal(environment.backendPort, '8000');
    assert.equal(environment.backendHealthUrl, 'http://127.0.0.1:8000/health');
    assert.equal(environment.expoEnv.EXPO_PUBLIC_BACKEND_URL, 'http://10.0.0.221:8000');
    assert.equal(environment.expoBackendUrlSource, 'root .env');
  });
});

test('createDevEnvironment uses loopback for web even when root .env targets physical device', () => {
  withTempDir((rootDir) => {
    fs.writeFileSync(
      path.join(rootDir, '.env'),
      [
        'EXPO_PUBLIC_BACKEND_URL=http://10.0.0.221:8000',
        'EXPO_PUBLIC_BACKEND_TARGET=physical-device',
        'EXPO_PUBLIC_WEB_BACKEND_HOST=127.0.0.1',
        'EXPO_PUBLIC_BACKEND_PORT=8000',
      ].join('\n')
    );

    const environment = createDevEnvironment({
      rootDir,
      baseEnv: {},
      frontendTarget: 'web',
    });

    assert.equal(environment.expoEnv.EXPO_PUBLIC_BACKEND_URL, 'http://127.0.0.1:8000');
    assert.match(environment.expoBackendUrlSource, /ignored root \.env LAN override/);
  });
});

test('shell env wins over root .env', () => {
  withTempDir((rootDir) => {
    fs.writeFileSync(
      path.join(rootDir, '.env'),
      'EXPO_PUBLIC_BACKEND_URL=http://10.0.0.221:8000\n'
    );

    const environment = createDevEnvironment({
      rootDir,
      baseEnv: {
        EXPO_PUBLIC_BACKEND_URL: 'http://127.0.0.1:8000',
      },
    });

    assert.equal(environment.expoEnv.EXPO_PUBLIC_BACKEND_URL, 'http://127.0.0.1:8000');
  });
});

test('buildExpoEnv falls back to localhost only without configured backend URL', () => {
  assert.equal(
    buildExpoEnv({ EXPO_PUBLIC_BACKEND_PORT: '9000' }, '9000').EXPO_PUBLIC_BACKEND_URL,
    'http://localhost:9000'
  );
});
