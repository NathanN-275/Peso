function includesMissingColumnMessage(message, columnNames) {
  const normalized = String(message || '').toLowerCase();
  const referencesColumn = columnNames.some((columnName) => normalized.includes(columnName));
  const reportsMissing = normalized.includes('does not exist') || normalized.includes('could not find');

  return referencesColumn && reportsMissing;
}

function getVideoInsertRetryMode(message, hasTrackingSetup) {
  if (hasTrackingSetup && includesMissingColumnMessage(message, ['tracking_setup'])) {
    return 'tracking_unavailable';
  }

  if (
    includesMissingColumnMessage(message, [
      'storage_state',
      'original_size_bytes',
      'uploaded_size_bytes',
      'was_compressed',
    ])
  ) {
    return 'retry_without_storage_metadata';
  }

  return 'fail';
}

module.exports = {
  getVideoInsertRetryMode,
};
