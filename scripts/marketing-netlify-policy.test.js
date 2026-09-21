const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const test = require('node:test');
const config = readFileSync(require('node:path').join(__dirname, '../web/netlify.toml'), 'utf8');

test('dedicated marketing configuration cannot select an app export or backend configuration', () => {
  assert.match(config, /base = "\."/);
  assert.match(config, /publish = "dist"/);
  assert.match(config, /command = "npm --prefix web ci && npm run web:build:marketing && npm run web:verify:marketing"/);
  assert.doesNotMatch(config, /\[context\.|EXPO_PUBLIC_|PESO_RELEASE_ENV|web:build:release|netlify-build\.js|\/app\/|functions|identity|forms/i);
  assert.match(config, /connect-src 'none'/);
  assert.match(config, /form-action 'none'/);
  for (const header of ['Content-Security-Policy', 'X-Frame-Options', 'X-Content-Type-Options', 'Referrer-Policy', 'Permissions-Policy', 'Strict-Transport-Security']) {
    assert.ok(config.includes(header), header);
  }
});
