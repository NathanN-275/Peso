import type {
  AnalysisResponse,
  SaveState,
  SavedVideo,
  VideoAnalysisStatus,
  VideoStatusResponse,
} from '../src/types/videoAnalysis';
import { Platform } from 'react-native';
import {
  getBackendApiUrl,
  getBackendConnectionDiagnostics,
  resolveBackendApiConfig,
} from './backendConfig';

let loggedBackendConfig = false;
const PLAYBACK_URL_CACHE_TTL_MS = 2 * 60 * 1000;
const DEFAULT_BACKEND_REQUEST_TIMEOUT_MS = __DEV__ ? 10_000 : 30_000;
const HEALTH_CHECK_TIMEOUT_MS = __DEV__ ? 3_000 : 8_000;
const EXPORT_REQUEST_TIMEOUT_MS = 5 * 60 * 1000;
const playbackUrlCache = new Map<string, { url: string; expiresAt: number }>();

type BackendRequestInit = RequestInit & {
  timeoutMs?: number;
};

class BackendRequestTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`Request timed out after ${Math.round(timeoutMs / 1000)}s.`);
    this.name = 'BackendRequestTimeoutError';
  }
}

function ensureBackendApiUrl() {
  // Fail fast when the backend URL is missing.
  const backend = resolveBackendApiConfig();

  if (!backend.url) {
    throw new Error(
      'Missing video analysis backend URL. Set EXPO_PUBLIC_BACKEND_URL before building or running the production app.'
    );
  }

  return backend;
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
  externalSignal?: AbortSignal
) {
  const controller = new AbortController();
  let didTimeout = false;
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const handleExternalAbort = () => {
    controller.abort();
  };

  if (externalSignal?.aborted) {
    controller.abort();
  } else {
    externalSignal?.addEventListener('abort', handleExternalAbort, { once: true });
  }

  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, timeoutMs);
  }

  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    if (didTimeout) {
      throw new BackendRequestTimeoutError(timeoutMs);
    }

    throw error;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    externalSignal?.removeEventListener('abort', handleExternalAbort);
  }
}

function summarizeError(error: unknown, fallbackMessage: string) {
  return error instanceof Error ? error.message : fallbackMessage;
}

function getFirstMessageLine(message: string) {
  return message.split('\n').find((line) => line.trim().length > 0)?.trim() || message;
}

function getWebLoopbackFallbackUrl(requestUrl: string) {
  // Local web dev sometimes needs 127.0.0.1 instead of localhost.
  if (!__DEV__ || Platform.OS !== 'web' || !requestUrl.startsWith('http://localhost:')) {
    return null;
  }

  return requestUrl.replace('http://localhost:', 'http://127.0.0.1:');
}

function getHostname(value: string) {
  try {
    return new URL(value).hostname;
  } catch {
    return null;
  }
}

function isLoopbackUrl(value: string) {
  const hostname = getHostname(value);
  return hostname === 'localhost' || hostname === '127.0.0.1';
}

function buildBackendUnreachableMessage({
  backend,
  diagnostics,
  fallbackUrl,
  message,
  method,
  requestUrl,
}: {
  backend: ReturnType<typeof resolveBackendApiConfig>;
  diagnostics: ReturnType<typeof getBackendConnectionDiagnostics>;
  fallbackUrl: string | null;
  message: string;
  method: string;
  requestUrl: string;
}) {
  const hints = [
    `No response came back from ${backend.url}. FastAPI may not be running or may still be starting.`,
  ];

  if (__DEV__) {
    if (
      Platform.OS !== 'web'
      && diagnostics.target === 'physical-device'
      && diagnostics.explicitUrlIsLoopback
    ) {
      hints.push(
        'Loopback backend URLs point at the phone in physical-device mode. Use your Mac LAN IP, for example http://10.0.0.221:8000.'
      );
    }

    if (Platform.OS === 'web' && isLoopbackUrl(backend.url)) {
      hints.push('For Expo web, start the backend with npm start or run FastAPI on 127.0.0.1:8000.');
    }

    if (diagnostics.explicitUrl && diagnostics.explicitUrl !== diagnostics.url) {
      hints.push(
        `The configured backend URL (${diagnostics.explicitUrl}) was resolved to ${diagnostics.url} for this platform.`
      );
    }

    if (backend.source === 'env override') {
      hints.push(
        'If this URL differs from your current .env, restart Expo with npm start so EXPO_PUBLIC_BACKEND_URL is rebuilt.'
      );
    }

    hints.push(
      'If /health works in a browser but the app still fails, check CORS, device network, and firewall access.'
    );
  }

  return [
    'Backend unreachable.',
    `Current backend URL: ${backend.url}`,
    `Backend URL source: ${backend.source}`,
    `Request: ${method} ${requestUrl}`,
    ...(fallbackUrl ? [`Fallback also failed: ${method} ${fallbackUrl}`] : []),
    ...hints.map((hint) => `Hint: ${hint}`),
    `Original error: ${message}`,
  ].join('\n');
}

async function requestJson<T>(path: string, accessToken?: string, init: BackendRequestInit = {}): Promise<T> {
  // Every backend call flows through this helper.
  const backend = ensureBackendApiUrl();
  const requestUrl = `${backend.url}${path}`;
  const {
    timeoutMs = DEFAULT_BACKEND_REQUEST_TIMEOUT_MS,
    signal,
    headers: initHeaders,
    ...fetchInit
  } = init;
  const method = fetchInit.method ?? 'GET';
  const hasBody = typeof fetchInit.body !== 'undefined';
  let response: Response;

  if (__DEV__ && !loggedBackendConfig) {
    // Log backend config once so connection issues are easier to trace.
    loggedBackendConfig = true;
    console.info('[BackendAPI] backend config', getBackendConnectionDiagnostics());
  }

  if (__DEV__) {
    console.info('[BackendAPI] request', {
      method,
      url: requestUrl,
      backendUrl: backend.url,
      backendUrlSource: backend.source,
    });
  }

  try {
    const headers: HeadersInit = {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(initHeaders ?? {}),
    };
    const requestOptions = {
      ...fetchInit,
      headers,
    };

    try {
      // Try the configured backend URL first.
      response = await fetchWithTimeout(requestUrl, requestOptions, timeoutMs, signal);
    } catch (error) {
      if (signal?.aborted || (error instanceof Error && error.name === 'AbortError')) {
        throw error;
      }
      const fallbackUrl = getWebLoopbackFallbackUrl(requestUrl);

      if (!fallbackUrl) {
        throw error;
      }

      if (__DEV__) {
        console.warn('[BackendAPI] localhost request failed, retrying 127.0.0.1', {
          originalUrl: requestUrl,
          fallbackUrl,
          error,
        });
      }

      response = await fetchWithTimeout(fallbackUrl, requestOptions, timeoutMs, signal);
    }
  } catch (error) {
    if (signal?.aborted || (error instanceof Error && error.name === 'AbortError')) {
      throw error;
    }
    // Expand network failures with the exact URL and environment details.
    const message = summarizeError(error, 'Unknown network error.');
    const fallbackUrl = getWebLoopbackFallbackUrl(requestUrl);
    const diagnostics = getBackendConnectionDiagnostics();

    console.error('[BackendAPI] fetch failed', {
      method,
      url: requestUrl,
      fallbackUrl,
      error,
      backend: diagnostics,
    });

    throw new Error(buildBackendUnreachableMessage({
      backend,
      diagnostics,
      fallbackUrl,
      message,
      method,
      requestUrl,
    }));
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Backend request failed with status ${response.status}.`);
  }

  return (await response.json()) as T;
}

export { getBackendApiUrl, getBackendConnectionDiagnostics };

export type { SaveState, SavedVideo };

export type StorageUsageResponse = {
  storage_limit_bytes: number;
  database_limit_bytes: number;
  monthly_egress_limit_bytes: number;
  current_storage_bytes: number;
  upload_size_bytes: number;
  playback_allowance_bytes: number;
  thumbnail_allowance_bytes: number;
  projected_peak_bytes: number;
  warning_threshold_bytes: number;
  block_threshold_bytes: number;
  status: 'ok' | 'warning' | 'blocked';
  blocked: boolean;
  message: string;
};

export type VideoCapabilitiesResponse = {
  pin_assisted_tracking: boolean;
  tracking_setup_versions: number[];
  reason: string | null;
};

export type AnalyzedVideoExportOptions = {
  pose: boolean;
  barbell: boolean;
};

export async function testBackendConnection(signal?: AbortSignal, timeoutMs = HEALTH_CHECK_TIMEOUT_MS) {
  // Health checks confirm the backend is reachable before upload starts.
  return requestJson<{ status: string }>('/health', undefined, { signal, timeoutMs });
}

export async function describeBackendRequestFailure(error: unknown, fallbackMessage: string) {
  const requestMessage = summarizeError(error, fallbackMessage);
  const diagnostics = getBackendConnectionDiagnostics();

  try {
    await testBackendConnection(undefined, HEALTH_CHECK_TIMEOUT_MS);

    return [
      requestMessage,
      `Health check succeeded at ${diagnostics.url}/health, so the backend is running but this request failed.`,
    ].join('\n');
  } catch (healthError) {
    const healthMessage = getFirstMessageLine(
      summarizeError(healthError, 'Backend health check failed.')
    );

    return [
      requestMessage,
      `Health check failed for ${diagnostics.url}/health: ${healthMessage}`,
    ].join('\n');
  }
}

export async function fetchStorageUsage(uploadSizeBytes: number, accessToken: string) {
  const normalizedSize = Math.max(0, Math.floor(uploadSizeBytes));
  return requestJson<StorageUsageResponse>(
    `/videos/storage-usage?upload_size_bytes=${normalizedSize}`,
    accessToken
  );
}

export async function fetchVideoCapabilities(accessToken: string) {
  return requestJson<VideoCapabilitiesResponse>('/videos/capabilities', accessToken);
}

export async function triggerVideoAnalysis(videoId: string, accessToken: string, signal?: AbortSignal) {
  // Queue analysis for an uploaded video.
  const analyzePath = `/analyze/${videoId}`;

  return requestJson<{ video_id: string; status: VideoAnalysisStatus }>(
    analyzePath,
    accessToken,
    {
      method: 'POST',
      signal,
    }
  );
}

export async function fetchVideoStatus(videoId: string, accessToken: string, signal?: AbortSignal) {
  // Poll the backend for the current analysis status.
  return requestJson<VideoStatusResponse>(`/videos/${videoId}/status`, accessToken, { signal });
}

export async function fetchAnalysisResult(videoId: string, accessToken: string, signal?: AbortSignal) {
  // Fetch the completed analysis payload once processing finishes.
  return requestJson<AnalysisResponse>(`/analysis/${videoId}`, accessToken, { signal });
}

export async function getSavedVideos(accessToken: string, signal?: AbortSignal) {
  // Saved video lists include thumbnail URLs only; playback URLs are fetched on demand.
  return requestJson<SavedVideo[]>('/videos/saved', accessToken, { signal });
}

export async function getVideoPlaybackUrl(videoId: string, accessToken: string) {
  const cacheKey = `${accessToken}:${videoId}`;
  const cached = playbackUrlCache.get(cacheKey);

  if (cached && cached.expiresAt > Date.now()) {
    return {
      video_id: videoId,
      video_url: cached.url,
      expires_in: Math.floor((cached.expiresAt - Date.now()) / 1000),
    };
  }

  const response = await requestJson<{
    video_id: string;
    video_url: string;
    expires_in: number;
  }>(`/videos/${videoId}/playback-url`, accessToken);

  playbackUrlCache.set(cacheKey, {
    url: response.video_url,
    expiresAt: Date.now() + PLAYBACK_URL_CACHE_TTL_MS,
  });

  return response;
}

export async function saveAnalyzedVideo(videoId: string, accessToken: string) {
  // Persist the analyzed clip to the user's saved list.
  return requestJson<{ video_id: string; save_state: SaveState }>(
    `/videos/${videoId}/save`,
    accessToken,
    {
      method: 'POST',
    }
  );
}

export async function exportAnalyzedVideo(
  videoId: string,
  accessToken: string,
  options: AnalyzedVideoExportOptions = { pose: true, barbell: false }
) {
  // Render and sign an analyzed copy with the requested overlays burned in.
  return requestJson<{
    video_id: string;
    analysis_id: string;
    storage_path: string;
    export_url: string;
    variant: string;
  }>(
    `/videos/${videoId}/analyzed-export`,
    accessToken,
    {
      method: 'POST',
      body: JSON.stringify(options),
      timeoutMs: EXPORT_REQUEST_TIMEOUT_MS,
    }
  );
}

export async function deleteAccount(accessToken: string) {
  return requestJson<{ deleted: boolean }>('/account', accessToken, {
    method: 'DELETE',
  });
}

export async function getSavedVideoPlaybackUrl(videoId: string, accessToken: string) {
  return requestJson<{
    video_id: string;
    video_url: string;
  }>(`/videos/${videoId}/playback-url`, accessToken);
}

export async function discardAnalyzedVideo(videoId: string, accessToken: string) {
  // Delete the upload and its analysis result from the backend.
  return requestJson<{ video_id: string; discarded: boolean }>(
    `/videos/${videoId}/discard`,
    accessToken,
    {
      method: 'POST',
    }
  );
}

export async function deleteSavedVideo(videoId: string, accessToken: string) {
  // Saved-video deletion uses the same backend cleanup path as discarding.
  return discardAnalyzedVideo(videoId, accessToken);
}
