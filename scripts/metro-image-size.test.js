const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const test = require('node:test');
const rootRequire = createRequire(path.join(__dirname, '../package.json'));
const metroPackage = rootRequire.resolve('metro/package.json');
const metroRequire = createRequire(metroPackage);
const assets = metroRequire(path.join(path.dirname(metroPackage), 'src/Assets.js'));
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5X8AAAAASUVORK5CYII=', 'base64');
function fixture(t) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'peso-metro-image-')));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}
function file(dir, name, bytes) {
  const filename = path.join(dir, name);
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  fs.writeFileSync(filename, bytes);
  return filename;
}
const getData = filename => assets.getAssetData(filename, path.basename(filename), [], 'web', '/assets');

test('Metro resolves official image-size 2.0.4 through its scoped override', () => {
  assert.equal(metroRequire('./package.json').version, '0.84.4');
  const entry = metroRequire.resolve('image-size');
  const metadata = JSON.parse(fs.readFileSync(path.resolve(path.dirname(entry), '../../package.json')));
  assert.equal(metadata.name, 'image-size');
  assert.equal(metadata.version, '2.0.4');
  assert.equal(typeof metroRequire('image-size/fromFile').imageSizeFromFile, 'function');
});

test('Metro getAssetSize preserves synchronous buffer dimensions and non-image behavior', () => {
  assert.deepEqual(assets.getAssetSize('png', png, 'fixture.png'), { width: 1, height: 1 });
  assert.equal(assets.getAssetSize('mp4', Buffer.alloc(0), 'fixture.mp4'), null);
  assert.throws(() => assets.getAssetSize('png', Buffer.alloc(0), 'empty.png'), /cannot be an empty file/);
  assert.throws(() => assets.getAssetSize('png', Buffer.from('not an image'), 'bad.png'));
});

test('Metro getAssetData reads regular filenames asynchronously and retains asset metadata', async t => {
  const dir = fixture(t);
  const filename = file(dir, 'pixel.png', png);
  const data = await getData(filename);
  assert.equal(data.width, 1);
  assert.equal(data.height, 1);
  assert.deepEqual(data.files, [filename]);
  assert.deepEqual(data.scales, [1]);
  assert.equal(data.name, 'pixel');
  assert.equal(data.type, 'png');
  assert.equal(data.__packager_asset, true);
  assert.equal(data.httpServerLocation, '/assets');
});

test('Metro filename parser preserves official 512 KiB read cap and closes the handle', async t => {
  const dir = fixture(t);
  const filename = file(dir, 'large.png', Buffer.concat([png, Buffer.alloc(600 * 1024)]));
  const originalOpen = fs.promises.open;
  let readLength;
  let closed = 0;
  fs.promises.open = async function (name, ...args) {
    const handle = await originalOpen.call(this, name, ...args);
    if (path.resolve(name) !== filename) return handle;
    const read = handle.read.bind(handle);
    const close = handle.close.bind(handle);
    handle.read = async function (bytes, offset, length, position) {
      readLength = length;
      return read(bytes, offset, length, position);
    };
    handle.close = async function () { closed += 1; return close(); };
    return handle;
  };
  try {
    const data = await getData(filename);
    assert.equal(data.width, 1);
    assert.equal(data.height, 1);
    assert.equal(readLength, 512 * 1024);
    assert.equal(closed, 1);
  } finally { fs.promises.open = originalOpen; }
});

test('Metro zip-marked path retains synchronous buffer parser branch', async t => {
  const dir = fixture(t);
  // A real owned directory exercises Metro's .zip/ branch; this is not a zip VFS implementation.
  const filename = file(dir, 'fixture.zip/pixel.png', png);
  const originalOpen = fs.promises.open;
  let fileParserOpened = false;
  fs.promises.open = async function (name, ...args) {
    if (path.resolve(name) === filename) fileParserOpened = true;
    return originalOpen.call(this, name, ...args);
  };
  try {
    const data = await getData(filename);
    assert.equal(data.width, 1);
    assert.equal(data.height, 1);
    assert.equal(fileParserOpened, false, 'zip-marked input must be parsed from its buffer');
  } finally { fs.promises.open = originalOpen; }
});

test('Metro preserves scaled dimensions and platform asset selection', async t => {
  const dir = fixture(t);
  const filename = file(dir, 'pixel@2x.web.png', png);
  const data = await getData(filename);
  assert.deepEqual(data.scales, [2]);
  assert.equal(data.width, 0.5);
  assert.equal(data.height, 0.5);
  assert.deepEqual(await assets.getAssetFiles(filename, 'web'), [filename]);
});

test('Metro propagates invalid and empty image failures for file and zip-buffer inputs', async t => {
  const dir = fixture(t);
  for (const prefix of ['', 'fixture.zip/']) {
    await assert.rejects(getData(file(dir, `${prefix}bad.png`, Buffer.from('invalid image'))));
    await assert.rejects(getData(file(dir, `${prefix}empty.png`, Buffer.alloc(0))));
  }
});

test('Metro non-image assets skip dimension parsing and preserve plugin processing', async t => {
  const dir = fixture(t);
  const filename = file(dir, 'fixture.txt', 'plain bytes');
  const plugin = file(dir, 'asset-plugin.cjs', 'module.exports = async asset => ({ ...asset, testedPlugin: true });\n');
  const data = await assets.getAssetData(filename, 'fixture.txt', [plugin], 'web', '/assets');
  assert.equal(data.width, undefined);
  assert.equal(data.height, undefined);
  assert.equal(data.testedPlugin, true);
  assert.equal(data.type, 'txt');
});
