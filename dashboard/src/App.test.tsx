import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getReview: vi.fn(),
  getPlaybackUrl: vi.fn(),
  streamRunEvents: vi.fn(),
  getFeedback: vi.fn(),
  saveFeedback: vi.fn(),
  downloadTrace: vi.fn(),
  downloadFeedback: vi.fn(),
  getSession: vi.fn(),
  unsubscribe: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock('./api', () => ({
  dashboardConfigError: null,
  listRuns: api.listRuns,
  getReview: api.getReview,
  getPlaybackUrl: api.getPlaybackUrl,
  streamRunEvents: api.streamRunEvents,
  getFeedback: api.getFeedback,
  saveFeedback: api.saveFeedback,
  downloadTrace: api.downloadTrace,
  downloadFeedback: api.downloadFeedback,
  supabase: {
    auth: {
      getSession: api.getSession,
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: api.unsubscribe } } }),
      signOut: api.signOut,
    },
  },
}));

import App from './App';

const session = { access_token: 'test-access-token' } as never;
const createdAt = '2026-07-14T04:00:00.000Z';

function run(overrides: Record<string, unknown> = {}) {
  return {
    format_version: 1,
    run_id: 'run-1',
    status: 'completed',
    created_at: createdAt,
    finished_at: createdAt,
    video_id: 'video-1',
    exercise_type: 'back_squat',
    view_type: 'side',
    model_version: 'trace-test-model',
    events: [
      { index: 0, type: 'analysis_started', at: createdAt, payload: { stage: 'initializing' } },
      {
        index: 1,
        type: 'snapshot',
        at: createdAt,
        payload: {
          name: 'quality_preflight',
          quality_preflight: {
            status: 'warning',
            overallConfidence: 0.78,
            checks: { lighting: { status: 'warning', reasonCode: 'lighting_quality_low' } },
          },
        },
      },
      {
        index: 2,
        type: 'snapshot',
        at: createdAt,
        payload: {
          name: 'raw_pose',
          frames: [{ source_frame_index: 1, timestamp_ms: 0, landmarks: { left_shoulder: { x: 0.2, y: 0.3, visibility: 0.8 } } }],
        },
      },
      {
        index: 3,
        type: 'snapshot',
        at: createdAt,
        payload: {
          name: 'pin_fusion',
          frames: [{ source_frame_index: 1, timestamp_ms: 0, landmarks: { left_shoulder: { x: 0.25, y: 0.35, accepted_source: 'pin_guided', visibility: 0.9 } } }],
          manual_tracking: { tracks: { upper_back: { 1: { x: 0.3, y: 0.25, confidence: 0.8 } } } },
          tracking_assistance: { actualMode: 'pin_assisted' },
        },
      },
      {
        index: 4,
        type: 'snapshot',
        at: createdAt,
        payload: {
          name: 'pose_repair',
          frames: [{ source_frame_index: 12, timestamp_ms: 500, landmarks: { left_shoulder: { x: 0.28, y: 0.36, accepted_source: 'pose_repair_velocity', visibility: 0.45, pose_repair_reasons: ['plate_occlusion'] } } }],
          pose_repair: { detector_occlusion_count: 1 },
        },
      },
      { index: 5, type: 'stage_completed', at: createdAt, payload: { name: 'pose_repair', duration_ms: 18 } },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getSession.mockResolvedValue({ data: { session } });
  api.listRuns.mockResolvedValue([{ ...run(), event_count: 5 }]);
  api.getReview.mockResolvedValue(run());
  api.getPlaybackUrl.mockResolvedValue('http://localhost/video.mp4');
  api.streamRunEvents.mockResolvedValue(undefined);
  api.getFeedback.mockResolvedValue({ format_version: 1, run_id: 'run-1', updated_at: null, annotations: [] });
  api.saveFeedback.mockImplementation(async (_runId, annotations) => ({ format_version: 1, run_id: 'run-1', updated_at: createdAt, annotations }));
  api.downloadTrace.mockResolvedValue(new Blob(['trace']));
  api.downloadFeedback.mockResolvedValue(new Blob(['feedback']));
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:trace') });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
});

afterEach(() => window.localStorage.clear());

describe('analysis dashboard', () => {
  it('renders generic-lift trace data and synchronizes the inspector with the scrubber', async () => {
    api.listRuns.mockResolvedValue([{ ...run({ exercise_type: 'overhead_press', view_type: 'front' }), event_count: 5 }]);
    api.getReview.mockResolvedValue(run({ exercise_type: 'overhead_press', view_type: 'front' }));

    render(<App />);

    expect(await screen.findByRole('heading', { name: 'overhead_press · front' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Diagnostics' }));
    fireEvent.change(screen.getByLabelText('Frame scrubber'), { target: { value: '0.5' } });
    expect(await screen.findByText('Frame 12 · 0.5s')).toBeInTheDocument();
    expect(screen.getByText('Raw: 0.200, 0.300')).toBeInTheDocument();
    expect(screen.getByText('Final: 0.280, 0.360')).toBeInTheDocument();
    expect(screen.getByText('Repair/rejection: plate_occlusion')).toBeInTheDocument();
    expect(screen.getByText('pose_repair · 18ms')).toBeInTheDocument();
  });

  it('defaults to the app view and keeps diagnostics available', async () => {
    render(<App />);

    expect(await screen.findByRole('button', { name: 'App view', pressed: true })).toBeInTheDocument();
    expect(screen.getByLabelText('App-style tracking overlay')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Frame inspector' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Diagnostics' }));
    expect(await screen.findByRole('heading', { name: 'Frame inspector' })).toBeInTheDocument();
    expect(await screen.findByText('Quality preflight and sampled-frame evidence')).toBeInTheDocument();
    expect(await screen.findByText(/lighting_quality_low/)).toBeInTheDocument();
  });

  it('shows only the side-squat annotation targets', async () => {
    render(<App />);

    await screen.findByRole('heading', { name: 'back_squat · side' });
    expect(screen.getByLabelText('Upper back')).toBeInTheDocument();
    expect(screen.getByLabelText('Hip')).toBeInTheDocument();
    expect(screen.getByLabelText('Knee')).toBeInTheDocument();
    expect(screen.getByLabelText('Ankle')).toBeInTheDocument();
    expect(screen.getByLabelText('Barbell center')).toBeInTheDocument();
    expect(screen.queryByLabelText('Left eye')).not.toBeInTheDocument();
  });

  it('keeps a failed draft and offers a retry with the server error', async () => {
    api.saveFeedback.mockRejectedValueOnce(new Error('source_stages is not permitted'));
    render(<App />);

    await screen.findByRole('heading', { name: 'Feedback annotations' });
    const saveButton = await screen.findByRole('button', { name: 'Save annotation' });
    await waitFor(() => expect(saveButton).not.toBeDisabled());
    fireEvent.click(saveButton);
    await waitFor(() => expect(api.saveFeedback).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('alert')).toHaveTextContent('source_stages is not permitted');
    expect(screen.getByRole('button', { name: 'Retry save' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry save' }));
    await waitFor(() => expect(api.saveFeedback).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('adds live stage events for a running trace', async () => {
    const running = run({ status: 'running', finished_at: null });
    api.listRuns.mockResolvedValue([{ ...running, event_count: 5 }]);
    api.getReview.mockResolvedValue(running);
    api.streamRunEvents.mockImplementation(async (_runId, _after, _session, onEvent, signal) => {
      onEvent({ index: 5, type: 'stage_completed', at: createdAt, payload: { name: 'barbell_tracking', duration_ms: 42 } });
      await new Promise<void>((resolve) => signal.addEventListener('abort', () => resolve(), { once: true }));
    });

    render(<App />);

    expect(await screen.findByText('barbell_tracking · 42ms')).toBeInTheDocument();
  });

  it('downloads the redacted export bundle for the selected run', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    render(<App />);

    const button = await screen.findByRole('button', { name: 'Export trace ZIP' });
    await waitFor(() => expect(button).not.toBeDisabled());
    button.click();

    await waitFor(() => expect(api.downloadTrace).toHaveBeenCalledWith('run-1', session));
    expect(click).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:trace');
  });

  it('saves timestamped feedback annotations with the current trace', async () => {
    render(<App />);

    await screen.findByRole('heading', { name: 'Feedback annotations' });
    await screen.findByRole('heading', { name: 'back_squat · side' });
    fireEvent.click(screen.getByRole('button', { name: 'Add current frame' }));
    fireEvent.click(screen.getByLabelText('automatic pose'));
    fireEvent.click(screen.getByLabelText('drift'));
    fireEvent.click(screen.getByLabelText('hold last reliable'));
    fireEvent.click(screen.getByLabelText('pose repair'));
    fireEvent.change(screen.getByLabelText('What happened and what should improve?'), { target: { value: 'Keep the right knee stable during occlusion.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save annotation' }));

    await waitFor(() => expect(api.saveFeedback).toHaveBeenCalledWith(
      'run-1',
      [expect.objectContaining({
        status: 'bad',
        systems: ['automatic_pose'],
        issue_types: ['drift'],
        expected_behaviors: ['hold_last_reliable'],
        source_stages: ['pose_repair'],
        notes: 'Keep the right knee stable during occlusion.',
        keyframes: [expect.objectContaining({ timestamp_ms: 500, source_frame_index: 12 })],
      })],
      session,
    ));
  });

  it('restores an unsaved local note after the review payload finishes loading', async () => {
    window.localStorage.setItem('peso:analysis-annotation-draft:v1:run-1', JSON.stringify({
      annotation: {
        id: 'local-draft', status: 'bad', start_ms: 0, end_ms: 0, systems: [], issue_types: [], landmarks: [],
        expected_behaviors: [], source_stages: [], severity: 'visual_only', notes: 'Do not lose this note.', keyframes: [], corrections: [],
      },
      editingAnnotationId: null,
      savedAt: Date.now(),
    }));
    render(<App />);

    expect(await screen.findByDisplayValue('Do not lose this note.')).toBeInTheDocument();
    expect(screen.getByText('Draft saved locally')).toBeInTheDocument();
  });

  it('retries playback with a fresh signed URL after a video error', async () => {
    render(<App />);

    await waitFor(() => expect(document.querySelector('video')).not.toBeNull());
    fireEvent.error(document.querySelector('video') as Element);
    fireEvent.click(await screen.findByRole('button', { name: 'Retry playback' }));
    await waitFor(() => expect(api.getPlaybackUrl).toHaveBeenCalledTimes(2));
  });

  it('ignores a stale review response after switching runs', async () => {
    let resolveFirstReview: (value: ReturnType<typeof run>) => void;
    let resolveFirstFeedback: (value: { format_version: number; run_id: string; updated_at: null; annotations: never[] }) => void;
    const firstReview = new Promise<ReturnType<typeof run>>((resolve) => { resolveFirstReview = resolve; });
    const firstFeedback = new Promise<{ format_version: number; run_id: string; updated_at: null; annotations: never[] }>((resolve) => { resolveFirstFeedback = resolve; });
    const secondRun = run({ run_id: 'run-2', video_id: 'video-2', exercise_type: 'deadlift' });
    api.listRuns.mockResolvedValue([
      { ...run(), event_count: 5 },
      { ...secondRun, event_count: 5 },
    ]);
    api.getReview.mockImplementation((runId: string) => runId === 'run-1' ? firstReview : Promise.resolve(secondRun));
    api.getFeedback.mockImplementation((runId: string) => runId === 'run-1'
      ? firstFeedback
      : Promise.resolve({ format_version: 1, run_id: 'run-2', updated_at: null, annotations: [] }));

    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open analysis run run-2' }));
    expect(await screen.findByRole('heading', { name: 'deadlift · side' })).toBeInTheDocument();
    resolveFirstReview!(run());
    resolveFirstFeedback!({ format_version: 1, run_id: 'run-1', updated_at: null, annotations: [] });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'deadlift · side' })).toBeInTheDocument());
  });
});
