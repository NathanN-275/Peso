import Constants from 'expo-constants';
import { Platform } from 'react-native';

import {
  AnalysisResponse,
  VideoAnalysisStatus,
  VideoStatusResponse,
} from '../src/types/videoAnalysis';

const DEFAULT_BACKEND_PORT = '8000';

function normalizeBackendApiUrl(value?: string | null) {
  return value?.trim().replace(/\/+$/, '') ?? '';
}

function inferDevelopmentBackendApiUrl() {
  const hostUri = Constants.expoConfig?.hostUri?.trim();

  if (hostUri) {
    try {
      const resolvedHostUri = hostUri.includes('://') ? hostUri : `http://${hostUri}`;
      const { hostname } = new URL(resolvedHostUri);
      return `http://${hostname}:${DEFAULT_BACKEND_PORT}`;
    } catch {
      // Ignore malformed host URIs and fall through to platform defaults.
    }
  }

  if (Platform.OS === 'android') {
    return `http://10.0.2.2:${DEFAULT_BACKEND_PORT}`;
  }

  return `http://127.0.0.1:${DEFAULT_BACKEND_PORT}`;
}

const backendApiUrl = normalizeBackendApiUrl(
  process.env.EXPO_PUBLIC_BACKEND_URL || (__DEV__ ? inferDevelopmentBackendApiUrl() : '')
);

function ensureBackendApiUrl() {
  if (!backendApiUrl) {
    throw new Error(
      'Missing video analysis backend URL. Set EXPO_PUBLIC_BACKEND_URL, or run the backend locally on port 8000 while using Expo development mode.'
    );
  }

  return backendApiUrl;
}

async function requestJson<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  const requestUrl = `${ensureBackendApiUrl()}${path}`;
  let response: Response;

  try {
    response = await fetch(requestUrl, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown network error.';
    throw new Error(`Unable to reach the video analysis backend at ${requestUrl}. ${message}`);
  }

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
