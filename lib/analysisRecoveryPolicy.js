function lastReachedAnalysisStage(activity) {
  return Object.entries(activity?.stage_timestamps ?? {})
    .filter(([key, time]) => !['failed', 'ready'].includes(key) && Number.isFinite(Date.parse(time)))
    .sort((a, b) => Date.parse(b[1]) - Date.parse(a[1]))[0]?.[0];
}

function failureCopy(activity) {
  const lastStage = lastReachedAnalysisStage(activity);
  if (activity?.failure_class === 'analysis_runtime' && lastStage === 'saving') {
    return 'Peso couldn’t finish saving this analysis. This does not mean your recording is unreadable.';
  }
  switch (activity?.failure_class) {
    case 'invalid_video':
      return 'Peso couldn’t read this video. Delete it and upload another video.';
    case 'analysis_timeout':
      return 'Analysis took too long. Try again or delete this video.';
    case 'transient_infrastructure':
      return 'A temporary service issue interrupted analysis. Try again or delete this video.';
    case 'worker_lease_expired':
    case 'worker_process_exit':
      return 'Analysis was interrupted. Try again or delete this video.';
    case 'analysis_runtime':
      return 'A processing error prevented this analysis from finishing. Your recording may be fine.';
    default:
      return 'This video could not be analyzed. Delete it and upload another video.';
  }
}

function canRetryAnalysis(activity) {
  return activity?.stage === 'failed' && activity?.recovery_action === 'retry';
}

module.exports = {
  canRetryAnalysis,
  failureCopy,
  lastReachedAnalysisStage,
};
