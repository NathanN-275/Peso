const assert = require('node:assert/strict');
const test = require('node:test');
const { APP_SITE_ID, buildScript } = require('./netlify-build');

test('only the stable main branch deploy builds the private beta', () => {
  assert.equal(buildScript({ SITE_ID: APP_SITE_ID, CONTEXT: 'branch-deploy', BRANCH: 'main' }), 'web:build:release');
  for (const env of [
    {},
    { CONTEXT: 'production', BRANCH: 'production' },
    { CONTEXT: 'production', BRANCH: 'main' },
    { CONTEXT: 'deploy-preview', BRANCH: 'main' },
    { CONTEXT: 'branch-deploy', BRANCH: 'feature' },
  ]) assert.equal(buildScript(env), 'web:build:marketing');
});

test('every non-app project and preview fails closed to marketing', () => {
  for (const SITE_ID of [undefined, '', 'marketing-project', APP_SITE_ID]) {
    for (const CONTEXT of ['production', 'deploy-preview', 'branch-deploy', undefined]) {
      for (const BRANCH of ['main', 'production', 'feature', undefined]) {
        const expected = SITE_ID === APP_SITE_ID && CONTEXT === 'branch-deploy' && BRANCH === 'main'
          ? 'web:build:release' : 'web:build:marketing';
        assert.equal(buildScript({ SITE_ID, CONTEXT, BRANCH }), expected);
      }
    }
  }
});
