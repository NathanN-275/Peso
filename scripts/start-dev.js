#!/usr/bin/env node

const { execFileSync, spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const backendPort = process.env.BACKEND_PORT || '8000';
const backendHealthUrl = `http://127.0.0.1:${backendPort}/health`;
const backendPython = path.join(backendDir, '.venv', 'bin', 'python');
const pythonCommand = fs.existsSync(backendPython) ? backendPython : 'python3';
const backendEnvFile = path.join(backendDir, '.env');
const expoBinary = path.join(
  rootDir,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'expo.cmd' : 'expo'
);

const children = new Set();
let shuttingDown = false;

function log(scope, message) {
  process.stdout.write(`[${scope}] ${message}\n`);
}

function checkBackendHealth() {
  return new Promise((resolve) => {
    const request = http.get(backendHealthUrl, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });

    request.on('error', () => {
      resolve(false);
    });

    request.setTimeout(1000, () => {
      request.destroy();
      resolve(false);
    });
  });
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function waitForBackendHealth({ attempts = 40, delayMs = 500 } = {}) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    if (await checkBackendHealth()) {
      return true;
    }

    await sleep(delayMs);
  }

  return false;
}

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Missing backend env file: ${filePath}`);
  }

  return fs.readFileSync(filePath, 'utf8').split(/\r?\n/).reduce((values, line) => {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) {
      return values;
    }

    const separatorIndex = trimmed.indexOf('=');
    const key = trimmed.slice(0, separatorIndex).trim();
    const value = trimmed.slice(separatorIndex + 1).trim().replace(/^["']|["']$/g, '');

    values[key] = value;
    return values;
  }, {});
}

function verifyBackendEnv() {
  const env = parseEnvFile(backendEnvFile);
  const missingKeys = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_JWT_SECRET']
    .filter((key) => !env[key]);

  if (missingKeys.length > 0) {
    throw new Error(`backend/.env is missing required keys: ${missingKeys.join(', ')}`);
  }

  return env;
}

function verifyFfmpeg(env) {
  const configuredBinary = env.FFMPEG_BINARY?.trim();
  const command = configuredBinary || 'ffmpeg';

  try {
    execFileSync(command, ['-version'], { stdio: 'ignore' });
  } catch {
    throw new Error(
      configuredBinary
        ? `FFMPEG_BINARY is set but not executable: ${configuredBinary}`
        : 'ffmpeg is required for video playback compression. Install it with `brew install ffmpeg` or set FFMPEG_BINARY.'
    );
  }
}

function spawnProcess(scope, command, args, options) {
  const child = spawn(command, args, {
    stdio: 'inherit',
    ...options,
  });

  children.add(child);

  child.on('exit', (code, signal) => {
    children.delete(child);

    if (!shuttingDown) {
      log(scope, `exited with code ${code ?? 0}${signal ? ` (${signal})` : ''}`);
      shutdown(code ?? 0);
    }
  });

  child.on('error', (error) => {
    children.delete(child);
    log(scope, error.message);
    shutdown(1);
  });

  return child;
}

function shutdown(exitCode = 0) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;

  for (const child of children) {
    child.kill('SIGINT');
  }

  setTimeout(() => {
    process.exit(exitCode);
  }, 300);
}

async function main() {
  const backendEnv = verifyBackendEnv();
  verifyFfmpeg(backendEnv);

  const backendAlreadyRunning = await checkBackendHealth();

  if (backendAlreadyRunning) {
    log('backend', `using existing backend at ${backendHealthUrl}`);
  } else {
    log('backend', `starting FastAPI on 0.0.0.0:${backendPort} for simulator and physical-device access`);
    spawnProcess(
      'backend',
      pythonCommand,
      [
        '-m',
        'uvicorn',
        'app.main:app',
        '--host',
        '0.0.0.0',
        '--port',
        backendPort,
        '--env-file',
        '.env',
      ],
      {
        cwd: backendDir,
      }
    );

    const backendReady = await waitForBackendHealth();

    if (!backendReady) {
      throw new Error(`FastAPI did not become healthy at ${backendHealthUrl}. Check the backend logs above.`);
    }
  }

  log('backend', `health check passed at ${backendHealthUrl}`);
  log('expo', 'starting Expo');
  spawnProcess('expo', expoBinary, ['start'], {
    cwd: rootDir,
    env: {
      ...process.env,
      EXPO_PUBLIC_BACKEND_URL:
        process.env.EXPO_PUBLIC_BACKEND_URL || `http://localhost:${backendPort}`,
    },
  });
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

main().catch((error) => {
  log('start', error instanceof Error ? error.message : String(error));
  shutdown(1);
});
