const QUEUED_DURATION_MS = 2_000;
const ANALYZING_DURATION_MS = 6_000;
const TOTAL_ANALYSIS_DURATION_MS = QUEUED_DURATION_MS + ANALYZING_DURATION_MS;

function createIdleDemoAnalysis() {
  return {
    phase: 'idle',
    percentage: 0,
    startTime: null,
  };
}

function startDemoAnalysis(startTime) {
  return {
    phase: 'queued',
    percentage: 0,
    startTime,
  };
}

function progressDemoAnalysis(startTime, now) {
  const elapsedMs = Math.max(0, now - startTime);

  if (elapsedMs < QUEUED_DURATION_MS) {
    return {
      phase: 'queued',
      percentage: 0,
      startTime,
    };
  }

  if (elapsedMs < TOTAL_ANALYSIS_DURATION_MS) {
    const analyzingElapsedMs = elapsedMs - QUEUED_DURATION_MS;
    const percentage = Math.min(
      99,
      Math.max(1, Math.floor((analyzingElapsedMs / ANALYZING_DURATION_MS) * 100))
    );

    return {
      phase: 'analyzing',
      percentage,
      startTime,
    };
  }

  return {
    phase: 'ready',
    percentage: 100,
    startTime,
  };
}

function cancelDemoAnalysis() {
  return createIdleDemoAnalysis();
}

module.exports = {
  ANALYZING_DURATION_MS,
  QUEUED_DURATION_MS,
  TOTAL_ANALYSIS_DURATION_MS,
  cancelDemoAnalysis,
  createIdleDemoAnalysis,
  progressDemoAnalysis,
  startDemoAnalysis,
};
