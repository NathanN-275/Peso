const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getStorageUploadErrorMessage,
  normalizeVideoUploadFileName,
} = require('../lib/videoUploadPolicy');

test('native picker metadata is normalized to the MIME type accepted by Storage policy', () => {
  assert.equal(
    normalizeVideoUploadFileName('IMG_0001.MOV', 'video/mp4'),
    'IMG_0001.mp4'
  );
  assert.equal(
    normalizeVideoUploadFileName('content://media/external/video/42', 'video/quicktime'),
    'video-upload.mov'
  );
  assert.equal(
    normalizeVideoUploadFileName('squat.webm?token=unused', 'video/webm'),
    'squat.webm'
  );
});

test('Storage authorization failures provide an actionable migration message', () => {
  assert.equal(
    getStorageUploadErrorMessage('new row violates row-level security policy'),
    'Peso could not upload this video because Storage rejected it. Update the videos Storage policy migration, then try again.'
  );
});
