const assert = require('node:assert/strict');
const test = require('node:test');

const {
  buildExpoStartArgs,
  parseStartOptions,
} = require('./start-dev-options');

test('development startup preserves Metro cache by default', () => {
  const options = parseStartOptions([]);

  assert.deepEqual(options, {
    startWeb: false,
    clearMetroCache: false,
  });
  assert.deepEqual(buildExpoStartArgs(options), ['start']);
});

test('development startup supports web and explicit Metro cache clearing', () => {
  const options = parseStartOptions(['--web', '--clear']);

  assert.deepEqual(options, {
    startWeb: true,
    clearMetroCache: true,
  });
  assert.deepEqual(buildExpoStartArgs(options), ['start', '--web', '--clear']);
});

test('development startup accepts the short clear option', () => {
  const options = parseStartOptions(['-c']);

  assert.equal(options.clearMetroCache, true);
  assert.deepEqual(buildExpoStartArgs(options), ['start', '--clear']);
});
