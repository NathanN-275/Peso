import { useCallback, useEffect, useRef, useState } from 'react';
import { getBackendApiUrl } from './backendConfig';
import { getActivePrivateMediaSessionKey, getPrivateMediaEpoch, registerPrivateMediaRelease } from './privateMediaLifecycle';
import { readPrivateVideoThumbnail, THUMBNAIL_FAILURE } from './privateVideoThumbnail';

type Preview = { uri: string; expiresAt: number; assertCurrent(): void };
export function useVideoThumbnail(videoId: string, available: boolean, accessToken: string | undefined, legacyUrl: string | null) {
  const [state, setState] = useState<{ scope: string; preview: Preview | null; error: boolean; revision: number } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const automaticRenewalUsed = useRef(false);
  const generation = useRef(0);
  const activePreview = useRef<{ scope: string; revision: number } | null>(null);
  const epoch = getPrivateMediaEpoch(), backend = getBackendApiUrl(), session = getActivePrivateMediaSessionKey();
  const privateMedia = process.env.EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED === 'true';
  const fallbackUrl = privateMedia ? null : legacyUrl;
  const enabled = privateMedia ? available === true : !!fallbackUrl;
  const scope = JSON.stringify([epoch, backend, session, videoId, enabled, fallbackUrl]);
  const current = useRef(scope); current.current = scope;
  const legacyOwner = useRef({ videoId, legacyUrl: fallbackUrl, session, epoch });
  if (legacyOwner.current.videoId !== videoId || legacyOwner.current.legacyUrl !== fallbackUrl) legacyOwner.current = { videoId, legacyUrl: fallbackUrl, session, epoch };
  const renew = useCallback((revision: number) => {
    if (current.current !== scope || (activePreview.current?.scope !== scope || activePreview.current.revision !== revision)) return;
    activePreview.current = null;
    if (automaticRenewalUsed.current || !privateMedia) { setState({ scope, preview: null, error: true, revision }); return; }
    automaticRenewalUsed.current = true; setState(null); setAttempt(value => value + 1);
  }, [scope, privateMedia, attempt]);
  useEffect(() => { automaticRenewalUsed.current = false; }, [scope]);
  useEffect(() => {
    activePreview.current = null; setState(null);
    if (!enabled || !accessToken || !session) return;
    const revision = ++generation.current;
    let active = true;
    const controller = new AbortController(); let timeout: ReturnType<typeof setTimeout> | undefined;
    const stop = () => { active = false; activePreview.current = null; controller.abort(); clearTimeout(timeout); setState(null); };
    const unregister = registerPrivateMediaRelease(stop);
    const check = () => {
      if (!active || controller.signal.aborted || current.current !== scope || epoch !== getPrivateMediaEpoch()
          || session !== getActivePrivateMediaSessionKey() || backend !== getBackendApiUrl()) throw new Error(THUMBNAIL_FAILURE);
    };
    const load = async (): Promise<Preview> => {
      check();
      if (!privateMedia) {
        if (legacyOwner.current.session !== session || legacyOwner.current.epoch !== epoch || !fallbackUrl) throw new Error(THUMBNAIL_FAILURE);
        return { uri: fallbackUrl, expiresAt: Infinity, assertCurrent: check };
      }
      const result = await readPrivateVideoThumbnail(videoId, accessToken, controller.signal);
      return { uri: result.dataUri, expiresAt: result.expiresAt, assertCurrent: result.assertCurrent };
    };
    void load().then(preview => {
      check(); preview.assertCurrent(); activePreview.current = { scope, revision };
      setState({ scope, preview, error: false, revision });
      if (Number.isFinite(preview.expiresAt)) timeout = setTimeout(() => renew(revision), Math.max(0, preview.expiresAt - Date.now()));
    }).catch(() => {
      if (active && !controller.signal.aborted && current.current === scope) setState({ scope, preview: null, error: true, revision });
    });
    return () => { active = false; controller.abort(); clearTimeout(timeout); unregister(); };
  }, [scope, enabled, accessToken, session, epoch, backend, videoId, fallbackUrl, privateMedia, attempt, renew]);
  let preview = accessToken && state?.scope === scope ? state.preview : null;
  try { preview?.assertCurrent(); } catch { preview = null; }
  const retry = useCallback(() => { activePreview.current = null; automaticRenewalUsed.current = false; setState(null); setAttempt(value => value + 1); }, []);
  const currentRevision = state?.scope === scope ? state.revision : null;
  const onImageError = useCallback(() => { if (currentRevision !== null) renew(currentRevision); }, [renew, currentRevision]);
  return { uri: preview?.uri ?? null, error: state?.scope === scope && state.error,
    retry, onImageError };
}
