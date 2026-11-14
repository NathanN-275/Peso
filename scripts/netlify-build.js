const { execFileSync } = require('node:child_process');
const APP_SITE_ID = '230da8eb-f00e-45d4-ba54-95f2e26f21c4';
const combinedBinding = require('../config/combined-web-release-binding.json');

function isCombinedProject(env, binding = combinedBinding) {
  return binding.schema_version === 1
    && typeof binding.site_id === 'string'
    && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(binding.site_id)
    && binding.site_id !== APP_SITE_ID
    && env.SITE_ID === binding.site_id;
}

function buildScript(env, binding = combinedBinding) {
  // This selects an artifact, not visibility. Provider access controls must be
  // verified before binding the new project and before every candidate deploy.
  if (isCombinedProject(env, binding)) return 'web:build:release';
  // Branch names can override deploy-preview contexts in netlify.toml. Only the
  // stable, private main branch deploy may export the app, never its release PR.
  return env.SITE_ID === APP_SITE_ID && env.CONTEXT === 'branch-deploy' && env.BRANCH === 'main'
    ? 'web:build:release'
    : 'web:build:marketing';
}
function buildEnvironment(env, binding = combinedBinding) {
  if (isCombinedProject(env, binding)) return { ...env, PESO_RELEASE_ENV: 'public-beta' };
  // Branch-only TOML settings would override every project's main build.
  if (env.SITE_ID === APP_SITE_ID && env.CONTEXT === 'branch-deploy' && env.BRANCH === 'main') {
    const { RENDER_BETA_WEB_ORIGIN, approvedRenderBetaApi, loadRenderBetaBinding } = require('./release-env');
    return { ...env, PESO_RELEASE_ENV: 'render-beta',
      EXPO_PUBLIC_SUPABASE_URL: require('./student-environment').STUDENT_SUPABASE_URL,
      EXPO_PUBLIC_PRODUCTION_BACKEND_URL: approvedRenderBetaApi(loadRenderBetaBinding()),
      EXPO_PUBLIC_AUTH_CHALLENGE_URL: `${RENDER_BETA_WEB_ORIGIN}/auth/turnstile/`,
      EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED: 'false' };
  }
  return env;
}
module.exports = { APP_SITE_ID, buildScript, isCombinedProject, buildEnvironment };
if (require.main === module) {
  const env = buildEnvironment(process.env);
  execFileSync('npm', ['run', buildScript(env)], { stdio: 'inherit', env });
}
