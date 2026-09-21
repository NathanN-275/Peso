function failureCopy(activity) {
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
};
