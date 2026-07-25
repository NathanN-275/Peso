const assert = require('node:assert/strict');
const test = require('node:test');

const {
  frontTrailWindowFrames,
  shouldConnectFrontTrailSamples,
  shouldShowFrontMotionTrails,
} = require('../lib/frontTrackingPolicy');

test('front squat trails are enabled for every squat variation', () => {
  for (const exercise of ['Squat', 'Front Squat', 'Zercher Squat', 'Box Squat', 'Goblet Squat']) {
    assert.equal(shouldShowFrontMotionTrails({ cameraView: 'Front', exercise }), true);
  }
  assert.equal(shouldShowFrontMotionTrails({ cameraView: 'Side', exercise: 'Squat' }), false);
  assert.equal(shouldShowFrontMotionTrails({ cameraView: 'Front', exercise: 'Deadlift' }), false);
});

test('front trail history contains only the preceding second', () => {
  const frames = [0, 0.5, 1, 1.5, 2].map((time) => ({ time, keypoints: [] }));
  assert.deepEqual(
    frontTrailWindowFrames(frames, 2).map((frame) => frame.time),
    [1, 1.5, 2]
  );
});

test('front trails break across long pose gaps', () => {
  assert.equal(shouldConnectFrontTrailSamples(1, 1.19), true);
  assert.equal(shouldConnectFrontTrailSamples(1, 1.21), false);
});
