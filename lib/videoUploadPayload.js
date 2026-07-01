function withOptionalTrackingSetup(payload, trackingSetup) {
  return trackingSetup
    ? { ...payload, tracking_setup: trackingSetup }
    : payload;
}

module.exports = { withOptionalTrackingSetup };
