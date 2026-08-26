const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

test('native auth uses PKCE and never adopts token pairs from deep links', () => {
  const client = read('lib/supabase.ts');
  const nativeRoot = read('src/native-root.tsx');

  assert.match(client, /flowType:\s*'pkce'/);
  assert.match(nativeRoot, /exchangeCodeForSession\(parsedRoute\.code\)/);
  assert.doesNotMatch(nativeRoot, /supabase\.auth\.setSession\(/);
});
