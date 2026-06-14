const assert = require('node:assert/strict');
const test = require('node:test');

const {
  FRAME_CHANGE_EPSILON_SECONDS,
  getPinnedFrameChangeAction,
} = require('../lib/trackingPinFramePolicy');

test('scrubbing with no pins changes frames without confirmation', () => {
  assert.equal(
    getPinnedFrameChangeAction({
      pinCount: 0,
      pinnedFrameTime: null,
      targetTime: 1.25,
      suppressWarning: false,
    }),
    'accept'
  );
});

test('scrubbing placed pins to another frame requires confirmation', () => {
  assert.equal(
    getPinnedFrameChangeAction({
      pinCount: 1,
      pinnedFrameTime: 0.5,
      targetTime: 1.25,
      suppressWarning: false,
    }),
    'confirm_reset'
  );
});

test('suppressed warning clears pins and accepts the new frame immediately', () => {
  assert.equal(
    getPinnedFrameChangeAction({
      pinCount: 5,
      pinnedFrameTime: 0.5,
      targetTime: 1.25,
      suppressWarning: true,
    }),
    'reset_and_accept'
  );
});

test('scrubbing within the same frame does not clear pins', () => {
  assert.equal(
    getPinnedFrameChangeAction({
      pinCount: 3,
      pinnedFrameTime: 0.5,
      targetTime: 0.5 + (FRAME_CHANGE_EPSILON_SECONDS / 2),
      suppressWarning: false,
    }),
    'restore_pinned_frame'
  );
});
