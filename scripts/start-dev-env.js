const fs = require('node:fs');
const path = require('node:path');

const DEFAULT_BACKEND_PORT = '8000';
const DEFAULT_WEB_BACKEND_HOST = 'localhost';

function parseDotenv(contents) {
  const values = {};

  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim();

    if (!line || line.startsWith('#')) {
      continue;
    }

    const normalizedLine = line.startsWith('export ') ? line.slice('export '.length).trim() : line;
    const separatorIndex = normalizedLine.indexOf('=');

    if (separatorIndex <= 0) {
      continue;
    }

    const key = normalizedLine.slice(0, separatorIndex).trim();
    let value = normalizedLine.slice(separatorIndex + 1).trim();

    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      continue;
    }

    if (
      (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    values[key] = value;
  }

  return values;
}

function loadRootEnv(rootDir, baseEnv = process.env) {
  return loadRootEnvWithSources(rootDir, baseEnv).env;
}

function loadRootEnvWithSources(rootDir, baseEnv = process.env) {
  const envPath = path.join(rootDir, '.env');
  const fileEnv = fs.existsSync(envPath) ? parseDotenv(fs.readFileSync(envPath, 'utf8')) : {};
  const sources = {};

  for (const key of Object.keys(fileEnv)) {
    sources[key] = 'root .env';
  }

  for (const key of Object.keys(baseEnv)) {
    sources[key] = 'shell env';
  }

  return {
    env: {
      ...fileEnv,
      ...baseEnv,
    },
    sources,
  };
}

function resolveBackendPort(env) {
  return env.BACKEND_PORT || env.EXPO_PUBLIC_BACKEND_PORT || DEFAULT_BACKEND_PORT;
}

function isLoopbackBackendUrl(value) {
  try {
    const hostname = new URL(value).hostname;
    return hostname === 'localhost' || hostname === '127.0.0.1';
  } catch {
    return false;
  }
}

function resolveExpoBackendUrl(env, backendPort, options = {}) {
  const frontendTarget = options.frontendTarget || 'native';
  const configuredUrl = env.EXPO_PUBLIC_BACKEND_URL;

  if (frontendTarget === 'web') {
    if (configuredUrl && isLoopbackBackendUrl(configuredUrl)) {
      return {
        url: configuredUrl,
        source: options.envSources?.EXPO_PUBLIC_BACKEND_URL || 'environment',
      };
    }

    return {
      url: `http://${env.EXPO_PUBLIC_WEB_BACKEND_HOST || DEFAULT_WEB_BACKEND_HOST}:${backendPort}`,
      source: configuredUrl
        ? `web loopback default; ignored ${options.envSources?.EXPO_PUBLIC_BACKEND_URL || 'environment'} LAN override`
        : 'default',
    };
  }

  if (configuredUrl) {
    return {
      url: configuredUrl,
      source: options.envSources?.EXPO_PUBLIC_BACKEND_URL || 'environment',
    };
  }

  return {
    url: `http://localhost:${backendPort}`,
    source: 'default',
  };
}

function buildExpoEnv(env, backendPort, options = {}) {
  const backendUrl = resolveExpoBackendUrl(env, backendPort, options);

  return {
    ...env,
    EXPO_PUBLIC_BACKEND_PORT: env.EXPO_PUBLIC_BACKEND_PORT || backendPort,
    EXPO_PUBLIC_BACKEND_URL: backendUrl.url,
  };
}

function createDevEnvironment({ rootDir, baseEnv = process.env, frontendTarget = 'native' }) {
  const loadedEnv = loadRootEnvWithSources(rootDir, baseEnv);
  const env = loadedEnv.env;
  const backendPort = resolveBackendPort(env);
  const expoBackendUrl = resolveExpoBackendUrl(
    env,
    backendPort,
    {
      envSources: loadedEnv.sources,
      frontendTarget,
    },
  );

  return {
    env,
    envSources: loadedEnv.sources,
    backendPort,
    backendHealthUrl: `http://127.0.0.1:${backendPort}/health`,
    expoBackendUrl: expoBackendUrl.url,
    expoBackendUrlSource: expoBackendUrl.source,
    expoEnv: buildExpoEnv(env, backendPort, {
      envSources: loadedEnv.sources,
      frontendTarget,
    }),
  };
}

module.exports = {
  DEFAULT_BACKEND_PORT,
  buildExpoEnv,
  createDevEnvironment,
  loadRootEnv,
  loadRootEnvWithSources,
  parseDotenv,
  resolveExpoBackendUrl,
  resolveBackendPort,
};
