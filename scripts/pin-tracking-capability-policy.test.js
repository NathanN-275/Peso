const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getPinTrackingCapabilityError,
  shouldCheckPinTrackingCapability,
  verifyPinTrackingCapability,
} = require('../lib/pinTrackingCapabilityPolicy');

test('automatic uploads skip pin tracking compatibility checks', () => {
  assert.equal(shouldCheckPinTrackingCapability(null), false);
  assert.equal(shouldCheckPinTrackingCapability(undefined), false);
});

test('pin-assisted uploads require compatibility checks', () => {
  assert.equal(shouldCheckPinTrackingCapability({ version: 1 }), true);
});

test('supported version one capability passes', () => {
  assert.equal(
    getPinTrackingCapabilityError({
      pin_assisted_tracking: true,
      tracking_setup_versions: [1],
      reason: null,
    }, 1),
    null
  );
});

test('missing migration returns a deployment-required error', () => {
  assert.match(
    getPinTrackingCapabilityError({
      pin_assisted_tracking: false,
      tracking_setup_versions: [],
      reason: 'tracking_setup_migration_missing',
    }, 1),
    /migration has not been applied/i
  );
});

test('unsupported payload version is rejected before upload', () => {
  assert.match(
    getPinTrackingCapabilityError({
      pin_assisted_tracking: true,
      tracking_setup_versions: [2],
      reason: null,
    }, 1),
    /version 1/i
  );
});

test('automatic preflight does not request auth or backend capabilities', async () => {
  let authCalled = false;
  let capabilitiesCalled = false;

  const token = await verifyPinTrackingCapability({
    trackingSetup: null,
    getAccessToken: async () => {
      authCalled = true;
      return 'token';
    },
    fetchCapabilities: async () => {
      capabilitiesCalled = true;
      return null;
    },
  });

  assert.equal(token, null);
  assert.equal(authCalled, false);
  assert.equal(capabilitiesCalled, false);
});

test('pin preflight checks capability and returns the reusable token', async () => {
  const calls = [];
  const token = await verifyPinTrackingCapability({
    trackingSetup: { version: 1 },
    getAccessToken: async () => {
      calls.push('auth');
      return 'token';
    },
    fetchCapabilities: async (accessToken) => {
      calls.push(`capabilities:${accessToken}`);
      return {
        pin_assisted_tracking: true,
        tracking_setup_versions: [1],
        reason: null,
      };
    },
  });

  assert.equal(token, 'token');
  assert.deepEqual(calls, ['auth', 'capabilities:token']);
});

test('unsupported capability rejects before later upload work can begin', async () => {
  const calls = [];

  await assert.rejects(
    verifyPinTrackingCapability({
      trackingSetup: { version: 1 },
      getAccessToken: async () => {
        calls.push('auth');
        return 'token';
      },
      fetchCapabilities: async () => {
        calls.push('capabilities');
        return {
          pin_assisted_tracking: false,
          tracking_setup_versions: [],
          reason: 'tracking_setup_migration_missing',
        };
      },
    }),
    /migration has not been applied/i
  );

  assert.deepEqual(calls, ['auth', 'capabilities']);
});
