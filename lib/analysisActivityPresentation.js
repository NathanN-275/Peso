const { failureCopy, lastReachedAnalysisStage } = require('./analysisRecoveryPolicy');

const ANALYSIS_STAGES = [
  ['queued', 'Queued'], ['downloading', 'Preparing video'], ['pose', 'Tracking movement'],
  ['barbell_tracking', 'Tracking barbell'], ['saving', 'Saving'], ['ready', 'Ready'],
];

function analysisStageCopy(activity) {
  const copy = {
    queued: ['Video queued', 'Waiting for an analysis worker. You can leave this page.'],
    downloading: ['Preparing your video', 'Downloading your uploaded video for analysis.'],
    pose: ['Tracking your movement', 'Following the lifter through the set.'],
    barbell_tracking: ['Tracking the barbell', 'Building your bar path.'],
    saving: ['Saving your analysis', 'Preparing the result for review.'],
    ready: ['Analysis ready', 'Your result is ready to review.'],
    failed: ['Analysis could not finish', failureCopy(activity) + (lastReachedAnalysisStage(activity)
      ? ` Last step: ${ANALYSIS_STAGES.find(([key]) => key === lastReachedAnalysisStage(activity))?.[1] || 'processing'}.` : '')],
  }[activity?.stage];
  return copy ? { title: copy[0], detail: copy[1] }
    : { title: 'Loading analysis activity', detail: 'Checking for the latest update.' };
}

function analysisElapsed(activity, nowMs) {
  const terminal = activity?.status === 'ready' || activity?.status === 'failed';
  const end = terminal ? Date.parse(activity.stage_timestamps?.[activity.stage] || activity.updated_at) : nowMs;
  const elapsed = start => {
    const parsed = Date.parse(start);
    return Number.isFinite(parsed) && Number.isFinite(end) ? Math.max(0, Math.floor((end - parsed) / 1000)) : null;
  };
  return { total: elapsed(activity?.created_at), stage: terminal ? null : elapsed(activity?.stage_started_at) };
}

function formatElapsed(seconds) {
  if (seconds === null) return 'Time unavailable';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

function analysisStepState(activity, stage) {
  if (activity.stage === 'ready') return 'complete';
  let current = activity.stage;
  if (current === 'failed') {
    current = lastReachedAnalysisStage(activity) ?? 'queued';
  }
  const index = ANALYSIS_STAGES.findIndex(([key]) => key === stage);
  const currentIndex = ANALYSIS_STAGES.findIndex(([key]) => key === current);
  if (index === currentIndex) return activity.stage === 'failed' ? 'failed' : 'current';
  return index < currentIndex ? 'complete' : 'pending';
}

module.exports = { ANALYSIS_STAGES, analysisStageCopy, analysisElapsed, formatElapsed, analysisStepState };
