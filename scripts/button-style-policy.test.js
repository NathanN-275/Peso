const assert = require('node:assert/strict');
const test = require('node:test');

const { getButtonVariantColors } = require('../lib/buttonStylePolicy');

const colors = {
  brand: '#1F6BFF',
  textPrimary: '#F5F8FF',
  secondarySurface: '#111827',
  secondaryBorder: '#263244',
  secondaryText: '#E5E7EB',
};

test('primary and secondary button variants have distinct enabled styles', () => {
  const primary = getButtonVariantColors('primary', colors);
  const secondary = getButtonVariantColors('secondary', colors);

  assert.equal(primary.backgroundColor, colors.brand);
  assert.equal(secondary.backgroundColor, colors.secondarySurface);
  assert.equal(secondary.borderColor, colors.secondaryBorder);
  assert.equal(secondary.borderWidth, 1);
  assert.notEqual(primary.backgroundColor, secondary.backgroundColor);
});
