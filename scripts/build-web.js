const { rmSync, writeFileSync } = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { verifyMarketingBuild } = require('./verify-marketing-build');

const mode = process.argv[2];
if (!['marketing', 'private-beta'].includes(mode)) {
  throw new Error('Choose marketing or private-beta explicitly.');
}
const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
const run = (args) => execFileSync('npm', args, {
  cwd: root, stdio: 'inherit', env: { ...process.env, PESO_WEB_BUILD: mode },
});
// Never publish stale app exports, redirects, or authentication assets.
rmSync(dist, { recursive: true, force: true });
try {
  run(['--prefix', 'web', 'run', 'build']);
  if (mode === 'private-beta') {
    run(['run', 'app:web:export']);
  } else {
    rmSync(path.join(dist, 'auth'), { recursive: true, force: true });
    writeFileSync(path.join(dist, '_redirects'),
      '/app /beta 302!\n/app/* /beta 302!\n/auth /beta 302!\n/auth/* /beta 302!\n');
    verifyMarketingBuild(dist);
  }
} catch (error) {
  // A failed build must not leave a publishable partial artifact.
  rmSync(dist, { recursive: true, force: true });
  throw error;
}
