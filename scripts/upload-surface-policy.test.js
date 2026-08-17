const assert = require('node:assert/strict');
const test = require('node:test');

const {
  MOBILE_WEB_BREAKPOINT,
  usesMobileUploadFlow,
} = require('../lib/uploadSurfacePolicy');

test('native uploads always use the mobile advisory flow', () => {
  assert.equal(usesMobileUploadFlow({ isWeb: false, viewportWidth: 1024 }), true);
});

test('web uploads use the mobile flow below the shared 768px breakpoint', () => {
  assert.equal(MOBILE_WEB_BREAKPOINT, 768);
  assert.equal(usesMobileUploadFlow({ isWeb: true, viewportWidth: 390 }), true);
  assert.equal(usesMobileUploadFlow({ isWeb: true, viewportWidth: 767 }), true);
  assert.equal(usesMobileUploadFlow({ isWeb: true, viewportWidth: 768 }), false);
  assert.equal(usesMobileUploadFlow({ isWeb: true, viewportWidth: 1280 }), false);
});

test('unknown web viewport widths remain on the desktop flow until layout resolves', () => {
  assert.equal(usesMobileUploadFlow({ isWeb: true, viewportWidth: 0 }), false);
  assert.equal(usesMobileUploadFlow({ isWeb: true, viewportWidth: Number.NaN }), false);
});
