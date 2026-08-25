function shouldPollAnalysisActivity(items, surfaceActive) {
  if (!surfaceActive) {
    return false;
  }

  return items.some((item) => item.status === 'queued' || item.status === 'processing');
}

module.exports = {
  shouldPollAnalysisActivity,
};
