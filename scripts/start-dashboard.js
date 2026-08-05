#!/usr/bin/env node

const { spawn } = require('node:child_process');
const path = require('node:path');
const { createDevEnvironment } = require('./start-dev-env');

const rootDir = path.resolve(__dirname, '..');
const devEnvironment = createDevEnvironment({
  rootDir,
  baseEnv: process.env,
  frontendTarget: 'web',
});
const env = devEnvironment.env;

if (!env.EXPO_PUBLIC_SUPABASE_URL || !env.EXPO_PUBLIC_SUPABASE_ANON_KEY) {
  throw new Error('Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY in the root .env before starting the dashboard.');
}

const child = spawn(
  'npm',
  ['--prefix', 'dashboard', 'run', 'dev', '--', '--host', '127.0.0.1'],
  {
    cwd: rootDir,
    env: {
      ...process.env,
      VITE_SUPABASE_URL: env.EXPO_PUBLIC_SUPABASE_URL,
      VITE_SUPABASE_ANON_KEY: env.EXPO_PUBLIC_SUPABASE_ANON_KEY,
      VITE_BACKEND_URL: devEnvironment.expoBackendUrl,
      VITE_BACKEND_PROXY_TARGET: new URL(devEnvironment.backendHealthUrl).origin,
    },
    stdio: 'inherit',
  },
);

child.on('exit', (code) => process.exit(code ?? 1));
