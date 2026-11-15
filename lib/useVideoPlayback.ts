import { useCallback, useEffect, useRef, useState } from 'react';
import type { VideoSource } from 'expo-video';
import { getVideoPlaybackUrl } from './backendApi';
import { getBackendApiUrl } from './backendConfig';
import { getActivePrivateMediaSessionKey, getPrivateMediaEpoch, registerPrivateMediaRelease } from './privateMediaLifecycle';
import { issuePrivateVideoPlayback, VIDEO_PLAYBACK_FAILURE, type VideoPlaybackLease } from './privateVideoPlayback';

// One automatic renewal per opened video, then an explicit Retry. No background
// retry loop, token persistence, provider-byte fallback or cross-resource cache.
export function useVideoPlayback(videoId: string | null, accessToken: string | undefined, localUri: string | null = null) {
  const [state, setState] = useState<{ scope: string; lease: VideoPlaybackLease | null; error: string | null; revision: number } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const automaticRenewalUsed = useRef(false);
  const generation = useRef(0);
  const epoch = getPrivateMediaEpoch();
  const backend = getBackendApiUrl();
  const session = getActivePrivateMediaSessionKey();
  const scope = JSON.stringify([epoch, backend, session, videoId, localUri]);
  const localOwner = useRef({ uri: localUri, videoId, session, epoch });
  if (localOwner.current.uri !== localUri || localOwner.current.videoId !== videoId) localOwner.current = { uri: localUri, videoId, session, epoch };
  const localCurrent = !!localUri && !!session && localOwner.current.session === session && localOwner.current.epoch === epoch
    && (process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED !== 'true' || /^(?:file|content|blob):/.test(localUri));
  const activeLease = useRef<{ scope: string; lease: VideoPlaybackLease; revision: number } | null>(null);
  const currentScope = useRef(scope); currentScope.current = scope;
  const renew = useCallback((revision: number) => {
    if (currentScope.current !== scope) return;
    if (localUri) {
      setState({ scope, lease: null, error: VIDEO_PLAYBACK_FAILURE, revision });
      return;
    }
    if (activeLease.current?.scope !== scope || activeLease.current.revision !== revision) return;
    activeLease.current = null;
    if (automaticRenewalUsed.current) {
      setState({ scope, lease: null, error: VIDEO_PLAYBACK_FAILURE, revision }); return;
    }
    automaticRenewalUsed.current = true;
    setState(null); setAttempt(value => value + 1);
  }, [scope, attempt, localUri]);
  useEffect(() => { automaticRenewalUsed.current = false; }, [scope]);
  useEffect(() => {
    activeLease.current = null; setState(null);
    if (localUri || !videoId || !accessToken) return;
    const revision = ++generation.current;
    let active = true;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const stop = () => { activeLease.current = null; active = false; controller.abort(); clearTimeout(timeout); setState(null); };
    const unregister = registerPrivateMediaRelease(stop);
    const check = () => {
      if (!active || controller.signal.aborted || epoch !== getPrivateMediaEpoch() || backend !== getBackendApiUrl()
          || session !== getActivePrivateMediaSessionKey() || currentScope.current !== scope) throw new Error(VIDEO_PLAYBACK_FAILURE);
    };
    const load = async (): Promise<VideoPlaybackLease> => {
      check();
      if (process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED === 'true') return issuePrivateVideoPlayback(videoId, accessToken, controller.signal);
      const response = await getVideoPlaybackUrl(videoId, accessToken, controller.signal);
      check();
      const expiresAt = Date.now() + Math.max(1, Math.min(300, response.expires_in)) * 1000;
      return { source: { uri: response.video_url, useCaching: false }, expiresAt, assertCurrent: check };
    };
    void load().then(lease => {
      check(); lease.assertCurrent();
      activeLease.current = { scope, lease, revision };
      setState({ scope, lease, error: null, revision });
      timeout = setTimeout(() => { if (active) renew(revision); }, Math.max(0, lease.expiresAt - Date.now()));
    }).catch(() => {
      if (active && !controller.signal.aborted && currentScope.current === scope) setState({ scope, lease: null, error: VIDEO_PLAYBACK_FAILURE, revision });
    });
    return () => { active = false; controller.abort(); clearTimeout(timeout); unregister(); };
  }, [scope, videoId, accessToken, localUri, attempt, renew, epoch, backend, session]);
  let lease = accessToken && state?.scope === scope ? state.lease : null;
  try { lease?.assertCurrent(); } catch { lease = null; }
  const retry = useCallback(() => { automaticRenewalUsed.current = false; activeLease.current = null; setState(null); setAttempt(value => value + 1); }, []);
  const currentRevision = state?.scope === scope ? state.revision : null;
  const onPlaybackError = useCallback(() => {
    if (localUri) renew(-1); else if (currentRevision !== null) renew(currentRevision);
  }, [renew, localUri, currentRevision]);
  const source: VideoSource = localUri ? (localCurrent && !(state?.scope === scope && state.error) ? localUri : null) : lease?.source ?? null;
  return { source, lease, scope, revision: state?.revision ?? attempt, retry, onPlaybackError,
    loading: !localUri && !!videoId && !!accessToken && !lease && !(state?.scope === scope && state.error),
    error: localUri && !localCurrent ? VIDEO_PLAYBACK_FAILURE : state?.scope === scope ? state.error : null,
    privateRemote: !localUri && process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED === 'true' };
}
