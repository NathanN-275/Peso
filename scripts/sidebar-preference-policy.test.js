const assert = require('node:assert/strict');
const test = require('node:test');

const {
  SIDEBAR_PREFERENCE_KEY,
  readSidebarCollapsed,
  writeSidebarCollapsed,
} = require('../lib/sidebarPreferencePolicy');

test('sidebar is expanded by default', () => {
  const storage = { getItem: () => null };

  assert.equal(readSidebarCollapsed(storage), false);
  assert.equal(readSidebarCollapsed(null), false);
});

test('sidebar restores and updates its collapsed preference', () => {
  const values = new Map([[SIDEBAR_PREFERENCE_KEY, 'true']]);
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };

  assert.equal(readSidebarCollapsed(storage), true);
  writeSidebarCollapsed(storage, false);
  assert.equal(readSidebarCollapsed(storage), false);
});

test('sidebar falls back to expanded when storage is unavailable', () => {
  const storage = {
    getItem: () => {
      throw new Error('blocked');
    },
  };

  assert.equal(readSidebarCollapsed(storage), false);
});
