const assert = require('node:assert/strict');
const test = require('node:test');

const { getBackendErrorMessage } = require('../lib/backendErrorPolicy');

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

test('plain-text and empty errors preserve useful fallbacks', () => {
  assert.equal(getBackendErrorMessage('Service unavailable', 503), 'Service unavailable');
  assert.equal(
    getBackendErrorMessage('', 500),
    'Backend request failed with status 500.'
  );
});
