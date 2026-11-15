const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const project = path.resolve(__dirname, '..');
const worker = path.join(__dirname, 'fixtures/marketing-renderer-worker.mjs');
const routes = ['index.html', 'beta/index.html', 'privacy/index.html', 'terms/index.html', 'auth/turnstile/index.html'];
const publicFiles = ['og.png', 'robots.txt', 'peso-logo.png', 'favicon.png', 'demo/peso-demo-thumbnail.jpg',
  'demo/peso-pose-overlay.jpg', 'demo/peso-demo-captions.vtt', 'demo/peso-pin-assisted-bar-path.jpg',
  'auth/turnstile.css', 'auth/turnstile.js'];
const weights = [['archivo-black', '400'], ['inter', '400'], ['inter', '500'], ['inter', '600'], ['inter', '700']];
// Reviewed font data identities. Updating fonts requires reviewing these inputs again.
const fontHashes = {
  'archivo-black/package.json': 'b969a21a9af6391476f6c3afe7c568c310b57e9a5c006060d653b2cb31eab961',
  'archivo-black/LICENSE': '4cafdbbd100af37a23805af09b7068e4daafb4516dc3d6d52436f4a9d7b4c0d3',
  'archivo-black/latin-400.css': '84bc295cea0810467380e14b14b872d11c1416c97ff128019620a9bffd00572a',
  'archivo-black/files/archivo-black-latin-400-normal.woff2': '25f33e61cf995abd6be62931cf03bf427286259177b43618cc410ee0157cfd30',
  'archivo-black/files/archivo-black-latin-400-normal.woff': 'd02e2312fd11842ead4e6de49733501d34f6980dbebf5807798eafe7dc3d648e',
  'inter/package.json': '05d03ec21754e37cf7da007c840e2f0a893c8161a53ee782d7c810e8a99c7cc5',
  'inter/LICENSE': '3b0a5fca3d17942cde889069889dedbbbd075e9b599968c82a95f4d944e9b345',
  'inter/latin-400.css': 'eb41eb009167dd65cd4df39a1d7393a2dc6ad47902d0e7937308fefc220696a1',
  'inter/latin-500.css': '7479efd8b62c928da8479ddbfc16d91f03dc642bcf4efa352b33dd999c4a9dd2',
  'inter/latin-600.css': 'c92c8c91f287e48c0d93b237e3d27f216b6cf8e643b54bc522f99751d7238fce',
  'inter/latin-700.css': '82667c4096262f9f05e920664afa9ae2d342fa1ac1fd9849cce7a64de66475b7',
  'inter/files/inter-latin-400-normal.woff2': '8909904ab6c872eb994093482a88a28eca2cd95912d7b6fecd72103b0dc07edc',
  'inter/files/inter-latin-400-normal.woff': 'e20fa0b4fd2dd26e4d14b3ac3cc922509c3a63fa5e910e90c614544aa042dd45',
  'inter/files/inter-latin-500-normal.woff2': 'f3779f1efccc4bdcdf9c0a02ab95bf6bd092ed09c48c08cedc725889edd1d19f',
  'inter/files/inter-latin-500-normal.woff': '9b42c108da48b5ed55a3072e815ffee2d271562e6c0dd6998910e8f9c09e0a3d',
  'inter/files/inter-latin-600-normal.woff2': 'f9a06e79cd3a2a20951c0f0e28f66dd0e6d3fda73911d640a2125c8fcb78f21a',
  'inter/files/inter-latin-600-normal.woff': '6a9cb3a509b4eeaf12b7dda6c4aacac3e85d07f4201bf4dd716e332e692b87bd',
  'inter/files/inter-latin-700-normal.woff2': '6f56409fd3d64bb85f7d070bce20749db2d66b6d63cec586cc22d1c761be2491',
  'inter/files/inter-latin-700-normal.woff': '7c5ed5655730de337704d3fc94628515cd7e3d8d32368871709bf56ac0397e7a',
};
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const input = (root, name) => fs.readFileSync(path.join(root, name));
function put(root, name, bytes) {
  fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
  fs.writeFileSync(path.join(root, name), bytes);
}
function tree(root) {
  const result = {};
  function walk(directory, prefix = '') {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const relative = prefix + entry.name;
      if (entry.isDirectory()) walk(path.join(directory, entry.name), `${relative}/`);
      else result[relative] = entry.isSymbolicLink() ? `symlink:${fs.readlinkSync(path.join(directory, entry.name))}`
        : digest(fs.readFileSync(path.join(directory, entry.name)));
    }
  }
  if (fs.existsSync(root)) walk(root);
  return result;
}
function fixture() {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'peso-renderer-test-')));
  try {
    for (const name of ['web/build.mjs', 'web/package.json', 'assets/demo/peso-pose-overlay.mp4']) put(root, name, input(project, name));
    fs.cpSync(path.join(project, 'web/src'), path.join(root, 'web/src'), { recursive: true });
    for (const name of publicFiles) put(root, `web/public/${name}`, input(project, `web/public/${name}`));
    for (const [name, expected] of Object.entries(fontHashes)) {
      const bytes = input(project, `web/node_modules/@fontsource/${name}`);
      assert.equal(digest(bytes), expected, `Reviewed font data changed: ${name}`);
      put(root, `web/node_modules/@fontsource/${name}`, bytes);
    }
    return root;
  } catch (error) { fs.rmSync(root, { recursive: true, force: true }); throw error; }
}
function withFixture(callback) {
  const root = fixture();
  try { return callback(root); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
function run(root, args, environment = {}) {
  const result = spawnSync(process.execPath, args, {
    cwd: root, env: { PATH: path.dirname(process.execPath), HOME: root, TMPDIR: os.tmpdir(), TZ: 'UTC', ...environment },
    encoding: 'utf8', timeout: 15000, maxBuffer: 8 * 1024 * 1024,
  });
  assert.ifError(result.error);
  assert.equal(result.signal, null, result.stderr);
  return result;
}
function prepared(root, environment = {}) {
  const result = run(root, [worker, root, 'prepare'], environment);
  assert.equal(result.status, 0, result.stderr);
  return new Map(JSON.parse(result.stdout).map(([name, bytes]) => [name, Buffer.from(bytes, 'base64')]));
}
function rejectedPreparation(root, environment = {}, expected) {
  const before = tree(root);
  const result = run(root, [worker, root, 'prepare'], environment);
  assert.notEqual(result.status, 0, 'Preparation should reject this input');
  if (expected) assert.match(result.stderr, expected);
  assert.deepEqual(tree(root), before, 'Preparation must not change fixture bytes');
}
function cli(root, args = [], environment = {}) { return run(root, [worker, root, 'cli', ...args], environment); }
function text(files, name) { assert.ok(files.has(name), name); return files.get(name).toString('utf8'); }
function hashed(name, bytes) {
  const extension = path.posix.extname(name);
  return `marketing-assets/${path.posix.basename(name, extension)}.${digest(bytes)}${extension}`;
}
function sameFiles(actual, expected) {
  assert.deepEqual([...actual.keys()].sort(), [...expected.keys()].sort());
  for (const [name, bytes] of expected) assert.deepEqual(actual.get(name), bytes, name);
}
function assertRoutes(files) { assert.deepEqual([...files.keys()].filter(name => name.endsWith('.html')).sort(), [...routes].sort()); }

// Each named case uses fresh worker processes and owned, disposable inputs/output.
test('R01 Default marketing output map', () => withFixture(root => {
  const before = tree(root);
  const files = prepared(root);
  assertRoutes(files);
  for (const name of routes.slice(0, 4)) {
    const html = text(files, name);
    assert.match(html, /<header class="site-header/);
    assert.match(html, /<footer class="site-footer">/);
    assert.match(html, /href="\/beta">Beta coming soon<\/a>/);
    assert.doesNotMatch(html, /href="\/app\/signup"/);
    assert.match(html, /2026 Peso\. Beta coming soon\./);
  }
  assert.match(text(files, 'index.html'), /signup, uploads, and analysis are unavailable/);
  assert.match(text(files, 'beta/index.html'), /Signup, sign-in, video uploads, and analysis are unavailable/);
  for (const name of ['privacy/index.html', 'terms/index.html']) {
    assert.match(text(files, name), /informational preview only/);
    assert.match(text(files, name), /Signup, uploads, analysis, and email collection are unavailable/);
  }
  assert.deepEqual(tree(root), before);
}));

test('R02 Private beta output map', () => withFixture(root => {
  const files = prepared(root, { PESO_WEB_BUILD: 'private-beta' });
  assertRoutes(files);
  for (const name of routes.slice(0, 4)) {
    assert.match(text(files, name), /href="\/app\/signup">Sign up for the beta<\/a>/);
    assert.match(text(files, name), /2026 Peso\. Public web beta\./);
  }
  assert.match(text(files, 'index.html'), /Side-view squats · US-IP signup/);
  assert.match(text(files, 'index.html'), /Create an account to upload a side-view squat video/);
  for (const name of ['privacy/index.html', 'terms/index.html']) {
    const html = text(files, name);
    assert.match(html, /Signup for the web beta requires a US IP address and email verification/);
    assert.match(html, /Signed-in users can upload side-view squat videos for private analysis, including while abroad/);
    assert.doesNotMatch(html, /informational preview only|Signup, uploads, analysis, and email collection are unavailable/);
    assert.match(html, /Beta draft for professional review/);
    assert.match(html, /href="mailto:support@usepeso\.com"/);
  }
  assert.equal(fs.existsSync(path.join(root, 'dist')), false);
}));

test('R03 Canonical and social metadata', () => withFixture(root => {
  for (const [environment, origin] of [[{}, undefined], [{ URL: 'http://example.test/ignored' }, 'http://example.test'],
    [{ URL: 'https://other.test', DEPLOY_PRIME_URL: 'https://preview.test/prefix' }, 'https://preview.test']]) {
    const files = prepared(root, environment);
    for (const [index, route] of ['/', '/beta/', '/privacy/', '/terms/'].entries()) {
      const html = text(files, routes[index]);
      if (!origin) assert.doesNotMatch(html, /rel="canonical"|property="og:url"|property="og:image"|name="twitter:image"/);
      else {
        assert.ok(html.includes(`<link rel="canonical" href="${origin}${route}" />`));
        assert.ok(html.includes(`<meta property="og:url" content="${origin}${route}" />`));
        assert.ok(html.includes(`<meta property="og:image" content="${origin}/og.png" />`));
        assert.ok(html.includes(`<meta name="twitter:image" content="${origin}/og.png" />`));
      }
    }
  }
}));

test('R04 Unknown build mode', () => {
  for (const PESO_WEB_BUILD of ['unknown', '']) withFixture(root => rejectedPreparation(root, { PESO_WEB_BUILD }, /Unknown marketing build mode/));
});

test('R05 Invalid deployment URL', () => {
  for (const URL of ['not a URL', 'file:///tmp/site', 'ftp://example.test', 'https://user:password@example.test']) {
    withFixture(root => rejectedPreparation(root, { URL }, /Invalid URL|HTTP\(S\) URL without credentials/));
  }
});

test('R06 Escaping and nonrecursive substitution', () => withFixture(root => {
  const files = prepared(root, { EXPO_PUBLIC_TURNSTILE_SITE_KEY: `a&<>"'{{UNKNOWN_MARKER}}` });
  assert.ok(text(files, 'auth/turnstile/index.html').includes('data-site-key="a&amp;&lt;&gt;&quot;&#39;{{UNKNOWN_MARKER}}"'));
}));

test('R07 Template marker rejection', () => {
  for (const marker of ['{{UNKNOWN_MARKER}}', '{{lowercase}}', '{{BROKEN', 'BROKEN}}']) withFixture(root => {
    const name = 'web/src/pages/index.html';
    const valid = input(root, name);
    put(root, name, Buffer.concat([valid, Buffer.from(marker)]));
    rejectedPreparation(root, {}, /Unknown template marker|Malformed template marker/);
    put(root, name, valid);
    assertRoutes(prepared(root));
  });
});

test('R08 Local asset identity and references', () => withFixture(root => {
  const files = prepared(root);
  assert.equal(files.size, 29);
  for (const name of publicFiles) assert.deepEqual(files.get(name), input(root, `web/public/${name}`), name);
  const styles = [];
  for (const [family, weight] of weights) {
    let css = input(root, `web/node_modules/@fontsource/${family}/latin-${weight}.css`).toString('utf8');
    for (const extension of ['woff2', 'woff']) {
      const name = `${family}-latin-${weight}-normal.${extension}`;
      const bytes = input(root, `web/node_modules/@fontsource/${family}/files/${name}`);
      const output = hashed(name, bytes);
      assert.deepEqual(files.get(output), bytes, output);
      css = css.replace(`url(./files/${name})`, `url(/${output})`);
    }
    styles.push(css);
  }
  assert.equal([...files.keys()].filter(name => /\.woff2?$/.test(name)).length, 10);
  const cssBytes = Buffer.from([...styles, input(root, 'web/src/styles/global.css').toString('utf8')].join('\n'));
  const cssName = hashed('site.css', cssBytes);
  assert.deepEqual(files.get(cssName), cssBytes);
  for (const match of cssBytes.toString().matchAll(/url\(([^)]+)\)/g)) {
    assert.match(match[1], /^\/marketing-assets\/.+\.[a-f0-9]{64}\.woff2?$/);
    assert.ok(files.has(match[1].slice(1)));
  }
  const licenses = ['archivo-black', 'inter'].map(family => `@fontsource/${family}\n${input(root, `web/node_modules/@fontsource/${family}/LICENSE`).toString('utf8')}`).join('\n\n');
  assert.equal(text(files, hashed('font-licenses.txt', Buffer.from(licenses))), licenses);
  for (const [name, source] of [['peso-pose-overlay.mp4', 'assets/demo/peso-pose-overlay.mp4'], ['demo-video.js', 'web/src/scripts/demo-video.js']]) {
    const bytes = input(root, source);
    const output = hashed(name, bytes);
    assert.deepEqual(files.get(output), bytes);
    const attribute = name.endsWith('.mp4') ? 'data-src' : 'src';
    assert.ok(text(files, 'index.html').includes(`${attribute}="/${output}"`), `Emitted ${attribute} must resolve ${output}`);
  }
  for (const name of routes.slice(0, 4)) assert.ok(text(files, name).includes(`href="/${cssName}"`));
}));

test('R09 Font package identity', () => {
  for (const family of ['archivo-black', 'inter']) for (const variant of ['malformed', 'name', 'version']) withFixture(root => {
    const name = `web/node_modules/@fontsource/${family}/package.json`;
    const valid = input(root, name);
    const data = JSON.parse(valid);
    if (variant !== 'malformed') data[variant] = variant === 'name' ? '@fontsource/unreviewed' : '0.0.0';
    put(root, name, variant === 'malformed' ? '{' : JSON.stringify(data));
    rejectedPreparation(root, {}, /JSON|Expected reviewed/);
    put(root, name, valid);
    assertRoutes(prepared(root));
  });
});

test('R10 Font CSS mapping boundary', () => {
  for (const variant of ['missing', 'duplicate', 'third', 'external', 'import']) withFixture(root => {
    const name = 'web/node_modules/@fontsource/inter/latin-500.css';
    const original = input(root, name).toString('utf8');
    const url = 'url(./files/inter-latin-500-normal.woff2)';
    const modified = {
      missing: original.replace(url, 'none'), duplicate: original + `\na{src:${url}}`,
      third: original + '\na{src:url(/unexpected.woff)}',
      external: original.replace(url, 'url(https://external.test/font.woff2)'),
      import: original + '\n@import "https://external.test/fonts.css";',
    }[variant];
    put(root, name, modified);
    rejectedPreparation(root, {}, /Unexpected font stylesheet|Unmapped font resource/);
    put(root, name, original);
    assertRoutes(prepared(root));
  });
});

test('R11 Required input types', () => {
  for (const name of ['web/src/pages/index.html', 'web/public/og.png', 'web/node_modules/@fontsource/inter/files/inter-latin-400-normal.woff2']) {
    for (const variant of ['missing', 'directory']) withFixture(root => {
      fs.rmSync(path.join(root, name));
      if (variant === 'directory') fs.mkdirSync(path.join(root, name));
      rejectedPreparation(root, {}, /ENOENT|Expected a regular file/);
    });
  }
});

test('R12 Input symlink rejection', () => {
  for (const name of ['web/src/pages/index.html', 'web/public/og.png', 'web/node_modules/@fontsource/inter/files/inter-latin-400-normal.woff2', 'web/src/components']) {
    withFixture(root => {
      const outside = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-renderer-sentinel-'));
      try {
        put(outside, 'sentinel', 'external sentinel unchanged');
        const source = path.join(root, name);
        const target = path.join(outside, 'replacement');
        fs.renameSync(source, target);
        fs.symlinkSync(target, source);
        const before = tree(outside);
        rejectedPreparation(root, {}, /Symlink is not allowed/);
        assert.deepEqual(tree(outside), before);
      } finally { fs.rmSync(outside, { recursive: true, force: true }); }
    });
  }
});

test('R13 CLI check is read-only', () => {
  for (const existing of [false, true]) withFixture(root => {
    if (existing) put(root, 'dist/stale.txt', 'do not change');
    const before = tree(root);
    const result = cli(root, ['--check']);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /five pages, 29 planned files; no files written/);
    assert.deepEqual(tree(root), before);
    assert.equal(fs.existsSync(path.join(root, 'dist')), existing);
  });
});

test('R14 CLI build replaces stale output', () => withFixture(root => {
  const expected = prepared(root);
  put(root, 'dist/app/stale.js', 'stale app');
  put(root, 'dist/auth/stale.html', 'stale neighbor');
  const result = cli(root);
  assert.equal(result.status, 0, result.stderr);
  const output = tree(path.join(root, 'dist'));
  assert.deepEqual(Object.keys(output).sort(), [...expected.keys()].sort());
  for (const [name, bytes] of expected) assert.deepEqual(input(root, `dist/${name}`), bytes, name);
}));

test('R15 Preparation failure cleans owned output', () => withFixture(root => {
  put(root, 'dist/app/stale.js', 'stale');
  fs.rmSync(path.join(root, 'web/public/og.png'));
  const result = cli(root);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /ENOENT/);
  assert.equal(fs.existsSync(path.join(root, 'dist')), false);
}));

test('R16 Write failure cleans partial output', () => withFixture(root => {
  const result = run(root, [worker, root, 'fault-build']);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /after one successful owned output write/);
  assert.match(result.stderr, /Injected owned output failure/);
  assert.equal(fs.existsSync(path.join(root, 'dist')), false);
  const control = cli(root);
  assert.equal(control.status, 0, control.stderr);
  assert.equal(Object.keys(tree(path.join(root, 'dist'))).length, 29);
}));

test('R17 Output symlink is refused', () => {
  for (const preparationFailure of [false, true]) withFixture(root => {
    const outside = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-output-sentinel-'));
    try {
      put(outside, 'sentinel', 'outside output stays unchanged');
      fs.symlinkSync(outside, path.join(root, 'dist'));
      if (preparationFailure) fs.rmSync(path.join(root, 'web/public/og.png'));
      const before = tree(outside);
      const result = cli(root);
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /Symlink is not allowed: dist/);
      assert.equal(fs.lstatSync(path.join(root, 'dist')).isSymbolicLink(), true);
      assert.deepEqual(tree(outside), before);
    } finally { fs.rmSync(outside, { recursive: true, force: true }); }
  });
});

test('R18 CLI argument boundary', () => {
  for (const args of [['--unknown'], ['--check', 'extra']]) withFixture(root => {
    put(root, 'dist/sentinel', 'preserve on usage error');
    const before = tree(root);
    const result = cli(root, args);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Usage: node build\.mjs \[--check\]/);
    assert.deepEqual(tree(root), before);
  });
});

test('R19 Public key trimming and environment isolation', () => withFixture(root => {
  for (const [key, expected] of [[undefined, ''], ['  \t ', ''], ['  public-key \n', 'public-key']]) {
    const environment = { UNRELATED_PRIVATE_SECRET: 'NEVER_EMIT_TEST_SECRET_7c2839' };
    if (key !== undefined) environment.EXPO_PUBLIC_TURNSTILE_SITE_KEY = key;
    const files = prepared(root, environment);
    assert.ok(text(files, 'auth/turnstile/index.html').includes(`data-site-key="${expected}"`));
    for (const bytes of files.values()) assert.equal(bytes.includes(Buffer.from(environment.UNRELATED_PRIVATE_SECRET)), false);
  }
}));

test('R20 Repeatable output for fixed inputs', () => {
  for (const mode of ['marketing', 'private-beta']) withFixture(first => withFixture(second => {
    const environment = { PESO_WEB_BUILD: mode };
    const before = prepared(first, environment);
    const equal = prepared(second, environment);
    sameFiles(before, equal);
    const source = 'assets/demo/peso-pose-overlay.mp4';
    const oldBytes = input(second, source);
    const changedBytes = Buffer.from(oldBytes);
    changedBytes[changedBytes.length - 1] ^= 1;
    put(second, source, changedBytes);
    const changed = prepared(second, environment);
    const oldName = hashed('peso-pose-overlay.mp4', oldBytes);
    const newName = hashed('peso-pose-overlay.mp4', changedBytes);
    assert.equal(changed.has(oldName), false);
    assert.deepEqual(changed.get(newName), changedBytes);
    assert.ok(text(changed, 'index.html').includes(`"/${newName}"`));
    assert.ok(text(before, 'index.html').includes(`"/${oldName}"`));
    const changedPaths = [...new Set([...before.keys(), ...changed.keys()])].filter(name => !before.has(name) || !changed.has(name) || !before.get(name).equals(changed.get(name))).sort();
    assert.deepEqual(changedPaths, ['index.html', oldName, newName].sort());
  }));
});
