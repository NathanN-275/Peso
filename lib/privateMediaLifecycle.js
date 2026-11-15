const releases = new Set();
let epoch = 0;
let activeSessionKey = null;

function getPrivateMediaEpoch() { return epoch; }
function setActivePrivateMediaSessionKey(key) { activeSessionKey = key; }
function getActivePrivateMediaSessionKey() { return activeSessionKey; }

function registerPrivateMediaRelease(release) {
  releases.add(release);
  return () => { releases.delete(release); };
}

function releaseBrowserMedia(video) {
  if (!video) return;
  let failed = false;
  // A failed pause must not prevent removal of private sources.
  for (const release of [() => video.pause(), () => video.removeAttribute('src'),
    () => video.removeAttribute('poster'), () => video.load()]) {
    try { release(); } catch { failed = true; }
  }
  if (failed) throw new Error('Unable to release private media. Please try signing out again.');
}

async function releaseNativeMedia(player) {
  let failed = false;
  try { player.pause(); } catch { failed = true; }
  try { await player.replaceAsync(null); } catch { failed = true; }
  if (failed) throw new Error('Unable to release private media. Please try signing out again.');
}

function registerNativePrivateMedia(player) {
  let mounted = true;
  const unregister = registerPrivateMediaRelease(async () => {
    if (!mounted) return;
    try { await releaseNativeMedia(player); } catch (error) {
      // useVideoPlayer disposes its object on unmount/source replacement.
      if (mounted) throw error;
    }
  });
  return () => { mounted = false; unregister(); };
}

const replacements = new WeakMap();
// A late native replace must settle and be cleared before logout can acknowledge
// release. Serialize source changes so an older cleanup cannot clear a newer clip.
function attachPrivateMediaSource(player, source, assertCurrent, onReady, onError) {
  let live = true;
  let state = replacements.get(player);
  if (!state) { state = { work: Promise.resolve() }; replacements.set(player, state); }
  const enqueue = action => {
    state.work = state.work.catch(() => {}).then(action);
    return state.work;
  };
  void enqueue(async () => {
    await releaseNativeMedia(player);
    if (!live || !source) return;
    try {
      assertCurrent();
      await player.replaceAsync(source);
      if (!live) { await releaseNativeMedia(player); return; }
      assertCurrent();
      player.pause();
      onReady();
    } catch (error) { await releaseNativeMedia(player); throw error; }
  }).catch(() => { if (live) onError(); });
  const clear = () => { live = false; return enqueue(() => releaseNativeMedia(player)); };
  const unregister = registerPrivateMediaRelease(clear);
  return () => { void clear().catch(() => {}).finally(unregister); };
}

async function releasePrivateMedia() {
  epoch += 1;
  const results = await Promise.allSettled([...releases].map((release) => {
    try { return Promise.resolve(release()); } catch (error) { return Promise.reject(error); }
  }));
  if (results.some((result) => result.status === 'rejected')) {
    throw new Error('Unable to release private media. Please try signing out again.');
  }
}

module.exports = { registerPrivateMediaRelease, releasePrivateMedia, getPrivateMediaEpoch,
  setActivePrivateMediaSessionKey, getActivePrivateMediaSessionKey, releaseBrowserMedia, releaseNativeMedia,
  registerNativePrivateMedia, attachPrivateMediaSource };
