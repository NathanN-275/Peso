const assert = require('node:assert/strict');
const test = require('node:test');

const {
  createObjectUrlLease,
  createWebVideoPreview,
} = require('../lib/webVideoSelectionPolicy');

function createVideoDocument({ unsupported = false } = {}) {
  const listeners = new Map();
  const context = { drawImage() {} };
  let source = '';
  let currentTime = 0;

  const video = {
    duration: 18.933,
    videoWidth: 360,
    videoHeight: 874,
    muted: false,
    playsInline: false,
    preload: '',
    addEventListener(name, callback) {
      listeners.set(name, callback);
    },
    pause() {},
    removeAttribute() {
      source = '';
    },
    load() {
      if (!source) return;
      if (unsupported) listeners.get('error')?.();
      else listeners.get('loadedmetadata')?.();
    },
    set src(value) {
      source = value;
    },
    set currentTime(value) {
      currentTime = value;
      listeners.get('seeked')?.();
    },
    get currentTime() {
      return currentTime;
    },
  };
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => context,
    toDataURL: () => 'data:image/jpeg;base64,preview',
  };

  return {
    createElement(name) {
      return name === 'video' ? video : canvas;
    },
  };
}

test('web video preview returns a real thumbnail and duration', async () => {
  const preview = await createWebVideoPreview(
    'blob:peso-video',
    { timeMs: 1_000 },
    createVideoDocument()
  );

  assert.deepEqual(preview, {
    thumbnail: 'data:image/jpeg;base64,preview',
    durationSeconds: 18.933,
  });
});

test('unsupported web video rejects so the UI can show its fallback', async () => {
  await assert.rejects(
    createWebVideoPreview(
      'blob:unsupported-video',
      { timeMs: 1_000 },
      createVideoDocument({ unsupported: true })
    ),
    /could not be decoded/
  );
});

test('object URL lease revokes a selected file exactly once', () => {
  const revoked = [];
  const lease = createObjectUrlLease(
    { name: 'squat.mov' },
    {
      createObjectURL: () => 'blob:squat-video',
      revokeObjectURL: (url) => revoked.push(url),
    }
  );

  assert.equal(lease.url, 'blob:squat-video');
  lease.revoke();
  lease.revoke();
  assert.deepEqual(revoked, ['blob:squat-video']);
});
