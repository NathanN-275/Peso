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
 * @param {{ advisoryOnly?: boolean }} [options]
 */
function getQualityPreflightQueueDecision(result, options = {}) {
  const advisoryOnly = options.advisoryOnly === true;
  const completedResult = ['pass', 'warning', 'blocked'].includes(result?.status);

  return {
    canQueue: completedResult && (advisoryOnly || result?.status !== 'blocked'),
    needsConfirmation: !advisoryOnly && result?.status === 'warning',
    mustReplaceVideo: !advisoryOnly && result?.status === 'blocked',
  };
}

/**
 * @param {{ status?: string | null } | null | undefined} result
 * @param {'pending' | 'saved'} mode
 */
function shouldShowQualityAdvisory(result, mode) {
  return mode === 'pending'
    && (result?.status === 'warning' || result?.status === 'blocked');
}

module.exports = {
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  getQualityPreflightQueueDecision,
  requiresQualityPreflight,
  shouldShowQualityAdvisory,
};
