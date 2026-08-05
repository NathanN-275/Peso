const assert = require('node:assert/strict');
const test = require('node:test');

const { resolveByteRange } = require('../lib/httpRangePolicy');

test('byte range policy resolves bounded and open-ended media ranges', () => {
  assert.deepEqual(resolveByteRange('bytes=0-999', 5_000), { start: 0, end: 999 });
  assert.deepEqual(resolveByteRange('bytes=1000-', 5_000), { start: 1_000, end: 4_999 });
});

test('byte range policy resolves suffix ranges', () => {
  assert.deepEqual(resolveByteRange('bytes=-500', 5_000), { start: 4_500, end: 4_999 });
});

test('byte range policy rejects invalid and unsatisfiable ranges', () => {
  assert.equal(resolveByteRange('items=0-10', 5_000), null);
  assert.equal(resolveByteRange('bytes=5000-', 5_000), null);
  assert.equal(resolveByteRange('bytes=10-5', 5_000), null);
});
