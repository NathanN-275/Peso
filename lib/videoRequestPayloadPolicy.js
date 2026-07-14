function buildRegisterUploadedVideoPayload(input) {
  const payload = {
    storage_path: input.storage_path,
    source_type: input.source_type,
    exercise_type: input.exercise_type,
    view_type: input.view_type,
    duration_ms: input.duration_ms,
  };

  if (Object.prototype.hasOwnProperty.call(input, 'tracking_setup')) {
    payload.tracking_setup = input.tracking_setup;
  }

  return payload;
}

function buildAnalyzedVideoExportPayload(input = {}) {
  return {
    pose: input.pose === true,
    barbell: input.barbell === true,
  };
}

module.exports = {
  buildAnalyzedVideoExportPayload,
  buildRegisterUploadedVideoPayload,
};
