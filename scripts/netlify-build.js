const { execFileSync } = require('node:child_process');
const APP_SITE_ID = '230da8eb-f00e-45d4-ba54-95f2e26f21c4';

function buildScript(env) {
  // Branch names can override deploy-preview contexts in netlify.toml. Only the
  // stable, private main branch deploy may export the app, never its release PR.
  return env.SITE_ID === APP_SITE_ID && env.CONTEXT === 'branch-deploy' && env.BRANCH === 'main'
    ? 'web:build:release'
    : 'web:build:marketing';
}
module.exports = { APP_SITE_ID, buildScript };
if (require.main === module) {
  execFileSync('npm', ['run', buildScript(process.env)], { stdio: 'inherit' });
}
