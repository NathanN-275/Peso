function getBackendErrorMessage(errorText, status) {
  if (typeof errorText === 'string' && errorText.trim()) {
    try {
      const payload = JSON.parse(errorText);

      if (typeof payload?.detail === 'string' && payload.detail.trim()) {
        if (payload.detail.includes('reference_time_out_of_bounds')) {
          return 'The saved pin frame is outside this video. Reopen Edit Pins and choose a frame inside the clip.';
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

module.exports = {
  getBackendErrorMessage,
};
