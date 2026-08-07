const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getSideSquatRecordingGuidance,
  isBarbellSideSquatSetup,
  isSideViewSquatSetup,
} = require('../lib/sideSquatRecordingGuidancePolicy');

const squatVariations = ['Squat', 'Front Squat', 'Zercher Squat', 'Box Squat', 'Goblet Squat'];

test('recording guidance is limited to side-view squat variations', () => {
  for (const exercise of squatVariations) {
    assert.equal(isSideViewSquatSetup({ exercise, angle: 'Side' }), true);
  }

  assert.equal(isSideViewSquatSetup({ exercise: 'Squat', angle: 'Front' }), false);
  assert.equal(isSideViewSquatSetup({ exercise: 'Deadlift', angle: 'Side' }), false);
  assert.equal(getSideSquatRecordingGuidance({ exercise: 'Bench Press', angle: 'Side' }), null);
});

test('barbell side squats receive every required recording rule', () => {
  const guidance = getSideSquatRecordingGuidance({ exercise: 'Squat', angle: 'Side' });
  const ids = guidance.items.map((item) => item.id);

  assert.equal(isBarbellSideSquatSetup({ exercise: 'Squat', angle: 'Side' }), true);
  assert.deepEqual(ids, [
    'phone_height',
    'distance_and_framing',
    'stationary_camera',
    'full_body',
    'barbell_collar',
    'clear_background',
    'lighting',
    'digital_zoom',
  ]);
  assert.match(guidance.compactSummary, /sleeve–plate interface/i);
});

test('Goblet Squat keeps body guidance and omits inapplicable collar instructions', () => {
  const guidance = getSideSquatRecordingGuidance({ exercise: 'Goblet Squat', angle: 'Side' });
  const ids = guidance.items.map((item) => item.id);

  assert.equal(isBarbellSideSquatSetup({ exercise: 'Goblet Squat', angle: 'Side' }), false);
  assert.equal(ids.includes('barbell_collar'), false);
  assert.equal(ids.includes('full_body'), true);
  assert.doesNotMatch(guidance.compactSummary, /sleeve|plate|collar/i);
});
