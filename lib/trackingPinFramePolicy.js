const FRAME_CHANGE_EPSILON_SECONDS = 1 / 120;

function getPinnedFrameChangeAction({
  pinCount,
  pinnedFrameTime,
  targetTime,
  suppressWarning,
}) {
  if (pinCount <= 0 || pinnedFrameTime === null) {
    return 'accept';
  }

  if (Math.abs(targetTime - pinnedFrameTime) <= FRAME_CHANGE_EPSILON_SECONDS) {
    return 'restore_pinned_frame';
  }

  return suppressWarning ? 'reset_and_accept' : 'confirm_reset';
}

module.exports = {
  FRAME_CHANGE_EPSILON_SECONDS,
  getPinnedFrameChangeAction,
};
