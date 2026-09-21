const assert = require('node:assert/strict');
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { verifyMarketingBuild } = require('./verify-marketing-build');

function fixture(t) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'peso-marketing-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  for (const page of ['index.html', 'beta/index.html', 'privacy/index.html', 'terms/index.html']) {
    mkdirSync(path.dirname(path.join(root, page)), { recursive: true });
    writeFileSync(path.join(root, page), '<h1>Beta coming soon</h1>');
  }
  writeFileSync(path.join(root, '_redirects'), '/app /beta 302!\n/app/* /beta 302!\n/auth /beta 302!\n/auth/* /beta 302!\n');
  return root;
}

test('marketing gate accepts only intended pages and rejects retained app/auth exports', (t) => {
  const root = fixture(t);
  verifyMarketingBuild(root);
  for (const name of ['app', 'auth', '_expo']) {
    mkdirSync(path.join(root, name));
    assert.throws(() => verifyMarketingBuild(root), /Unexpected marketing output/);
    rmSync(path.join(root, name), { recursive: true });
  }
});

test('marketing gate blocks backend calls, collection forms, and app entry points', (t) => {
  const root = fixture(t);
  for (const content of ['fetch("https://api.example.com")', '<form action="/">', '<a href="/app/signup">Join</a>', '<script src="/auth/turnstile.js"></script>']) {
    writeFileSync(path.join(root, 'index.html'), content);
    assert.throws(() => verifyMarketingBuild(root));
  }
});

test('marketing gate rejects missing forced redirects and extra HTML pages', (t) => {
  const root = fixture(t);
  writeFileSync(path.join(root, 'beta/login.html'), '<h1>Sign in</h1>');
  assert.throws(() => verifyMarketingBuild(root));
  rmSync(path.join(root, 'beta/login.html'));
  writeFileSync(path.join(root, '_redirects'), '/app/* /app/index.html 200\n');
  assert.throws(() => verifyMarketingBuild(root));
});

test('marketing gate rejects inline scripts blocked by the hosted CSP', (t) => {
  const root = fixture(t);
  writeFileSync(path.join(root, 'index.html'), '<script type="module">document.querySelector("video")</script>');
  assert.throws(() => verifyMarketingBuild(root), /Inline script blocked/);
});
