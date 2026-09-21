function getBackendErrorMessage(errorText, status) {
  if (typeof errorText === 'string' && errorText.trim()) {
    try {
      const payload = JSON.parse(errorText);

      if (typeof payload?.detail === 'string' && payload.detail.trim()) {
        if (payload.detail.includes('reference_time_out_of_bounds')) {
          return 'The saved pin frame is outside this video. Reopen Edit Pins and choose a frame inside the clip.';
        }

        if (
          payload.detail.includes('do not contain a valid video stream')
          || payload.detail.includes('contents do not match the selected video format')
        ) {
          return 'Peso couldn’t read this video. Export the clip again as MP4 or choose another video, then try again.';
        }

        return payload.detail;
      }
    } catch {
      return errorText;
    }

    return errorText;
  }

  return `Backend request failed with status ${status}.`;
}

function getVideoSubmissionFailureMessage(phase, message) {
  if (phase === 'quality_preflight') {
    return message;
  }

  return 'Upload succeeded, but analysis could not start. The upload was cleaned up; please try again.';
}

module.exports = {
  getBackendErrorMessage,
  getVideoSubmissionFailureMessage,
};
