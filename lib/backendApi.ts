import {
  AnalysisResponse,
  VideoAnalysisStatus,
  VideoStatusResponse,
} from '../src/types/videoAnalysis';
import {
  getBackendApiUrl,
  getBackendConnectionDiagnostics,
  resolveBackendApiConfig,
} from './backendConfig';

function ensureBackendApiUrl() {
  const backendApiUrl = getBackendApiUrl();

  if (!backendApiUrl) {
    throw new Error(
      'Missing video analysis backend URL. Set EXPO_PUBLIC_BACKEND_URL, or run the backend locally on port 8000 while using Expo development mode.'
    );
  }

  return backendApiUrl;
}

async function requestJson<T>(path: string, accessToken?: string, init?: RequestInit): Promise<T> {
  const backend = resolveBackendApiConfig();
  const requestUrl = `${backend.url}${path}`;
  const method = init?.method ?? 'GET';
  let response: Response;

  if (__DEV__) {
    console.info('[BackendAPI] request', {
      method,
      url: requestUrl,
      backend: getBackendConnectionDiagnostics(),
    });
  }

  try {
    response = await fetch(requestUrl, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown network error.';

    console.error('[BackendAPI] fetch failed', {
      method,
      url: requestUrl,
      error,
      backend: getBackendConnectionDiagnostics(),
    });

    throw new Error(
      [
        'Backend unreachable.',
        `Current backend URL: ${backend.url}`,
        `Backend URL source: ${backend.source}`,
        `Request: ${method} ${requestUrl}`,
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
  return requestJson<{ ok: boolean }>('/health');
}

export async function triggerVideoAnalysis(videoId: string, accessToken: string) {
  const backend = resolveBackendApiConfig();
  const analyzePath = `/analyze/${videoId}`;
  const analyzeUrl = `${backend.url}${analyzePath}`;

  console.info('[BackendAPI] analyze request', {
    backendUrl: backend.url,
    backendUrlSource: backend.source,
    endpointUrl: analyzeUrl,
  });

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
