const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getVideoInsertRetryMode,
} = require('../lib/videoUploadInsertPolicy');

test('missing tracking_setup blocks pin-assisted uploads', () => {
  assert.equal(
    getVideoInsertRetryMode(
      'column videos.tracking_setup does not exist',
      true
    ),
    'tracking_unavailable'
  );
});

test('missing storage metadata retries without dropping tracking_setup', () => {
  assert.equal(
    getVideoInsertRetryMode(
      'column videos.original_size_bytes does not exist',
      true
    ),
    'retry_without_storage_metadata'
  );
});

test('unrelated insert errors do not retry', () => {
  assert.equal(
    getVideoInsertRetryMode('row violates row-level security policy', true),
    'fail'
  );
});
