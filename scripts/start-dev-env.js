const fs = require('node:fs');
const path = require('node:path');

const DEFAULT_BACKEND_PORT = '8000';

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
  const envPath = path.join(rootDir, '.env');

  if (!fs.existsSync(envPath)) {
    return { ...baseEnv };
  }

  const fileEnv = parseDotenv(fs.readFileSync(envPath, 'utf8'));

  return {
    ...fileEnv,
    ...baseEnv,
  };
}

function resolveBackendPort(env) {
  return env.BACKEND_PORT || env.EXPO_PUBLIC_BACKEND_PORT || DEFAULT_BACKEND_PORT;
}

function buildExpoEnv(env, backendPort) {
  return {
    ...env,
    EXPO_PUBLIC_BACKEND_PORT: env.EXPO_PUBLIC_BACKEND_PORT || backendPort,
    EXPO_PUBLIC_BACKEND_URL: env.EXPO_PUBLIC_BACKEND_URL || `http://localhost:${backendPort}`,
  };
}

function createDevEnvironment({ rootDir, baseEnv = process.env }) {
  const env = loadRootEnv(rootDir, baseEnv);
  const backendPort = resolveBackendPort(env);

  return {
    env,
    backendPort,
    backendHealthUrl: `http://127.0.0.1:${backendPort}/health`,
    expoEnv: buildExpoEnv(env, backendPort),
  };
}

module.exports = {
  DEFAULT_BACKEND_PORT,
  buildExpoEnv,
  createDevEnvironment,
  loadRootEnv,
  parseDotenv,
  resolveBackendPort,
};
