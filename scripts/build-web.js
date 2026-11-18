const { rmSync, writeFileSync, copyFileSync } = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { verifyMarketingBuild } = require('./verify-marketing-build');
const { stagingReleaseIdentity, isStagingProject } = require('./staging-web-environment');

const mode = process.argv[2];
if (!['marketing', 'private-beta'].includes(mode)) {
  throw new Error('Choose marketing or private-beta explicitly.');
}
const root = path.resolve(__dirname, '..');
let stagingIdentity;
const dist = path.join(root, 'dist');
// Never publish stale app exports, redirects, or authentication assets.
rmSync(dist, { recursive: true, force: true });
try {
  if (process.env.PESO_RELEASE_ENV === 'web-staging' || isStagingProject(process.env)) {
    stagingIdentity = stagingReleaseIdentity(process.env);
    if (mode !== 'private-beta' || execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: root, encoding: 'utf8',
    }).trim() !== stagingIdentity.source_commit || execFileSync('git', ['status', '--porcelain'], {
      cwd: root, encoding: 'utf8',
    }).trim()) throw new Error('Staging artifact requires the clean selected source commit and both web surfaces.');
    if (stagingIdentity.private_media_enabled) {
      // This checkout must contain the real runtime before a verified binding can activate it.
      const { existsSync } = require('node:fs');
      if (!existsSync(path.join(root, 'backend/app/routes/private_media.py'))) {
        throw new Error('Staging media runtime is missing from the selected source.');
      }
    }
    execFileSync(process.execPath, ['scripts/release-env.js'], { cwd: root, stdio: 'inherit' });
  }
  execFileSync(process.execPath, ['scripts/dependency-patches.js', 'verify'], { cwd: root, stdio: 'inherit' });
  const run = (args) => execFileSync('npm', args, {
    cwd: root, stdio: 'inherit', env: { ...process.env, PESO_WEB_BUILD: mode },
  });
  execFileSync(process.execPath, ['scripts/npm-audit-web-ci.js'], { cwd: root, stdio: 'inherit' });
  run(['--prefix', 'web', 'run', 'build']);
  if (mode === 'private-beta') {
    run(['run', 'app:web:export']);
    if (stagingIdentity) {
      writeFileSync(path.join(dist, 'peso-release.json'), JSON.stringify(stagingIdentity) + '\n');
      // Dashboard manual uploads consume these artifact files, not repository TOML.
      copyFileSync(path.join(root, 'config/staging-web-headers'), path.join(dist, '_headers'));
      copyFileSync(path.join(root, 'config/staging-web-redirects'), path.join(dist, '_redirects'));
    }
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
