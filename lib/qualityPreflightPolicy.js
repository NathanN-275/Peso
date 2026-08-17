const { isSideViewSquatSetup } = require('./sideSquatRecordingGuidancePolicy');

const QUALITY_PREFLIGHT_THRESHOLD_VERSION = 'side-squat-preflight-v1';
const QUALITY_PREFLIGHT_WARNING_CONFIDENCE = 0.85;
const QUALITY_PREFLIGHT_CRITICAL_CHECKS = [
  'sideView',
  'bodyChain',
  'subjectScale',
  'motionBlur',
  'dominantLifter',
  'multiplePeople',
];

/**
 * @param {{ status?: string | null, overallConfidence?: number | null, checks?: Record<string, { status?: string | null }> } | null | undefined} result
 */
function needsQualityPreflightWarning(result) {
  if (!result) {
    return false;
  }

  const lowConfidence = typeof result.overallConfidence === 'number'
    && result.overallConfidence < QUALITY_PREFLIGHT_WARNING_CONFIDENCE;
  const criticalCheckFailed = result.status === 'blocked'
    || QUALITY_PREFLIGHT_CRITICAL_CHECKS.some((name) => {
      const status = result.checks?.[name]?.status;
      return status === 'warning' || status === 'blocked';
    });

  return lowConfidence || criticalCheckFailed;
}

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
  const needsAdvisoryConfirmation = advisoryOnly
    && completedResult
    && needsQualityPreflightWarning(result);

  return {
    canQueue: completedResult && (advisoryOnly || result?.status !== 'blocked'),
    needsConfirmation: needsAdvisoryConfirmation || (!advisoryOnly && result?.status === 'warning'),
    mustReplaceVideo: !advisoryOnly && result?.status === 'blocked',
  };
}

/**
 * @param {{ status?: string | null } | null | undefined} result
 * @param {'pending' | 'saved'} mode
 */
function shouldShowQualityAdvisory(result, mode) {
  return mode === 'pending'
    && needsQualityPreflightWarning(result);
}

module.exports = {
  QUALITY_PREFLIGHT_CRITICAL_CHECKS,
  QUALITY_PREFLIGHT_WARNING_CONFIDENCE,
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  getQualityPreflightQueueDecision,
  needsQualityPreflightWarning,
  requiresQualityPreflight,
  shouldShowQualityAdvisory,
};
