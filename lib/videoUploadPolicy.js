function extensionForVideoMimeType(contentType) {
  switch (contentType.split(';')[0].trim().toLowerCase()) {
    case 'video/quicktime':
      return '.mov';
    case 'video/x-m4v':
    case 'video/m4v':
      return '.m4v';
    case 'video/webm':
      return '.webm';
    default:
      return '.mp4';
  }
}

function normalizeVideoUploadFileName(filename, contentType) {
  const expectedExtension = extensionForVideoMimeType(contentType);
  const normalizedFilename = filename.split(/[?#]/)[0];
  const dotIndex = normalizedFilename.lastIndexOf('.');

  if (dotIndex < 0) {
    return `video-upload${expectedExtension}`;
  }

  const currentExtension = normalizedFilename.slice(dotIndex).toLowerCase();
  return currentExtension === expectedExtension
    ? normalizedFilename
    : `${normalizedFilename.slice(0, dotIndex)}${expectedExtension}`;
}

function getStorageUploadErrorMessage(detail) {
  const normalizedDetail = detail.toLowerCase();

  if (
    normalizedDetail.includes('row-level security')
    || normalizedDetail.includes('not authorized')
    || normalizedDetail.includes('permission denied')
  ) {
    return 'Peso could not upload this video because Storage rejected it. Update the videos Storage policy migration, then try again.';
  }

  return `Peso could not upload this video. ${detail}`;
}

module.exports = {
  getStorageUploadErrorMessage,
  normalizeVideoUploadFileName,
};
