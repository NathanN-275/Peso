const assert = require('node:assert/strict');
const test = require('node:test');

const {
  parseWorkoutSaveDetails,
  resolveStoredLoadUnit,
} = require('../lib/workoutSavePolicy');

test('workout save details allow reps and weight to be omitted', () => {
  assert.deepEqual(parseWorkoutSaveDetails('', '', 'lb'), {
    ok: true,
    value: { performed_reps: null, load_value: null, load_unit: null },
  });
  assert.deepEqual(parseWorkoutSaveDetails('', '225', 'lb'), {
    ok: true,
    value: { performed_reps: null, load_value: 225, load_unit: 'lb' },
  });
  assert.deepEqual(parseWorkoutSaveDetails('2', '', 'kg'), {
    ok: true,
    value: { performed_reps: 2, load_value: null, load_unit: null },
  });
});

test('workout save details require entered reps to be an integer of at least one', () => {
  assert.deepEqual(parseWorkoutSaveDetails('1.5', '225', 'lb'), {
    ok: false,
    error: 'Reps must be a whole number of at least 1.',
  });
  assert.deepEqual(parseWorkoutSaveDetails('0', '225', 'lb'), {
    ok: false,
    error: 'Reps must be a whole number of at least 1.',
  });
});

test('workout save details accept zero and decimal load', () => {
  assert.deepEqual(parseWorkoutSaveDetails('2', '0', 'kg'), {
    ok: true,
    value: { performed_reps: 2, load_value: 0, load_unit: 'kg' },
  });
  assert.deepEqual(parseWorkoutSaveDetails('2', '102.5', 'lb'), {
    ok: true,
    value: { performed_reps: 2, load_value: 102.5, load_unit: 'lb' },
  });
});

test('workout save details reject negative and malformed load', () => {
  assert.equal(parseWorkoutSaveDetails('2', '-1', 'lb').ok, false);
  assert.equal(parseWorkoutSaveDetails('2', 'twenty', 'lb').ok, false);
});

test('stored load unit accepts only lb and kg', () => {
  assert.equal(resolveStoredLoadUnit('kg'), 'kg');
  assert.equal(resolveStoredLoadUnit('lb'), 'lb');
  assert.equal(resolveStoredLoadUnit('stone'), 'lb');
  assert.equal(resolveStoredLoadUnit(null), 'lb');
});
