import {
  AnalysisResponse,
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

function ensureBackendApiUrl() {
  const backend = resolveBackendApiConfig();

  if (!backend.url) {
    throw new Error(
      'Missing video analysis backend URL. Set EXPO_PUBLIC_BACKEND_URL before building or running the production app.'
    );
  }

  return backend;
}

function getWebLoopbackFallbackUrl(requestUrl: string) {
  if (!__DEV__ || Platform.OS !== 'web' || !requestUrl.startsWith('http://localhost:')) {
    return null;
  }

  return requestUrl.replace('http://localhost:', 'http://127.0.0.1:');
}

async function requestJson<T>(path: string, accessToken?: string, init?: RequestInit): Promise<T> {
  const backend = ensureBackendApiUrl();
  const requestUrl = `${backend.url}${path}`;
  const method = init?.method ?? 'GET';
  const hasBody = typeof init?.body !== 'undefined';
  let response: Response;

  if (__DEV__ && !loggedBackendConfig) {
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
    const message = error instanceof Error ? error.message : 'Unknown network error.';
    const fallbackUrl = getWebLoopbackFallbackUrl(requestUrl);

    console.error('[BackendAPI] fetch failed', {
      method,
      url: requestUrl,
      fallbackUrl,
      error,
      backend: getBackendConnectionDiagnostics(),
    });

    throw new Error(
      [
        'Backend unreachable.',
        `Current backend URL: ${backend.url}`,
        `Backend URL source: ${backend.source}`,
        `Request: ${method} ${requestUrl}`,
        ...(fallbackUrl ? [`Fallback also failed: ${method} ${fallbackUrl}`] : []),
        'Check that FastAPI is running on 0.0.0.0:8000.',
        'Check that your phone/simulator and computer are on the same network.',
        `Original error: ${message}`,
      ].join('\n')
    );
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Backend request failed with status ${response.status}.`);
  }

  return (await response.json()) as T;
}

export { getBackendApiUrl, getBackendConnectionDiagnostics };

export async function testBackendConnection() {
  return requestJson<{ status: string }>('/health');
}

export async function triggerVideoAnalysis(videoId: string, accessToken: string) {
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
  return requestJson<VideoStatusResponse>(`/videos/${videoId}/status`, accessToken);
}

export async function fetchAnalysisResult(videoId: string, accessToken: string) {
  return requestJson<AnalysisResponse>(`/analysis/${videoId}`, accessToken);
}

export async function saveAnalyzedVideo(videoId: string, accessToken: string) {
  return requestJson<{ video_id: string; is_saved: boolean }>(
    `/videos/${videoId}/save`,
    accessToken,
    {
      method: 'POST',
    }
  );
}

export async function discardAnalyzedVideo(videoId: string, accessToken: string) {
  return requestJson<{ video_id: string; discarded: boolean }>(
    `/videos/${videoId}`,
    accessToken,
    {
      method: 'DELETE',
    }
  );
}
