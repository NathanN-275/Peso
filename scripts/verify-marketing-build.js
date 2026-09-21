const { readdirSync, readFileSync } = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

function verifyMarketingBuild(dist) {
  const pages = [];
  const allowed = new Set(['index.html', 'beta', 'privacy', 'terms', 'marketing-assets',
    'demo', 'peso-logo.png', 'og.png', 'favicon.png', 'robots.txt', '_redirects']);
  for (const name of readdirSync(dist)) assert.ok(allowed.has(name), `Unexpected marketing output: ${name}`);
  function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      assert.ok(!entry.isSymbolicLink(), `Unexpected symlink: ${file}`);
      if (entry.isDirectory()) { walk(file); continue; }
      if (file.endsWith('.html')) pages.push(path.relative(dist, file));
      if (!/\.(html|js|css|json)$/.test(file)) continue;
      const content = readFileSync(file, 'utf8');
      if (file.endsWith('.html')) {
        assert.doesNotMatch(content, /<script\b(?![^>]*\bsrc=)[^>]*>\s*\S/i,
          `Inline script blocked by marketing CSP in ${file}`);
      }
      assert.doesNotMatch(content, /supabase|onrender\.com|turnstile|EXPO_PUBLIC_|_expo|XMLHttpRequest|WebSocket|sendBeacon|\bfetch\s*\(/i, `App/backend code in ${file}`);
      assert.doesNotMatch(content, /(?:href|src|action)=["']\/(?:app|auth)(?:[\/"'?#])|<form\b|<input\b/i, `App entry or collection form in ${file}`);
    }
  }
  walk(dist);
  assert.deepEqual(pages.sort(), ['beta/index.html', 'index.html', 'privacy/index.html', 'terms/index.html']);
  assert.equal(readFileSync(path.join(dist, '_redirects'), 'utf8'),
    '/app /beta 302!\n/app/* /beta 302!\n/auth /beta 302!\n/auth/* /beta 302!\n');
  console.log('Marketing output verified: four pages, no app/auth assets or backend calls.');
}
module.exports = { verifyMarketingBuild };
if (require.main === module) verifyMarketingBuild(path.resolve(__dirname, '..', 'dist'));
