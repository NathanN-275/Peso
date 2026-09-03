const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getBackendErrorMessage,
  getVideoSubmissionFailureMessage,
} = require('../lib/backendErrorPolicy');

test('FastAPI detail errors are shown without raw JSON', () => {
  assert.equal(
    getBackendErrorMessage('{"detail":"Unsupported camera view."}', 400),
    'Unsupported camera view.'
  );
});

test('out-of-bounds pin timestamps get an actionable message', () => {
  assert.equal(
    getBackendErrorMessage(
      '{"detail":"Invalid tracking setup: reference_time_out_of_bounds."}',
      400
    ),
    'The saved pin frame is outside this video. Reopen Edit Pins and choose a frame inside the clip.'
  );
});

test('unreadable video errors explain how to recover', () => {
  assert.equal(
    getBackendErrorMessage(
      '{"detail":"Uploaded file contents do not contain a valid video stream."}',
      400
    ),
    'Peso couldn’t read this video. Export the clip again as MP4 or choose another video, then try again.'
  );
});

test('preflight failures survive cleanup while queue failures keep the generic message', () => {
  const detail = 'Video validation is temporarily unavailable. Please try again.';

  assert.equal(getVideoSubmissionFailureMessage('quality_preflight', detail), detail);
  assert.equal(
    getVideoSubmissionFailureMessage('queue_analysis', detail),
    'Upload succeeded, but analysis could not start. The upload was cleaned up; please try again.'
  );
});

test('plain-text and empty errors preserve useful fallbacks', () => {
  assert.equal(getBackendErrorMessage('Service unavailable', 503), 'Service unavailable');
  assert.equal(
    getBackendErrorMessage('', 500),
    'Backend request failed with status 500.'
  );
});
