const assert = require('node:assert/strict');
const test = require('node:test');

const {
  buildReservedUploadRequest,
  getStorageUploadErrorMessage,
  normalizeVideoUploadFileName,
  resolveReservedUploadUrl,
} = require('../lib/videoUploadPolicy');

test('reserved API uploads resolve the backend path and add the current bearer token', () => {
  const video = new Blob(['video-bytes'], { type: 'video/mp4' });
  const request = buildReservedUploadRequest(video, {
    upload_method: 'PUT',
    upload_body_format: 'raw',
    upload_authentication: 'bearer',
    upload_headers: { 'Content-Type': 'video/mp4', 'If-None-Match': '*' },
  }, 'access-token');

  assert.equal(
    resolveReservedUploadUrl('/upload-reservations/abc/content', 'https://api.example.test', 'bearer'),
    'https://api.example.test/upload-reservations/abc/content'
  );
  assert.equal(request.method, 'PUT');
  assert.deepEqual(request.headers, {
    Authorization: 'Bearer access-token',
    'Content-Type': 'video/mp4',
    'If-None-Match': '*',
  });
  assert.equal(request.body, video);
});

test('authenticated reserved uploads cannot send a bearer token to another origin', () => {
  assert.throws(
    () => resolveReservedUploadUrl(
      'https://storage.example.test/upload',
      'https://api.example.test',
      'bearer'
    ),
    /configured backend origin/
  );
});

test('authenticated reserved uploads cannot override the current bearer token', () => {
  const request = buildReservedUploadRequest(new Blob(['video-bytes']), {
    upload_method: 'PUT',
    upload_body_format: 'raw',
    upload_authentication: 'bearer',
    upload_headers: { Authorization: 'Bearer stale-token' },
  }, 'current-token');

  assert.equal(request.headers.Authorization, 'Bearer current-token');
});

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
