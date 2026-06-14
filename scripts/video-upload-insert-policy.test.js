const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getVideoInsertRetryMode,
  omitLegacyStorageMetadata,
} = require('../lib/videoUploadInsertPolicy');
const { withOptionalTrackingSetup } = require('../lib/videoUploadPayload');

test('automatic uploads omit tracking_setup', () => {
  assert.deepEqual(
    withOptionalTrackingSetup({ id: 'video-1' }, null),
    { id: 'video-1' }
  );
});

test('pin-assisted uploads retain the complete tracking_setup payload', () => {
  const trackingSetup = {
    version: 1,
    reference_time_ms: 250,
    barbell_target: 'near_side_collar',
    anchors: {
      shoulder: { x: 0.4, y: 0.2 },
      hip: { x: 0.4, y: 0.4 },
      knee: { x: 0.4, y: 0.6 },
      ankle: { x: 0.4, y: 0.8 },
      barbell: { x: 0.6, y: 0.2 },
    },
  };

  assert.deepEqual(
    withOptionalTrackingSetup({ id: 'video-1' }, trackingSetup),
    { id: 'video-1', tracking_setup: trackingSetup }
  );
});

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
