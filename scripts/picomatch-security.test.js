const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const vm = require('node:vm');
const fs = require('node:fs');
const os = require('node:os');

const root = path.resolve(__dirname, '..');
const copies = [
  'node_modules/picomatch',
  'node_modules/anymatch/node_modules/picomatch',
  'node_modules/jest-util/node_modules/picomatch',
  'node_modules/micromatch/node_modules/picomatch',
  'node_modules/readdirp/node_modules/picomatch',
];
const unsafe = ['+(*)x', '+(*a)x', '*(*a)x', '*(a*)x', '+([ab]*)x',
  '+(@(*a))x', '+((*a))x', '+(a+)x', '+(a?(b))x', '+(*a|b)x',
  '+(@(a|aa))x', '+((a|aa))x', '+({a,aa})x', '+(ab|abab)x'];
const rejected = /Unsafe nested repetition in extglob/;

for (const copy of copies) {
  const pm = require(path.join(root, copy));
  test(`${copy} rejects nested variable repetition before regex execution`, () => {
    for (const options of [{}, { capture: true }, { windows: true }, { bash: true },
      { fastpaths: false }, { maxExtglobRecursion: false }]) {
      for (const pattern of unsafe) assert.throws(() => pm.makeRe(pattern, options), rejected, pattern);
    }
  });

  test(`${copy} protects public, direct parser, array and ignore entry points`, () => {
    const parse = require(path.join(root, copy, 'lib/parse'));
    const posix = fs.existsSync(path.join(root, copy, 'posix.js'))
      ? require(path.join(root, copy, 'posix')) : pm;
    for (const pattern of unsafe.slice(0, 7)) {
      for (const compile of [p => pm(p), p => posix(p), p => pm([p]),
        p => pm('**/*', { ignore: p }), p => pm.parse(p), p => parse(p),
        p => pm.compileRe(pm.parse(p)), p => pm(p, { noext: false })]) {
        assert.throws(() => compile(pattern), rejected, pattern);
      }
    }
  });

  test(`${copy} preserves ordinary globs, finite extglobs, captures and literal syntax`, () => {
    for (const [pattern, input] of [['**/*.ts', 'app/test.ts'], ['*.{js,tsx}', 'a.tsx'],
      ['+(foo|bar).js', 'foobar.js'], ['*(foo).js', 'foofoo.js'], ['a[bc].js', 'ab.js'],
      ['a?.js', 'ab.js'], ['a\\*.js', 'a*.js'], ['"*".js', '*.js'],
      ['**/!(*.d).ts', 'app/test.ts']]) {
      const re = pm.makeRe(pattern);
      assert.equal(vm.runInNewContext('re.test(input)', { re, input }, { timeout: 250 }), true, pattern);
      assert.equal(pm.compileRe(pm.parse(pattern)).test(input), true, pattern);
    }
    assert.deepEqual(pm.makeRe('+(foo|bar).js', { capture: true }).exec('foobar.js').slice(1), ['foobar']);
    assert.equal(pm.isMatch('app/test.d.ts', '**/!(*.d).ts'), false);
    assert.equal(pm.isMatch('+(a|a)x', '+(a|a)x'), true);
    assert.equal(pm.isMatch('aax', '+(a|a)x'), false);
    assert.throws(() => pm.makeRe('+(a|a)x', { maxExtglobRecursion: false }), rejected);
    assert.throws(() => pm.parse('+(A|aa)x'), rejected);
    assert.equal(pm.isMatch('+(*a)x', '"+(*a)x"'), true);
    assert.equal(pm.isMatch('+(*a)x', '\\+\\(\\*a\\)x'), true);
    assert.doesNotThrow(() => pm.makeRe('+(*a)x', { noextglob: true }));
  });
}

test('micromatch, anymatch and Jest reject unsafe filters and preserve normal matching', () => {
  const mm = require('micromatch');
  const anymatch = require('anymatch');
  const { globsToMatcher } = require('jest-util');
  assert.throws(() => mm.makeRe('+(*a)x'), rejected);
  assert.throws(() => mm.matcher('+(*a)x'), rejected);
  assert.throws(() => anymatch('+(*a)x', 'aax'), rejected);
  assert.throws(() => globsToMatcher(['+(*a)x'])('aax'), rejected);
  assert.deepEqual(mm(['app/a.ts', 'app/b.js', 'app/c.tsx'], '**/*.{ts,tsx}'), ['app/a.ts', 'app/c.tsx']);
  assert.deepEqual(mm.capture('+(foo|bar).js', 'foobar.js'), ['foobar']);
  assert.equal(anymatch('**/*.ts', 'app/a.ts'), true);
  assert.equal(globsToMatcher(['**/*.ts', '!**/*.d.ts'])('app/a.ts'), true);
});

test('the proposed finite-body restriction explicitly rejects unsupported legitimate forms', () => {
  // This compatibility restriction requires Nathan's approval; it is not a claim of exploitability.
  for (const copy of copies) {
    const pm = require(path.join(root, copy));
    for (const pattern of ['+(a?(b)).js', '+(@(foo)).js', '+(a[bc]).js', '+(a?).js', '+(a\\*).js', '+("*").js']) {
      assert.throws(() => pm.makeRe(pattern), rejected, pattern);
    }
  }
});

test('readdirp rejects unsafe file filters and preserves ordinary walking', async t => {
  const readdirp = require('readdirp');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-picomatch-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.writeFileSync(path.join(dir, 'a.ts'), '');
  fs.writeFileSync(path.join(dir, 'b.js'), '');
  assert.throws(() => readdirp(dir, { fileFilter: '+(*a)x' }), rejected);
  const files = await readdirp.promise(dir, { fileFilter: '*.ts' });
  assert.deepEqual(files.map(file => file.basename), ['a.ts']);
});
