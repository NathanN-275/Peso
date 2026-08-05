import { createClient, type Session } from '@supabase/supabase-js';

export type TraceEvent = {
  index: number;
  type: string;
  at: string;
  payload: Record<string, unknown>;
};

export type TraceRunSummary = {
  run_id: string;
  status: 'running' | 'completed' | 'failed';
  created_at: string;
  finished_at: string | null;
  video_id: string;
  exercise_type: string;
  view_type: string;
  model_version: string;
  event_count: number;
};

export type TraceRun = TraceRunSummary & {
  format_version: number;
  metadata: Record<string, unknown>;
  events: TraceEvent[];
};

export type FeedbackStatus = 'good' | 'bad' | 'uncertain';
export type FeedbackSeverity = 'visual_only' | 'metric_changing' | 'blocking';
export type FeedbackVisibility = 'visible' | 'occluded' | 'invalid';
export type FeedbackSourceStage = 'raw_pose' | 'pin_fusion' | 'pose_repair' | 'barbell_tracking';

export type FeedbackKeyframe = {
  timestamp_ms: number;
  source_frame_index: number | null;
};

export type FeedbackCorrection = FeedbackKeyframe & {
  target: string;
  x: number;
  y: number;
  visibility: FeedbackVisibility;
};

export type FeedbackAnnotation = {
  id: string;
  status: FeedbackStatus;
  start_ms: number;
  end_ms: number;
  systems: string[];
  issue_types: string[];
  landmarks: string[];
  expected_behaviors: string[];
  source_stages?: FeedbackSourceStage[];
  severity: FeedbackSeverity;
  notes: string;
  keyframes: FeedbackKeyframe[];
  corrections: FeedbackCorrection[];
};

export type AnalysisFeedback = {
  format_version: number;
  run_id: string;
  updated_at: string | null;
  annotations: FeedbackAnnotation[];
};

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
export const backendUrl = (import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');

export const dashboardConfigError = !supabaseUrl || !supabaseAnonKey
  ? 'Missing dashboard environment. Start it with npm run dashboard from the project root.'
  : null;

export const supabase = dashboardConfigError
  ? null
  : createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    });

async function request(path: string, session: Session, init: RequestInit = {}) {
  const response = await fetch(`${backendUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      ...init.headers,
    },
  });

  if (!response.ok) {
    throw new Error(await response.text() || `Request failed (${response.status})`);
  }
  return response;
}

export async function listRuns(session: Session): Promise<TraceRunSummary[]> {
  const response = await request('/dev/analysis-runs', session);
  const payload = await response.json() as { runs?: TraceRunSummary[] };
  return payload.runs || [];
}

export async function getRun(runId: string, session: Session): Promise<TraceRun> {
  const response = await request(`/dev/analysis-runs/${runId}`, session);
  return response.json() as Promise<TraceRun>;
}

export async function getReview(runId: string, session: Session): Promise<TraceRun> {
  const response = await request(`/dev/analysis-runs/${runId}/review`, session);
  return response.json() as Promise<TraceRun>;
}

export async function getPlaybackUrl(videoId: string, session: Session): Promise<string> {
  const response = await request(`/videos/${videoId}/playback-url`, session);
  const payload = await response.json() as { video_url: string };
  return payload.video_url;
}

export async function downloadTrace(runId: string, session: Session): Promise<Blob> {
  const response = await request(`/dev/analysis-runs/${runId}/export`, session);
  return response.blob();
}

export async function getFeedback(runId: string, session: Session): Promise<AnalysisFeedback> {
  const response = await request(`/dev/analysis-runs/${runId}/feedback`, session);
  return response.json() as Promise<AnalysisFeedback>;
}

export async function saveFeedback(
  runId: string,
  annotations: FeedbackAnnotation[],
  session: Session,
): Promise<AnalysisFeedback> {
  const response = await request(`/dev/analysis-runs/${runId}/feedback`, session, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ annotations }),
  });
  return response.json() as Promise<AnalysisFeedback>;
}

export async function downloadFeedback(runId: string, session: Session): Promise<Blob> {
  const response = await request(`/dev/analysis-runs/${runId}/feedback/export`, session);
  return response.blob();
}

export async function streamRunEvents(
  runId: string,
  after: number,
  session: Session,
  onEvent: (event: TraceEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await request(`/dev/analysis-runs/${runId}/events?after=${after}`, session, { signal });
  if (!response.body) {
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) {
      return;
    }
    buffer += decoder.decode(value, { stream: true });
    const messages = buffer.split('\n\n');
    buffer = messages.pop() || '';
    for (const message of messages) {
      const line = message.split('\n').find((entry) => entry.startsWith('data: '));
      if (!line) {
        continue;
      }
      const event = JSON.parse(line.slice(6)) as TraceEvent;
      if (event.type !== 'keepalive') {
        onEvent(event);
      }
    }
  }
}
