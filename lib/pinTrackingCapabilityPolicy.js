const MISSING_MIGRATION_MESSAGE =
  'Pin-assisted tracking is unavailable because the tracking database migration has not been applied. Your pins were not submitted.';

function shouldCheckPinTrackingCapability(trackingSetup) {
  return Boolean(trackingSetup);
}

function getPinTrackingCapabilityError(capabilities, requestedVersion) {
  if (!capabilities || capabilities.pin_assisted_tracking !== true) {
    return MISSING_MIGRATION_MESSAGE;
  }

  if (!capabilities.tracking_setup_versions?.includes(requestedVersion)) {
    return `Pin-assisted tracking payload version ${requestedVersion} is not supported by the deployed backend.`;
  }

  return null;
}

async function verifyPinTrackingCapability({
  trackingSetup,
  getAccessToken,
  fetchCapabilities,
}) {
  if (!shouldCheckPinTrackingCapability(trackingSetup)) {
    return null;
  }

  const accessToken = await getAccessToken();
  const capabilities = await fetchCapabilities(accessToken);
  const capabilityError = getPinTrackingCapabilityError(
    capabilities,
    trackingSetup.version
  );

  if (capabilityError) {
    throw new Error(capabilityError);
  }

  return accessToken;
}

module.exports = {
  MISSING_MIGRATION_MESSAGE,
  getPinTrackingCapabilityError,
  shouldCheckPinTrackingCapability,
  verifyPinTrackingCapability,
};
