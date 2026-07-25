function normalizePositiveDurationMs(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return null;
  }

  return Math.round(value);
}

function resolveVideoDurationMs({
  playerDurationSeconds,
  pickerDurationMs,
}) {
  const playerDurationMs = normalizePositiveDurationMs(
    typeof playerDurationSeconds === 'number'
      ? playerDurationSeconds * 1000
      : null
  );

  return playerDurationMs ?? normalizePositiveDurationMs(pickerDurationMs);
}

function clampTrackingReferenceTimeMs(currentTimeSeconds, durationMs) {
  const currentTimeMs =
    typeof currentTimeSeconds === 'number' && Number.isFinite(currentTimeSeconds)
      ? Math.max(0, Math.round(currentTimeSeconds * 1000))
      : 0;
  const normalizedDurationMs = normalizePositiveDurationMs(durationMs);

  return normalizedDurationMs === null
    ? currentTimeMs
    : Math.min(currentTimeMs, normalizedDurationMs);
}

module.exports = {
  clampTrackingReferenceTimeMs,
  normalizePositiveDurationMs,
  resolveVideoDurationMs,
};
