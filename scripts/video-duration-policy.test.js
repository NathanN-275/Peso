const assert = require('node:assert/strict');
const test = require('node:test');

const {
  clampTrackingReferenceTimeMs,
  normalizePositiveDurationMs,
  resolveVideoDurationMs,
} = require('../lib/videoDurationPolicy');

test('zero and invalid picker durations are treated as unknown', () => {
  assert.equal(normalizePositiveDurationMs(0), null);
  assert.equal(normalizePositiveDurationMs(Number.NaN), null);
  assert.equal(normalizePositiveDurationMs(null), null);
});

test('player duration wins over picker duration', () => {
  assert.equal(
    resolveVideoDurationMs({
      playerDurationSeconds: 15.788345,
      pickerDurationMs: 0,
    }),
    15788
  );
  assert.equal(
    resolveVideoDurationMs({
      playerDurationSeconds: 12.5,
      pickerDurationMs: 13000,
    }),
    12500
  );
});

test('picker duration is used when player metadata is unavailable', () => {
  assert.equal(
    resolveVideoDurationMs({
      playerDurationSeconds: 0,
      pickerDurationMs: 15788,
    }),
    15788
  );
  assert.equal(
    resolveVideoDurationMs({
      playerDurationSeconds: Number.NaN,
      pickerDurationMs: 0,
    }),
    null
  );
});

test('tracking reference time is clamped to the resolved duration', () => {
  assert.equal(clampTrackingReferenceTimeMs(16, 15788), 15788);
  assert.equal(clampTrackingReferenceTimeMs(-1, 15788), 0);
  assert.equal(clampTrackingReferenceTimeMs(5.1234, null), 5123);
});
