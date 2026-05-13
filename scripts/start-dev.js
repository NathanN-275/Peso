#!/usr/bin/env node

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const backendPort = process.env.BACKEND_PORT || '8000';
const backendHealthUrl = `http://127.0.0.1:${backendPort}/health`;
const backendPython = path.join(backendDir, '.venv', 'bin', 'python');
const pythonCommand = fs.existsSync(backendPython) ? backendPython : 'python3';
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
  const backendAlreadyRunning = await checkBackendHealth();

  if (backendAlreadyRunning) {
    log('backend', `using existing backend at ${backendHealthUrl}`);
  } else {
    log('backend', `starting FastAPI on port ${backendPort}`);
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
  }

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
