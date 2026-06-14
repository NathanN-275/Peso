const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getVideoInsertRetryMode,
  omitLegacyStorageMetadata,
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

  const trackingSetup = { version: 1, anchors: {} };
  const retryPayload = omitLegacyStorageMetadata({
    id: 'video-1',
    storage_state: 'available',
    original_size_bytes: 10,
    uploaded_size_bytes: 9,
    was_compressed: true,
    tracking_setup: trackingSetup,
  });
  assert.deepEqual(retryPayload, {
    id: 'video-1',
    tracking_setup: trackingSetup,
  });
});

test('unrelated insert errors do not retry', () => {
  assert.equal(
    getVideoInsertRetryMode('row violates row-level security policy', true),
    'fail'
  );
});
