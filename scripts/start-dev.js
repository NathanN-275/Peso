#!/usr/bin/env node

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { createDevEnvironment } = require('./start-dev-env');
const { buildExpoStartArgs, parseStartOptions } = require('./start-dev-options');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const startupOptions = parseStartOptions(process.argv.slice(2));
const { startWeb } = startupOptions;
const devEnvironment = createDevEnvironment({
  rootDir,
  baseEnv: process.env,
  frontendTarget: startWeb ? 'web' : 'native',
});
const { backendPort, backendHealthUrl, expoEnv } = devEnvironment;
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
const backendStartupTimeoutMs = Number(devEnvironment.env.BACKEND_STARTUP_TIMEOUT_MS || 30000);
const startAnalysisWorker = devEnvironment.env.START_ANALYSIS_WORKER !== 'false';

function log(scope, message) {
  process.stdout.write(`[${scope}] ${message}\n`);
}

function checkBackendHealth(url = backendHealthUrl) {
  return new Promise((resolve) => {
    const request = http.get(url, (response) => {
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

async function waitForBackendHealth(timeoutMs = backendStartupTimeoutMs) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    if (await checkBackendHealth()) {
      return;
    }

    await sleep(500);
  }

  throw new Error(
    `FastAPI did not become healthy at ${backendHealthUrl} within ${timeoutMs}ms. `
    + 'Check backend/.env, port conflicts, and backend startup logs above.'
  );
}

function spawnProcess(scope, command, args, options = {}) {
  const { continueOnExitCodes = [], ...spawnOptions } = options;
  const child = spawn(command, args, {
    stdio: 'inherit',
    ...spawnOptions,
  });

  children.add(child);

  child.on('exit', (code, signal) => {
    children.delete(child);

    if (!shuttingDown) {
      if (continueOnExitCodes.includes(code)) {
        log(scope, `stopped with code ${code}; apply the required Supabase migration before starting analysis`);
        return;
      }
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
  log('backend', `health URL ${backendHealthUrl}`);
  log(
    'expo',
    `backend URL ${devEnvironment.expoBackendUrl} (${devEnvironment.expoBackendUrlSource})`
  );

  const backendAlreadyRunning = await checkBackendHealth();

  let backendHealthPromise = Promise.resolve();

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
    backendHealthPromise = waitForBackendHealth().then(() => {
      log('backend', `healthy at ${backendHealthUrl}`);
    });
  }

  if (startAnalysisWorker) {
    log('worker', 'starting durable video-analysis worker');
    spawnProcess(
      'worker',
      pythonCommand,
      ['-m', 'app.jobs.worker', '--env-file', '.env'],
      {
        cwd: backendDir,
        continueOnExitCodes: [78],
      }
    );
  }

  const expoArgs = buildExpoStartArgs(startupOptions);
  log(
    'expo',
    `starting Expo ${startWeb ? 'web' : 'native'} with backend ${expoEnv.EXPO_PUBLIC_BACKEND_URL}`
      + (startupOptions.clearMetroCache ? ' (clearing Metro cache)' : ' (using Metro cache)')
  );
  spawnProcess('expo', expoBinary, expoArgs, {
    cwd: rootDir,
    env: expoEnv,
  });

  await backendHealthPromise;
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

main().catch((error) => {
  log('start', error instanceof Error ? error.message : String(error));
  shutdown(1);
});
