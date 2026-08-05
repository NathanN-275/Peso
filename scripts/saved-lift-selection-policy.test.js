const test = require('node:test');
const assert = require('node:assert/strict');

const {
  normalizeSavedLiftIds,
  normalizeSavedLiftView,
  pruneSavedLiftSelection,
  selectVisibleSavedLifts,
  toggleSavedLiftSelection,
} = require('../lib/savedLiftSelectionPolicy');

test('Saved Lift view defaults to list for unknown persisted values', () => {
  assert.equal(normalizeSavedLiftView('grid'), 'grid');
  assert.equal(normalizeSavedLiftView('folder'), 'list');
});

test('Saved Lift selection is deduplicated and toggled without mutating library data', () => {
  assert.deepEqual(normalizeSavedLiftIds(['lift-1', 'lift-1', '', null]), ['lift-1']);
  assert.deepEqual(toggleSavedLiftSelection(['lift-1'], 'lift-2'), ['lift-1', 'lift-2']);
  assert.deepEqual(toggleSavedLiftSelection(['lift-1', 'lift-2'], 'lift-1'), ['lift-2']);
});

test('select visible and prune keep selection scoped to available Saved Lifts', () => {
  assert.deepEqual(selectVisibleSavedLifts(['lift-1'], ['lift-1', 'lift-2']), ['lift-1', 'lift-2']);
  assert.deepEqual(pruneSavedLiftSelection(['lift-1', 'lift-2'], ['lift-2', 'lift-3']), ['lift-2']);
});
