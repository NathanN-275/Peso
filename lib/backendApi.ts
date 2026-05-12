import {
  AnalysisResponse,
  VideoAnalysisStatus,
  VideoStatusResponse,
} from '../src/types/videoAnalysis';

const backendApiUrl = process.env.EXPO_PUBLIC_BACKEND_URL?.replace(/\/+$/, '') ?? '';

function ensureBackendApiUrl() {
  if (!backendApiUrl) {
    throw new Error('Missing EXPO_PUBLIC_BACKEND_URL for video analysis backend.');
  }

  return backendApiUrl;
}

async function requestJson<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${ensureBackendApiUrl()}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Backend request failed with status ${response.status}.`);
  }

  return (await response.json()) as T;
}

export async function triggerVideoAnalysis(videoId: string, accessToken: string) {
  return requestJson<{ video_id: string; status: VideoAnalysisStatus }>(
    `/analyze/${videoId}`,
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
