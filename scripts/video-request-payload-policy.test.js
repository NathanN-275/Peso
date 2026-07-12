const assert = require('node:assert/strict');
const test = require('node:test');

const {
  buildAnalyzedVideoExportPayload,
  buildRegisterUploadedVideoPayload,
} = require('../lib/videoRequestPayloadPolicy');

test('upload registration payload builder excludes server-owned fields', () => {
  const payload = buildRegisterUploadedVideoPayload({
    storage_path: 'user/uploads/video.mov',
    source_type: 'camera_roll',
    exercise_type: 'squat',
    view_type: 'side',
    duration_ms: 90000,
    tracking_setup: { version: 1, pins: [] },
    status: 'completed',
    save_state: 'saved',
    expires_at: null,
    playback_path: 'other/playback/video.mp4',
    thumbnail_path: 'other/thumbnails/video.jpg',
    error_message: 'ignore me',
  });

  assert.deepEqual(Object.keys(payload).sort(), [
    'duration_ms',
    'exercise_type',
    'source_type',
    'storage_path',
    'tracking_setup',
    'view_type',
  ]);
  assert.equal(payload.status, undefined);
  assert.equal(payload.playback_path, undefined);
});

test('upload registration payload builder preserves minimum upload registration fields', () => {
  assert.deepEqual(
    buildRegisterUploadedVideoPayload({
      storage_path: 'user/uploads/video.mov',
      source_type: 'camera',
      exercise_type: 'bench press',
      view_type: 'front',
      duration_ms: null,
    }),
    {
      storage_path: 'user/uploads/video.mov',
      source_type: 'camera',
      exercise_type: 'bench press',
      view_type: 'front',
      duration_ms: null,
    }
  );
});

test('analyzed export payload builder excludes unknown fields', () => {
  const payload = buildAnalyzedVideoExportPayload({
    pose: true,
    barbell: false,
    storage_path: 'other/export.mp4',
    expires_in: 999999,
  });

  assert.deepEqual(payload, { pose: true, barbell: false });
});
