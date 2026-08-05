const FRONT_TRAIL_WINDOW_SECONDS = 1;
const MAX_FRONT_TRAIL_SAMPLE_GAP_SECONDS = 0.2;

function shouldShowFrontMotionTrails({ cameraView, exercise }) {
  return cameraView?.trim().toLowerCase() === 'front'
    && exercise?.trim().toLowerCase().endsWith('squat') === true;
}

function frontTrailWindowFrames(frames, currentTime, windowSeconds = FRONT_TRAIL_WINDOW_SECONDS) {
  if (!Array.isArray(frames) || !Number.isFinite(currentTime)) {
    return [];
  }
  const startTime = Math.max(currentTime - windowSeconds, 0);
  return frames.filter((frame) => (
    Number.isFinite(frame?.time)
    && frame.time >= startTime
    && frame.time <= currentTime
  ));
}

function shouldConnectFrontTrailSamples(previousTime, currentTime) {
  return Number.isFinite(previousTime)
    && Number.isFinite(currentTime)
    && currentTime >= previousTime
    && currentTime - previousTime <= MAX_FRONT_TRAIL_SAMPLE_GAP_SECONDS;
}

function resolveSquatTorsoStart(pointNames, side) {
  const upperBackName = `${side}_upper_back`;
  if (pointNames?.has(upperBackName)) {
    return upperBackName;
  }

  const shoulderName = `${side}_shoulder`;
  return pointNames?.has(shoulderName) ? shoulderName : null;
}

module.exports = {
  FRONT_TRAIL_WINDOW_SECONDS,
  MAX_FRONT_TRAIL_SAMPLE_GAP_SECONDS,
  frontTrailWindowFrames,
  resolveSquatTorsoStart,
  shouldConnectFrontTrailSamples,
  shouldShowFrontMotionTrails,
};
