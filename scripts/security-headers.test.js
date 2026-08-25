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

test('Netlify revalidates HTML and caches fingerprinted app assets and WOFF2 fonts', () => {
  assert.match(netlifyConfig, /for = "\/app\/_expo\/static\/\*"\s+\[headers\.values\]\s+Cache-Control = "public, max-age=31536000, immutable"/s);
  assert.match(netlifyConfig, /for = "\/app\/fonts\/\*"\s+\[headers\.values\]\s+Cache-Control = "public, max-age=31536000, immutable"/s);
  assert.match(netlifyConfig, /for = "\/\*"\s+\[headers\.values\]\s+Cache-Control = "public, max-age=0, must-revalidate"/s);
  assert.doesNotMatch(netlifyConfig, /Basic-Auth/i);
});
