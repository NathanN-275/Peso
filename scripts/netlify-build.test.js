const assert = require('node:assert/strict');
const test = require('node:test');
const { APP_SITE_ID, buildScript } = require('./netlify-build');

test('an explicitly bound new project builds both surfaces in production and previews', () => {
  const site = '11111111-2222-3333-4444-555555555555';
  const binding = { schema_version: 1, site_id: site };
  for (const CONTEXT of ['production', 'deploy-preview', 'branch-deploy']) {
    assert.equal(buildScript({ SITE_ID: site, CONTEXT }, binding), 'web:build:release');
    assert.equal(buildScript({ SITE_ID: 'other', CONTEXT }, binding), 'web:build:marketing');
  }
});

test('missing, malformed and historical app bindings cannot enable combined production', () => {
  for (const site_id of [null, '', 'not-a-site-id', APP_SITE_ID]) {
    assert.equal(buildScript({ SITE_ID: site_id, CONTEXT: 'production' }, {
      schema_version: 1, site_id,
    }), 'web:build:marketing');
  }
  assert.equal(buildScript({ SITE_ID: '11111111-2222-3333-4444-555555555555' }, {
    schema_version: 2, site_id: '11111111-2222-3333-4444-555555555555',
  }), 'web:build:marketing');
});

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
