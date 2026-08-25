const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const netlifyConfig = fs.readFileSync(path.join(__dirname, '..', 'netlify.toml'), 'utf8');

test('Netlify applies a restrictive browser security policy', () => {
  assert.match(netlifyConfig, /Content-Security-Policy = ".*default-src 'self';.*object-src 'none';.*frame-ancestors 'none';.*script-src 'self' https:\/\/challenges\.cloudflare\.com;/);
  assert.match(netlifyConfig, /X-Content-Type-Options = "nosniff"/);
  assert.match(netlifyConfig, /X-Frame-Options = "DENY"/);
  assert.match(netlifyConfig, /Strict-Transport-Security = "max-age=31536000; includeSubDomains"/);
});
