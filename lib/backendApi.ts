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
const playbackUrlCache = new Map<string, { url: string; expiresAt: number }>();

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

async function requestJson<T>(path: string, accessToken?: string, init?: RequestInit): Promise<T> {
  // Every backend call flows through this helper.
  const backend = ensureBackendApiUrl();
  const requestUrl = `${backend.url}${path}`;
  const method = init?.method ?? 'GET';
  const hasBody = typeof init?.body !== 'undefined';
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
      ...(init?.headers ?? {}),
    };
    const requestOptions = {
      ...init,
      headers,
    };

    try {
      // Try the configured backend URL first.
      response = await fetch(requestUrl, requestOptions);
    } catch (error) {
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

      response = await fetch(fallbackUrl, requestOptions);
    }
  } catch (error) {
    // Expand network failures with the exact URL and environment details.
    const message = error instanceof Error ? error.message : 'Unknown network error.';
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

export async function testBackendConnection() {
  // Health checks confirm the backend is reachable before upload starts.
  return requestJson<{ status: string }>('/health');
}

export async function triggerVideoAnalysis(videoId: string, accessToken: string) {
  // Queue analysis for an uploaded video.
  const analyzePath = `/analyze/${videoId}`;

  return requestJson<{ video_id: string; status: VideoAnalysisStatus }>(
    analyzePath,
    accessToken,
    {
      method: 'POST',
    }
  );
}

export async function fetchVideoStatus(videoId: string, accessToken: string) {
  // Poll the backend for the current analysis status.
  return requestJson<VideoStatusResponse>(`/videos/${videoId}/status`, accessToken);
}

export async function fetchAnalysisResult(videoId: string, accessToken: string) {
  // Fetch the completed analysis payload once processing finishes.
  return requestJson<AnalysisResponse>(`/analysis/${videoId}`, accessToken);
}

export async function getSavedVideos(accessToken: string) {
  // Saved video lists include thumbnail URLs only; playback URLs are fetched on demand.
  return requestJson<SavedVideo[]>('/videos/saved', accessToken);
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

export async function exportAnalyzedVideo(videoId: string, accessToken: string) {
  // Render and sign an analyzed copy with the pose overlay burned in.
  return requestJson<{
    video_id: string;
    analysis_id: string;
    storage_path: string;
    export_url: string;
  }>(
    `/videos/${videoId}/analyzed-export`,
    accessToken,
    {
      method: 'POST',
    }
  );
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
