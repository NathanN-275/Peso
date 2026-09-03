function shouldPollAnalysisActivity(items, surfaceActive) {
  if (!surfaceActive) {
    return false;
  }

  return items.some((item) => item.status === 'queued' || item.status === 'processing');
}

const OPTIMISTIC_ACTIVITY_TTL_MS = 60 * 60 * 1000;

function mergeAnalysisActivity(serverItems, optimisticItems, nowMs = Date.now()) {
  const serverVideoIds = new Set(serverItems.map((item) => item.video_id));
  const unconfirmedItems = optimisticItems.filter((item) => {
    if (serverVideoIds.has(item.video_id)) {
      return false;
    }

    const createdAtMs = Date.parse(item.created_at);
    return Number.isFinite(createdAtMs) && nowMs - createdAtMs <= OPTIMISTIC_ACTIVITY_TTL_MS;
  });

  return [...serverItems, ...unconfirmedItems];
}

module.exports = {
  mergeAnalysisActivity,
  shouldPollAnalysisActivity,
};
