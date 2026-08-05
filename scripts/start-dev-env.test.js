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

test('createDevEnvironment uses the same-origin proxy for web even when root .env targets a device', () => {
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

    assert.equal(environment.expoEnv.EXPO_PUBLIC_BACKEND_URL, '/__peso_api');
    assert.equal(environment.expoBackendUrlSource, 'web same-origin proxy');
    assert.equal(environment.expoEnv.EXPO_PUBLIC_WEB_SURFACE, 'web-app');
    assert.equal(environment.expoEnv.EXPO_PUBLIC_WEB_ROUTER_BASE, '/');
  });
});

test('createDevEnvironment routes local web requests through the Expo origin', () => {
  const environment = createDevEnvironment({
    rootDir: '/path/without/an/env/file',
    baseEnv: {},
    frontendTarget: 'web',
  });

  assert.equal(environment.expoEnv.EXPO_PUBLIC_BACKEND_URL, '/__peso_api');
  assert.equal(environment.expoEnv.EXPO_PUBLIC_WEB_SURFACE, 'web-app');
  assert.equal(environment.expoEnv.EXPO_PUBLIC_WEB_ROUTER_BASE, '/');
  assert.equal(environment.expoBackendUrlSource, 'web same-origin proxy');
  assert.equal(environment.backendHealthUrl, 'http://127.0.0.1:8000/health');
});

test('createDevEnvironment keeps localhost for iOS Simulator runs', () => {
  withTempDir((rootDir) => {
    fs.writeFileSync(
      path.join(rootDir, '.env'),
      [
        'EXPO_PUBLIC_BACKEND_URL=http://localhost:8000',
        'EXPO_PUBLIC_BACKEND_TARGET=ios-simulator',
        'EXPO_PUBLIC_BACKEND_PORT=8000',
      ].join('\n')
    );

    const environment = createDevEnvironment({
      rootDir,
      baseEnv: {},
      frontendTarget: 'native',
    });

    assert.equal(environment.expoEnv.EXPO_PUBLIC_BACKEND_URL, 'http://localhost:8000');
    assert.equal(environment.expoEnv.EXPO_PUBLIC_BACKEND_TARGET, 'ios-simulator');
    assert.equal(environment.expoEnv.EXPO_PUBLIC_WEB_SURFACE, 'native-preview');
    assert.equal(environment.backendHealthUrl, 'http://127.0.0.1:8000/health');
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
