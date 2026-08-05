function createObjectUrlLease(file, urlApi = globalThis.URL) {
  if (!urlApi?.createObjectURL || !urlApi?.revokeObjectURL) {
    throw new Error('Object URLs are unavailable in this browser.');
  }

  const url = urlApi.createObjectURL(file);
  let revoked = false;

  return {
    url,
    revoke() {
      if (revoked) {
        return;
      }

      revoked = true;
      urlApi.revokeObjectURL(url);
    },
  };
}

function createWebVideoPreview(
  uri,
  { timeMs, quality = 0.7 },
  documentRef = globalThis.document
) {
  if (!documentRef) {
    return Promise.reject(
      new Error('Document is unavailable for web video thumbnail generation.')
    );
  }

  return new Promise((resolve, reject) => {
    const video = documentRef.createElement('video');
    const canvas = documentRef.createElement('canvas');
    let settled = false;

    const cleanup = () => {
      video.pause();
      video.removeAttribute('src');
      video.load();
    };
    const fail = (error) => {
      if (settled) {
        return;
      }

      settled = true;
      cleanup();
      reject(
        error instanceof Error
          ? error
          : new Error('Unable to generate web video thumbnail.')
      );
    };

    video.muted = true;
    video.playsInline = true;
    video.preload = 'metadata';

    video.addEventListener(
      'loadedmetadata',
      () => {
        const durationSeconds = Number.isFinite(video.duration) ? video.duration : 0;
        const targetSeconds = Math.max(
          0,
          Math.min(timeMs / 1_000, durationSeconds || timeMs / 1_000)
        );
        video.currentTime = targetSeconds;
      },
      { once: true }
    );

    video.addEventListener(
      'seeked',
      () => {
        const width = video.videoWidth;
        const height = video.videoHeight;

        if (!width || !height) {
          fail(new Error('Selected video did not expose frame dimensions.'));
          return;
        }

        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext('2d');

        if (!context) {
          fail(new Error('Canvas 2D context is unavailable.'));
          return;
        }

        context.drawImage(video, 0, 0, width, height);

        try {
          const thumbnail = canvas.toDataURL('image/jpeg', quality);
          const durationSeconds = Number.isFinite(video.duration) ? video.duration : 0;
          settled = true;
          cleanup();
          resolve({ thumbnail, durationSeconds });
        } catch (error) {
          fail(error);
        }
      },
      { once: true }
    );

    video.addEventListener(
      'error',
      () => fail(new Error('Selected video could not be decoded by this browser.')),
      { once: true }
    );

    video.src = uri;
    video.load();
  });
}

module.exports = {
  createObjectUrlLease,
  createWebVideoPreview,
};
