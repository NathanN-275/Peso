const { isSideViewSquatSetup } = require('./sideSquatRecordingGuidancePolicy');

const QUALITY_PREFLIGHT_THRESHOLD_VERSION = 'side-squat-preflight-v1';

/**
 * @param {{ exercise?: string | null, angle?: string | null } | null | undefined} setup
 */
function requiresQualityPreflight(setup) {
  return isSideViewSquatSetup(setup);
}

/**
 * @param {{ status?: string | null } | null | undefined} result
 */
function getQualityPreflightQueueDecision(result) {
  return {
    canQueue: result?.status === 'pass' || result?.status === 'warning',
    needsConfirmation: result?.status === 'warning',
    mustReplaceVideo: result?.status === 'blocked',
  };
}

module.exports = {
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  getQualityPreflightQueueDecision,
  requiresQualityPreflight,
};
