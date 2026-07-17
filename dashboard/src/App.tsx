import { FormEvent, MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Session } from '@supabase/supabase-js';
import {
  dashboardConfigError,
  downloadFeedback,
  downloadTrace,
  getFeedback,
  getPlaybackUrl,
  getReview,
  listRuns,
  saveFeedback,
  streamRunEvents,
  supabase,
  type AnalysisFeedback,
  type FeedbackAnnotation,
  type FeedbackCorrection,
  type FeedbackSeverity,
  type FeedbackSourceStage,
  type FeedbackStatus,
  type FeedbackVisibility,
  type TraceEvent,
  type TraceRun,
  type TraceRunSummary,
} from './api';
import { clearAnnotationDraft, loadAnnotationDraft, saveAnnotationDraft } from './annotationDraft';
import {
  appViewConnections,
  appViewKeypoints,
  mapPointToCoverStage,
  sideSquatAnnotationTargets,
  visibleBarbellPoints,
  type AppViewBarbellPoint,
} from './appView';

type Frame = {
  timestamp_ms?: number;
  source_frame_index?: number;
  landmarks?: Record<string, Point>;
};

type Point = {
  x?: number;
  y?: number;
  visibility?: number;
  confidence?: number;
  accepted_source?: string;
  tracking_state?: string;
  manual_source?: string;
  pose_repair_reasons?: string[];
  chain_failure_reason?: string;
  occluded?: boolean;
  tracking_lost?: number;
  stale_track?: number;
};

type Snapshot = TraceEvent & {
  payload: TraceEvent['payload'] & { name?: string; frames?: Frame[] };
};

const SKELETON_PAIRS = [
  ['left_shoulder', 'left_hip'],
  ['left_hip', 'left_knee'],
  ['left_knee', 'left_ankle'],
  ['right_shoulder', 'right_hip'],
  ['right_hip', 'right_knee'],
  ['right_knee', 'right_ankle'],
];

const FEEDBACK_SYSTEMS = [
  'automatic_pose',
  'pin_tracking',
  'barbell_tracking',
  'rep_detection',
  'final_metrics',
];
const FEEDBACK_ISSUE_TYPES = [
  'wrong_point',
  'drift',
  'swap',
  'missing_detection',
  'false_positive',
  'failed_recovery',
  'bad_rejection',
  'incorrect_metric',
];
const FEEDBACK_EXPECTED_BEHAVIORS = [
  'track_normally',
  'prefer_pin',
  'hold_last_reliable',
  'interpolate_briefly',
  'mark_occluded',
  'reject_frame',
  'recover_tracking',
];
const FEEDBACK_SOURCE_STAGES: FeedbackSourceStage[] = [
  'raw_pose', 'pin_fusion', 'pose_repair', 'barbell_tracking',
];

function newAnnotation(timeSeconds: number): FeedbackAnnotation {
  const timestamp = Math.round(timeSeconds * 1000);
  return {
    id: globalThis.crypto?.randomUUID?.() || `annotation-${Date.now()}`,
    status: 'bad',
    start_ms: timestamp,
    end_ms: timestamp,
    systems: [],
    issue_types: [],
    landmarks: [],
    expected_behaviors: [],
    source_stages: [],
    severity: 'visual_only',
    notes: '',
    keyframes: [],
    corrections: [],
  };
}

function toggleListValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((entry) => entry !== value) : [...values, value];
}

function timestampLabel(timestampMs: number): string {
  return `${(timestampMs / 1000).toFixed(2)}s`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function snapshots(run: TraceRun | null): Snapshot[] {
  return (run?.events || []).filter((event): event is Snapshot => event.type === 'snapshot');
}

function snapshotByName(run: TraceRun | null, name: string): Snapshot | undefined {
  return snapshots(run).find((event) => event.payload.name === name);
}

export function nearestFrame(snapshot: Snapshot | undefined, timeSeconds: number): Frame | null {
  const frames = snapshot?.payload.frames || [];
  if (!frames.length) {
    return null;
  }
  const target = timeSeconds * 1000;
  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if ((frames[middle].timestamp_ms || 0) < target) low = middle + 1;
    else high = middle;
  }
  const following = frames[low];
  const previous = frames[Math.max(0, low - 1)];
  return Math.abs((previous.timestamp_ms || 0) - target) <= Math.abs((following.timestamp_ms || 0) - target)
    ? previous
    : following;
}

function isEmptyAnnotation(annotation: FeedbackAnnotation): boolean {
  return !annotation.notes
    && !annotation.systems.length
    && !annotation.issue_types.length
    && !annotation.landmarks.length
    && !annotation.expected_behaviors.length
    && !(annotation.source_stages || []).length
    && !annotation.keyframes.length
    && !annotation.corrections.length;
}

function displayTime(value: string | null): string {
  if (!value) {
    return 'Running';
  }
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function asPoint(value: unknown): Point | null {
  const record = asRecord(value);
  return typeof record.x === 'number' && typeof record.y === 'number' ? record as Point : null;
}

function pointPosition(point: Point | null | undefined): string {
  return typeof point?.x === 'number' && typeof point?.y === 'number'
    ? `${point.x.toFixed(3)}, ${point.y.toFixed(3)}`
    : 'missing';
}

function pointState(point: Point | null | undefined): string {
  if (!point) {
    return 'not available';
  }
  const source = point.accepted_source || point.manual_source || point.tracking_state || 'model';
  const confidence = point.visibility ?? point.confidence;
  return `${source} · confidence ${typeof confidence === 'number' ? confidence.toFixed(2) : 'n/a'}`;
}

function pointWarning(point: Point | null | undefined): string | null {
  if (!point) {
    return null;
  }
  if (point.chain_failure_reason) {
    return point.chain_failure_reason;
  }
  if (point.pose_repair_reasons?.length) {
    return point.pose_repair_reasons.join(', ');
  }
  if (point.accepted_source === 'gap' || point.occluded || point.tracking_lost || point.stale_track) {
    return 'occluded, rejected, or stale';
  }
  return null;
}

function manualTrackPoints(manualTracking: unknown, sourceFrameIndex?: number): Array<{ name: string; point: Point }> {
  if (typeof sourceFrameIndex !== 'number') {
    return [];
  }
  const tracks = asRecord(asRecord(manualTracking).tracks);
  return Object.entries(tracks).flatMap(([name, value]) => {
    const entries = Object.entries(asRecord(value));
    const exact = asPoint(asRecord(value)[String(sourceFrameIndex)]);
    const nearest = entries
      .map(([index, point]) => ({ index: Number(index), point: asPoint(point) }))
      .filter((entry): entry is { index: number; point: Point } => Number.isFinite(entry.index) && entry.point !== null)
      .sort((first, second) => Math.abs(first.index - sourceFrameIndex) - Math.abs(second.index - sourceFrameIndex))[0]?.point;
    const point = exact || nearest;
    return point ? [{ name, point }] : [];
  });
}

function Overlay({
  frame,
  color,
  label,
  showLabels,
}: {
  frame: Frame | null;
  color: string;
  label: string;
  showLabels: boolean;
}) {
  if (!frame?.landmarks) {
    return null;
  }
  const landmarks = frame.landmarks;
  const pointFor = (name: string) => landmarks[name];
  return (
    <svg className="pose-overlay" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label={label}>
      {SKELETON_PAIRS.map(([firstName, secondName]) => {
        const first = pointFor(firstName);
        const second = pointFor(secondName);
        if (typeof first?.x !== 'number' || typeof first?.y !== 'number' || typeof second?.x !== 'number' || typeof second?.y !== 'number') {
          return null;
        }
        return <line key={`${firstName}-${secondName}`} x1={first.x} y1={first.y} x2={second.x} y2={second.y} stroke={color} strokeWidth="0.006" />;
      })}
      {Object.entries(landmarks).map(([name, point]) => {
        if (typeof point.x !== 'number' || typeof point.y !== 'number') {
          return null;
        }
        return (
          <g key={name}>
            <circle cx={point.x} cy={point.y} r="0.01" fill={color}><title>{name}</title></circle>
            {showLabels ? <text className="overlay-label" x={point.x + 0.012} y={point.y - 0.012} fill={color}>{name.replace(/_/g, ' ')}</text> : null}
          </g>
        );
      })}
    </svg>
  );
}

function ManualTracksOverlay({ points, showLabels }: { points: Array<{ name: string; point: Point }>; showLabels: boolean }) {
  if (!points.length) {
    return null;
  }
  return (
    <svg className="pose-overlay" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Manual pin tracks">
      {points.map(({ name, point }) => (
        <g key={name}>
          <rect x={(point.x || 0) - 0.01} y={(point.y || 0) - 0.01} width="0.02" height="0.02" fill="#43e870" stroke="#06120b" strokeWidth="0.003" />
          {showLabels ? <text className="overlay-label" x={(point.x || 0) + 0.012} y={(point.y || 0) - 0.012} fill="#43e870">{name.replace(/_/g, ' ')}</text> : null}
        </g>
      ))}
    </svg>
  );
}

function WarningOverlay({ frame }: { frame: Frame | null }) {
  const warnings = Object.entries(frame?.landmarks || {})
    .map(([name, point]) => ({ name, point, warning: pointWarning(point) }))
    .filter((entry): entry is { name: string; point: Point; warning: string } => Boolean(entry.warning));
  if (!warnings.length) {
    return null;
  }
  return (
    <svg className="pose-overlay" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Warning markers">
      {warnings.map(({ name, point, warning }) => (
        <g key={name}>
          <circle cx={point.x} cy={point.y} r="0.022" fill="none" stroke="#ff6680" strokeWidth="0.005"><title>{`${name}: ${warning}`}</title></circle>
          <text className="overlay-warning" x={(point.x || 0) + 0.02} y={(point.y || 0) + 0.02}>!</text>
        </g>
      ))}
    </svg>
  );
}

function CorrectionOverlay({ corrections, showLabels }: { corrections: FeedbackCorrection[]; showLabels: boolean }) {
  if (!corrections.length) {
    return null;
  }
  return (
    <svg className="pose-overlay correction-overlay" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Ground-truth corrections">
      {corrections.map((correction, index) => (
        <g key={`${correction.target}-${correction.timestamp_ms}-${index}`}>
          <circle cx={correction.x} cy={correction.y} r="0.014" fill="#ff9254" stroke="#2c1505" strokeWidth="0.004">
            <title>{`${correction.target}: ${correction.visibility}`}</title>
          </circle>
          <path d={`M ${correction.x - 0.009} ${correction.y} L ${correction.x + 0.009} ${correction.y} M ${correction.x} ${correction.y - 0.009} L ${correction.x} ${correction.y + 0.009}`} stroke="#2c1505" strokeWidth="0.003" />
          {showLabels ? <text className="overlay-label" x={correction.x + 0.014} y={correction.y - 0.014} fill="#ffb787">{correction.target.replace(/_/g, ' ')}</text> : null}
        </g>
      ))}
    </svg>
  );
}

function AppViewOverlay({
  frame,
  exercise,
  cameraView,
  barbellPoints,
  currentTime,
  sourceAspectRatio,
  showPose,
  showBarbell,
}: {
  frame: Frame | null;
  exercise?: string;
  cameraView?: string;
  barbellPoints: AppViewBarbellPoint[];
  currentTime: number;
  sourceAspectRatio: number;
  showPose: boolean;
  showBarbell: boolean;
}) {
  const points = useMemo(
    () => showPose ? appViewKeypoints(frame, exercise, cameraView) : [],
    [cameraView, exercise, frame, showPose],
  );
  const pointsByName = useMemo(() => new Map(points.map((point) => [point.name, point])), [points]);
  const mapPoint = (point: { x: number; y: number }) => mapPointToCoverStage(point, sourceAspectRatio);
  const barbell = useMemo(
    () => showBarbell ? visibleBarbellPoints(barbellPoints, currentTime) : [],
    [barbellPoints, currentTime, showBarbell],
  );

  return (
    <svg className="pose-overlay app-view-overlay" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="App-style tracking overlay">
      {appViewConnections(points, exercise, cameraView).map(([fromName, toName]) => {
        const from = pointsByName.get(fromName);
        const to = pointsByName.get(toName);
        if (!from || !to || from.visualOnly || to.visualOnly) {
          return null;
        }
        const mappedFrom = mapPoint(from);
        const mappedTo = mapPoint(to);
        return <line key={`${fromName}-${toName}`} className={(from.estimated || to.estimated) ? 'app-view-line estimated' : 'app-view-line'} x1={mappedFrom.x} y1={mappedFrom.y} x2={mappedTo.x} y2={mappedTo.y} />;
      })}
      {barbell.length > 1 ? <polyline className="app-view-barbell" points={barbell.map((point) => {
        const mapped = mapPoint(point);
        return `${mapped.x},${mapped.y}`;
      }).join(' ')} /> : null}
      {points.map((point) => {
        const mapped = mapPoint(point);
        const state = point.visualOnly ? ' visual-only' : point.estimated ? ' estimated' : '';
        return <g key={point.name} className={`app-view-point${state}`}><circle cx={mapped.x} cy={mapped.y} r="0.012" /><text x={mapped.x + 0.018} y={mapped.y - 0.014}>{point.label}</text></g>;
      })}
      {barbell.length ? (() => {
        const current = mapPoint(barbell[barbell.length - 1]);
        return <circle className="app-view-barbell-marker" cx={current.x} cy={current.y} r="0.012" />;
      })() : null}
    </svg>
  );
}

function JsonPanel({ title, value }: { title: string; value: unknown }) {
  const record = asRecord(value);
  if (!Object.keys(record).length) {
    return null;
  }
  return (
    <section className="diagnostic-panel">
      <h3>{title}</h3>
      <pre>{JSON.stringify(record, null, 2)}</pre>
    </section>
  );
}

function SignIn({ onSession }: { onSession: (session: Session) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) {
      return;
    }
    setSubmitting(true);
    setError(null);
    const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    setSubmitting(false);
    if (signInError || !data.session) {
      setError(signInError?.message || 'Unable to create a dashboard session.');
      return;
    }
    onSession(data.session);
  };

  return (
    <main className="sign-in">
      <p className="eyebrow">LOCAL DEVELOPER TOOL</p>
      <h1>Peso Analysis Dashboard</h1>
      <p>Sign in with your existing Peso account. Your browser only receives the public Supabase key and your own session token.</p>
      <form onSubmit={submit}>
        <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [runs, setRuns] = useState<TraceRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<TraceRun | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [playbackState, setPlaybackState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [showRaw, setShowRaw] = useState(true);
  const [showPins, setShowPins] = useState(true);
  const [showRepaired, setShowRepaired] = useState(true);
  const [showBarbell, setShowBarbell] = useState(true);
  const [showLabels, setShowLabels] = useState(false);
  const [showWarnings, setShowWarnings] = useState(true);
  const [viewMode, setViewMode] = useState<'app' | 'diagnostics'>('app');
  const [appViewShowPose, setAppViewShowPose] = useState(true);
  const [appViewShowBarbell, setAppViewShowBarbell] = useState(true);
  const [sourceAspectRatio, setSourceAspectRatio] = useState(9 / 16);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<AnalysisFeedback | null>(null);
  const [draftAnnotation, setDraftAnnotation] = useState<FeedbackAnnotation>(() => newAnnotation(0));
  const [draftRunId, setDraftRunId] = useState<string | null>(null);
  const [draftSavedLocally, setDraftSavedLocally] = useState(false);
  const [editingAnnotationId, setEditingAnnotationId] = useState<string | null>(null);
  const [captureTarget, setCaptureTarget] = useState<string | null>(null);
  const [correctionVisibility, setCorrectionVisibility] = useState<FeedbackVisibility>('visible');
  const [savingFeedback, setSavingFeedback] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const runsRef = useRef<TraceRunSummary[]>([]);
  const selectedRunIdRef = useRef<string | null>(null);
  const draftSnapshotRef = useRef<{ runId: string | null; annotation: FeedbackAnnotation; editingAnnotationId: string | null } | null>(null);
  const loadRequestRef = useRef(0);
  const playbackRequestRef = useRef(0);
  const playbackFrameRef = useRef<number | null>(null);

  useEffect(() => {
    selectedRunIdRef.current = selectedRunId;
  }, [selectedRunId]);

  useEffect(() => {
    draftSnapshotRef.current = { runId: draftRunId, annotation: draftAnnotation, editingAnnotationId };
  }, [draftAnnotation, draftRunId, editingAnnotationId]);

  const refreshRuns = useCallback(async (activeSession: Session) => {
    try {
      const nextRuns = await listRuns(activeSession);
      runsRef.current = nextRuns;
      setRuns(nextRuns);
      setSelectedRunId((current) => current || nextRuns[0]?.run_id || null);
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to load analysis runs.');
    }
  }, []);

  useEffect(() => {
    if (!supabase) {
      return;
    }
    void supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => setSession(nextSession));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) {
      setRuns([]);
      setSelectedRun(null);
      setFeedback(null);
      setVideoUrl(null);
      setPlaybackState('idle');
      return;
    }
    void refreshRuns(session);
    const timer = window.setInterval(() => void refreshRuns(session), 2500);
    return () => window.clearInterval(timer);
  }, [refreshRuns, session]);

  useEffect(() => {
    if (!session || !selectedRunId) {
      return;
    }
    const controller = new AbortController();
    const requestId = ++loadRequestRef.current;
    const previousDraft = draftSnapshotRef.current;
    if (previousDraft?.runId && previousDraft.runId !== selectedRunId && !isEmptyAnnotation(previousDraft.annotation)) {
      saveAnnotationDraft(previousDraft.runId, { annotation: previousDraft.annotation, editingAnnotationId: previousDraft.editingAnnotationId, savedAt: Date.now() });
    }
    const knownVideoId = runsRef.current.find((run) => run.run_id === selectedRunId)?.video_id;
    setVideoUrl(null);
    setPlaybackState(knownVideoId ? 'loading' : 'idle');
    setPlaybackError(null);
    const loadPlayback = async (videoId: string) => {
      const playbackId = ++playbackRequestRef.current;
      try {
        const url = await getPlaybackUrl(videoId, session);
        if (!controller.signal.aborted && loadRequestRef.current === requestId && playbackRequestRef.current === playbackId) {
          setVideoUrl(url);
          setPlaybackState('loading');
        }
      } catch (nextError) {
        if (!controller.signal.aborted && loadRequestRef.current === requestId && playbackRequestRef.current === playbackId) {
          setPlaybackState('error');
          setPlaybackError(nextError instanceof Error ? nextError.message : 'Unable to load video playback.');
        }
      }
    };
    const load = async () => {
      try {
        const reviewPromise = getReview(selectedRunId, session);
        if (knownVideoId) void loadPlayback(knownVideoId);
        const [run, loadedFeedback] = await Promise.all([
          reviewPromise,
          getFeedback(selectedRunId, session),
        ]);
        if (controller.signal.aborted || loadRequestRef.current !== requestId) return;
        setSelectedRun(run);
        setFeedback(loadedFeedback);
        if (draftSnapshotRef.current?.runId !== run.run_id) {
          const storedDraft = loadAnnotationDraft(run.run_id);
          setDraftAnnotation(storedDraft?.annotation || newAnnotation(0));
          setEditingAnnotationId(storedDraft?.editingAnnotationId || null);
          setDraftRunId(run.run_id);
          setDraftSavedLocally(Boolean(storedDraft));
          setCaptureTarget(null);
          setSaveError(null);
          setCurrentTime(0);
          setVideoDuration(0);
          setSourceAspectRatio(9 / 16);
        }
        if (!knownVideoId) void loadPlayback(run.video_id);
        if (run.status === 'running') {
          await streamRunEvents(run.run_id, run.events.length, session, (event) => {
            setSelectedRun((current) => current && current.run_id === run.run_id
              ? { ...current, events: [...current.events, event] }
              : current);
          }, controller.signal);
          if (!controller.signal.aborted) {
            setSelectedRun(await getReview(run.run_id, session));
          }
        }
      } catch (nextError) {
        if (!controller.signal.aborted) {
          setError(nextError instanceof Error ? nextError.message : 'Unable to load analysis trace.');
        }
      }
    };
    void load();
    return () => controller.abort();
  }, [selectedRunId, session]);

  useEffect(() => {
    if (!draftRunId || isEmptyAnnotation(draftAnnotation)) return;
    const timer = window.setTimeout(() => {
      saveAnnotationDraft(draftRunId, { annotation: draftAnnotation, editingAnnotationId, savedAt: Date.now() });
      setDraftSavedLocally(true);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [draftAnnotation, draftRunId, editingAnnotationId]);

  useEffect(() => () => {
    if (playbackFrameRef.current !== null) window.cancelAnimationFrame(playbackFrameRef.current);
  }, []);

  const snapshotIndex = useMemo(
    () => new Map(snapshots(selectedRun).flatMap((snapshot) => typeof snapshot.payload.name === 'string' ? [[snapshot.payload.name, snapshot] as const] : [])),
    [selectedRun],
  );
  const rawSnapshot = snapshotIndex.get('raw_pose');
  const pinSnapshot = snapshotIndex.get('pin_fusion');
  const repairSnapshot = snapshotIndex.get('pose_repair');
  const barbellSnapshot = snapshotIndex.get('barbell_tracking');
  const rawFrame = useMemo(() => nearestFrame(rawSnapshot, currentTime), [currentTime, rawSnapshot]);
  const pinFrame = useMemo(() => nearestFrame(pinSnapshot, currentTime), [currentTime, pinSnapshot]);
  const repairedFrame = useMemo(() => nearestFrame(repairSnapshot, currentTime), [currentTime, repairSnapshot]);
  const selectedFrame = repairedFrame || pinFrame || rawFrame;
  const manualPoints = useMemo(
    () => manualTrackPoints(pinSnapshot?.payload.manual_tracking, pinFrame?.source_frame_index),
    [pinFrame?.source_frame_index, pinSnapshot],
  );
  const barbellPoints = useMemo<AppViewBarbellPoint[]>(() => {
    const path = asRecord(barbellSnapshot?.payload.barbell_path);
    const points = path.points;
    return Array.isArray(points) ? points.flatMap((point) => {
      const record = asRecord(point);
      if (typeof record.x !== 'number' || typeof record.y !== 'number') {
        return [];
      }
      const time = typeof record.time === 'number' ? record.time : typeof record.timestamp_ms === 'number' ? record.timestamp_ms / 1000 : 0;
      return [{
        x: record.x, y: record.y, time,
        tracking_state: typeof record.tracking_state === 'string' ? record.tracking_state : undefined,
        selected_source: typeof record.selected_source === 'string' ? record.selected_source : undefined,
        coasting_frame: record.coasting_frame === true,
        stationary_hardware_rejected: record.stationary_hardware_rejected === true,
        hardware_rejected: record.hardware_rejected === true,
        gap_reason: typeof record.gap_reason === 'string' ? record.gap_reason : undefined,
      }];
    }) : [];
  }, [barbellSnapshot]);
  const traceDuration = useMemo(() => Math.max(
    0,
    ...snapshots(selectedRun).flatMap((snapshot) => snapshot.payload.frames || []).map((frame) => (frame.timestamp_ms || 0) / 1000),
  ), [selectedRun]);
  const scrubDuration = Math.max(videoDuration, traceDuration, 1);
  const labeledLayer = repairedFrame ? 'repaired' : pinFrame ? 'pins' : 'raw';
  const inspectorLandmarks = useMemo(() => {
    const standardOrder = [
      'upper_back',
      'left_shoulder',
      'right_shoulder',
      'left_hip',
      'right_hip',
      'left_knee',
      'right_knee',
      'left_ankle',
      'right_ankle',
    ];
    const observed = new Set([
      ...Object.keys(rawFrame?.landmarks || {}),
      ...Object.keys(pinFrame?.landmarks || {}),
      ...Object.keys(repairedFrame?.landmarks || {}),
      ...manualPoints.map(({ name }) => name),
    ]);
    return [...standardOrder.filter((name) => observed.has(name)), ...[...observed].filter((name) => !standardOrder.includes(name)).sort()];
  }, [manualPoints, pinFrame, rawFrame, repairedFrame]);
  const annotationTargets = useMemo(() => {
    const isSideSquat = selectedRun?.view_type?.toLowerCase() === 'side'
      && selectedRun.exercise_type?.replace(/_/g, ' ').toLowerCase() === 'back squat';
    if (isSideSquat) {
      return sideSquatAnnotationTargets(selectedFrame);
    }
    return [...inspectorLandmarks, 'barbell_center'].map((key) => ({ key, label: key.replace(/_/g, ' ') }));
  }, [inspectorLandmarks, selectedFrame, selectedRun?.exercise_type, selectedRun?.view_type]);
  const annotationTargetLabel = (key: string) => annotationTargets.find((target) => target.key === key)?.label || key.replace(/_/g, ' ');
  const activeCorrections = useMemo(() => {
    const frameIndex = selectedFrame?.source_frame_index;
    const timestampMs = selectedFrame?.timestamp_ms ?? Math.round(currentTime * 1000);
    const savedAnnotations = feedback?.annotations || [];
    const annotations = editingAnnotationId
      ? savedAnnotations.map((annotation) => annotation.id === editingAnnotationId ? draftAnnotation : annotation)
      : [...savedAnnotations, draftAnnotation];
    return annotations.flatMap((annotation) => annotation.corrections).filter((correction) => (
      typeof frameIndex === 'number' && correction.source_frame_index === frameIndex
    ) || Math.abs(correction.timestamp_ms - timestampMs) < 20);
  }, [currentTime, draftAnnotation, editingAnnotationId, feedback, selectedFrame?.source_frame_index, selectedFrame?.timestamp_ms]);

  const scrubTo = (seconds: number) => {
    const nextTime = Math.min(Math.max(seconds, 0), scrubDuration);
    setCurrentTime(nextTime);
    if (videoRef.current) {
      videoRef.current.currentTime = nextTime;
    }
  };

  const updatePlaybackTime = (time: number) => {
    if (playbackFrameRef.current !== null) return;
    playbackFrameRef.current = window.requestAnimationFrame(() => {
      playbackFrameRef.current = null;
      setCurrentTime(time);
    });
  };

  const retryPlayback = () => {
    if (!session || !selectedRun) return;
    const requestId = ++playbackRequestRef.current;
    setPlaybackState('loading');
    setPlaybackError(null);
    void getPlaybackUrl(selectedRun.video_id, session).then((url) => {
      if (selectedRunIdRef.current === selectedRun.run_id && playbackRequestRef.current === requestId) setVideoUrl(url);
    }).catch((nextError) => {
      if (playbackRequestRef.current === requestId) {
        setPlaybackState('error');
        setPlaybackError(nextError instanceof Error ? nextError.message : 'Unable to load video playback.');
      }
    });
  };

  const exportRun = async () => {
    if (!session || !selectedRun) {
      return;
    }
    try {
      const archive = await downloadTrace(selectedRun.run_id, session);
      const url = URL.createObjectURL(archive);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `peso-analysis-trace-${selectedRun.run_id}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to export analysis trace.');
    }
  };

  const exportFeedback = async () => {
    if (!session || !selectedRun) {
      return;
    }
    try {
      const archive = await downloadFeedback(selectedRun.run_id, session);
      const url = URL.createObjectURL(archive);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `peso-analysis-feedback-${selectedRun.run_id}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to export analysis feedback.');
    }
  };

  const persistAnnotations = async (annotations: FeedbackAnnotation[]): Promise<boolean> => {
    if (!session || !selectedRun) {
      return false;
    }
    setSavingFeedback(true);
    setSaveError(null);
    try {
      const saved = await saveFeedback(selectedRun.run_id, annotations, session);
      setFeedback(saved);
      clearAnnotationDraft(selectedRun.run_id);
      setDraftSavedLocally(false);
      setError(null);
      return true;
    } catch (nextError) {
      setSaveError(nextError instanceof Error ? nextError.message : 'Unable to save analysis feedback.');
      return false;
    } finally {
      setSavingFeedback(false);
    }
  };

  const setAnnotationBoundary = (boundary: 'start_ms' | 'end_ms') => {
    const nextTimestamp = Math.round(currentTime * 1000);
    setDraftAnnotation((current) => {
      if (boundary === 'start_ms') {
        return { ...current, start_ms: nextTimestamp, end_ms: Math.max(current.end_ms, nextTimestamp) };
      }
      return { ...current, end_ms: nextTimestamp, start_ms: Math.min(current.start_ms, nextTimestamp) };
    });
  };

  const addCurrentKeyframe = () => {
    const timestampMs = selectedFrame?.timestamp_ms ?? Math.round(currentTime * 1000);
    const sourceFrameIndex = selectedFrame?.source_frame_index ?? null;
    setDraftAnnotation((current) => {
      const exists = current.keyframes.some((keyframe) => (
        sourceFrameIndex !== null && keyframe.source_frame_index === sourceFrameIndex
      ) || Math.abs(keyframe.timestamp_ms - timestampMs) < 20);
      return exists ? current : {
        ...current,
        keyframes: [...current.keyframes, { timestamp_ms: timestampMs, source_frame_index: sourceFrameIndex }],
      };
    });
  };

  const captureCorrection = (event: MouseEvent<HTMLButtonElement>) => {
    if (!captureTarget) {
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const y = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
    const timestampMs = selectedFrame?.timestamp_ms ?? Math.round(currentTime * 1000);
    const sourceFrameIndex = selectedFrame?.source_frame_index ?? null;
    setDraftAnnotation((current) => {
      const correction: FeedbackCorrection = {
        timestamp_ms: timestampMs,
        source_frame_index: sourceFrameIndex,
        target: captureTarget,
        x,
        y,
        visibility: correctionVisibility,
      };
      const corrections = current.corrections.filter((entry) => !(
        entry.target === captureTarget
        && ((sourceFrameIndex !== null && entry.source_frame_index === sourceFrameIndex)
          || Math.abs(entry.timestamp_ms - timestampMs) < 20)
      ));
      return {
        ...current,
        landmarks: current.landmarks.includes(captureTarget) ? current.landmarks : [...current.landmarks, captureTarget],
        corrections: [...corrections, correction],
      };
    });
    setCaptureTarget(null);
  };

  const saveDraftAnnotation = async () => {
    const savedAnnotations = feedback?.annotations || [];
    const nextAnnotations = editingAnnotationId
      ? savedAnnotations.map((annotation) => annotation.id === editingAnnotationId ? draftAnnotation : annotation)
      : [...savedAnnotations, draftAnnotation];
    if (await persistAnnotations(nextAnnotations)) {
      setDraftAnnotation(newAnnotation(currentTime));
      setEditingAnnotationId(null);
      setCaptureTarget(null);
      setSaveError(null);
    }
  };

  const editAnnotation = (annotation: FeedbackAnnotation) => {
    setDraftAnnotation({
      ...annotation,
      systems: [...annotation.systems],
      issue_types: [...annotation.issue_types],
      landmarks: [...annotation.landmarks],
      expected_behaviors: [...annotation.expected_behaviors],
      source_stages: [...(annotation.source_stages || [])],
      keyframes: [...annotation.keyframes],
      corrections: [...annotation.corrections],
    });
    setEditingAnnotationId(annotation.id);
    setCaptureTarget(null);
    setSaveError(null);
    scrubTo(annotation.start_ms / 1000);
  };

  const deleteAnnotation = async (annotationId: string) => {
    const nextAnnotations = (feedback?.annotations || []).filter((annotation) => annotation.id !== annotationId);
    if (await persistAnnotations(nextAnnotations)) {
      if (editingAnnotationId === annotationId) {
        setDraftAnnotation(newAnnotation(currentTime));
        setEditingAnnotationId(null);
        setCaptureTarget(null);
      }
    }
  };

  if (dashboardConfigError) {
    return <main className="sign-in"><h1>Dashboard configuration missing</h1><p>{dashboardConfigError}</p></main>;
  }
  if (!session) {
    return <SignIn onSession={setSession} />;
  }

  return (
    <main className="dashboard-shell">
      <aside className="runs-sidebar">
        <div>
          <p className="eyebrow">LOCAL DEVELOPER TOOL</p>
          <h1>Peso Analysis</h1>
          <p className="muted">Live traces and replay artifacts stay on this computer.</p>
        </div>
        <button className="secondary" onClick={() => void refreshRuns(session)}>Refresh runs</button>
        <nav aria-label="Analysis runs">
          {runs.length ? runs.map((run) => (
            <button aria-label={`Open analysis run ${run.run_id}`} className={`run-card ${selectedRunId === run.run_id ? 'selected' : ''}`} key={run.run_id} onClick={() => setSelectedRunId(run.run_id)}>
              <span className={`status ${run.status}`}>{run.status}</span>
              <strong>{run.exercise_type} · {run.view_type}</strong>
              <small>{displayTime(run.created_at)} · {run.event_count} events</small>
            </button>
          )) : <p className="muted">No local traces yet. Start an analysis from Peso.</p>}
        </nav>
        <button className="secondary sign-out" onClick={() => void supabase?.auth.signOut()}>Sign out</button>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">{selectedRun?.status || 'WAITING'}</p>
            <h2>{selectedRun ? `${selectedRun.exercise_type} · ${selectedRun.view_type}` : 'Select an analysis run'}</h2>
            <p className="muted">{selectedRun ? `Model: ${selectedRun.model_version} · ${selectedRun.events.length} trace events` : 'The dashboard will follow new analyses automatically.'}</p>
          </div>
          <div className="workspace-actions">
            <button className="secondary" disabled={!selectedRun} onClick={() => void exportRun()}>Export trace ZIP</button>
            <button disabled={!selectedRun} onClick={() => void exportFeedback()}>Export feedback bundle</button>
          </div>
        </header>
        {error ? <p className="error">{error}</p> : null}

        <section className={viewMode === 'diagnostics' ? 'video-and-inspector' : 'video-and-inspector app-view-workspace'}>
          <div className="video-panel">
            <div className="review-mode" role="group" aria-label="Review mode">
              <button type="button" className={viewMode === 'app' ? '' : 'secondary'} aria-pressed={viewMode === 'app'} onClick={() => setViewMode('app')}>App view</button>
              <button type="button" className={viewMode === 'diagnostics' ? '' : 'secondary'} aria-pressed={viewMode === 'diagnostics'} onClick={() => setViewMode('diagnostics')}>Diagnostics</button>
            </div>
            {viewMode === 'app' ? <div className="layer-controls app-view-controls">
              <label><input type="checkbox" checked={appViewShowPose} onChange={(event) => setAppViewShowPose(event.target.checked)} /> Pose overlay</label>
              <label><input type="checkbox" checked={appViewShowBarbell} onChange={(event) => setAppViewShowBarbell(event.target.checked)} /> Barbell path</label>
            </div> : <div className="layer-controls">
              <label><input type="checkbox" checked={showRaw} onChange={(event) => setShowRaw(event.target.checked)} /> Raw pose</label>
              <label><input type="checkbox" checked={showPins} onChange={(event) => setShowPins(event.target.checked)} /> Pin/manual tracks</label>
              <label><input type="checkbox" checked={showRepaired} onChange={(event) => setShowRepaired(event.target.checked)} /> Repaired pose</label>
              <label><input type="checkbox" checked={showBarbell} onChange={(event) => setShowBarbell(event.target.checked)} /> Barbell path</label>
              <label><input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} /> Labels</label>
              <label><input type="checkbox" checked={showWarnings} onChange={(event) => setShowWarnings(event.target.checked)} /> Warnings</label>
            </div>}
            <div className="video-stage">
              {videoUrl ? <video ref={videoRef} src={videoUrl} controls preload="metadata" onLoadedMetadata={(event) => { setVideoDuration(event.currentTarget.duration || 0); if (event.currentTarget.videoWidth && event.currentTarget.videoHeight) setSourceAspectRatio(event.currentTarget.videoWidth / event.currentTarget.videoHeight); }} onLoadedData={() => setPlaybackState('ready')} onError={() => { setPlaybackState('error'); setPlaybackError('Video playback failed to load.'); }} onTimeUpdate={(event) => updatePlaybackTime(event.currentTarget.currentTime)} /> : <div className="video-placeholder">{playbackState === 'loading' ? 'Loading playback…' : 'Playback becomes available when this video is stored.'}</div>}
              {playbackState === 'loading' && videoUrl ? <div className="video-load-status">Loading playback…</div> : null}
              {playbackState === 'error' ? <div className="video-load-status error"><span>{playbackError}</span><button type="button" onClick={retryPlayback}>Retry playback</button></div> : null}
              {viewMode === 'app' ? <AppViewOverlay frame={selectedFrame} exercise={selectedRun?.exercise_type} cameraView={selectedRun?.view_type} barbellPoints={barbellPoints} currentTime={currentTime} sourceAspectRatio={sourceAspectRatio} showPose={appViewShowPose} showBarbell={appViewShowBarbell} /> : <>
                {showRaw ? <Overlay frame={rawFrame} color="#f6c445" label="Raw pose" showLabels={showLabels && labeledLayer === 'raw'} /> : null}
                {showPins ? <Overlay frame={pinFrame} color="#43e870" label="Pin fusion" showLabels={showLabels && labeledLayer === 'pins'} /> : null}
                {showPins ? <ManualTracksOverlay points={manualPoints} showLabels={showLabels} /> : null}
                {showRepaired ? <Overlay frame={repairedFrame} color="#34a8ff" label="Repaired pose" showLabels={showLabels && labeledLayer === 'repaired'} /> : null}
                {showBarbell && barbellPoints.length > 1 ? <svg className="pose-overlay" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Barbell path"><polyline points={barbellPoints.map((point) => `${point.x},${point.y}`).join(' ')} fill="none" stroke="#ff63dd" strokeWidth="0.006" /></svg> : null}
                {showWarnings ? <WarningOverlay frame={repairedFrame || pinFrame || rawFrame} /> : null}
              </>}
              <CorrectionOverlay corrections={activeCorrections} showLabels={showLabels} />
              {captureTarget ? <button type="button" className="annotation-capture-surface" aria-label={`Place ${captureTarget} correction`} onClick={captureCorrection}>Click the video to place {captureTarget.replace(/_/g, ' ')}</button> : null}
            </div>
            <label className="scrubber">Frame scrubber
              <input aria-label="Frame scrubber" type="range" min="0" max={scrubDuration} step="0.01" value={Math.min(currentTime, scrubDuration)} onChange={(event) => scrubTo(Number(event.target.value))} />
            </label>
            <p className="frame-time">Frame {selectedFrame?.source_frame_index ?? '—'} · {(selectedFrame?.timestamp_ms || 0) / 1000}s</p>
          </div>

          {viewMode === 'diagnostics' ? <aside className="frame-inspector">
            <h3>Frame inspector</h3>
            {inspectorLandmarks.length ? inspectorLandmarks.map((name) => {
              const rawPoint = rawFrame?.landmarks?.[name] || null;
              const pinPoint = pinFrame?.landmarks?.[name] || manualPoints.find((entry) => entry.name === name)?.point || null;
              const finalPoint = repairedFrame?.landmarks?.[name] || null;
              const warning = pointWarning(finalPoint || pinPoint || rawPoint);
              return (
              <article key={name} className="landmark-row">
                <strong>{name.replace(/_/g, ' ')}</strong>
                <span>Raw: {pointPosition(rawPoint)}</span>
                <span>Pin: {pointPosition(pinPoint)}</span>
                <span>Final: {pointPosition(finalPoint)}</span>
                <small>Raw source: {pointState(rawPoint)}</small>
                <small>Pin state: {pointState(pinPoint)}</small>
                <small>Final source: {pointState(finalPoint)}</small>
                <small>Repair/rejection: {warning || 'none'}</small>
                <small>Occlusion: {warning?.includes('occlusion') ? 'flagged' : 'not flagged'}</small>
              </article>
              );
            }) : <p className="muted">Select a completed pose stage to inspect its landmarks.</p>}
          </aside> : null}
        </section>

        <section className="timeline-panel">
          <h3>Live stage timeline</h3>
          <div className="timeline-events">
            {selectedRun?.events.map((event) => (
              <article key={`${event.index}-${event.type}`} className={`timeline-event ${event.type}`}>
                <strong>{event.type.replace(/_/g, ' ')}</strong>
                <span>{displayTime(event.at)}</span>
                {typeof event.payload.name === 'string' ? <small>{event.payload.name}{typeof event.payload.duration_ms === 'number' ? ` · ${event.payload.duration_ms}ms` : ''}</small> : null}
              </article>
            )) || <p className="muted">No trace selected.</p>}
          </div>
        </section>

        <section className="feedback-panel">
          <header className="feedback-header">
            <div>
              <p className="eyebrow">HUMAN REVIEW</p>
              <h3>Feedback annotations</h3>
              <p className="muted">Mark useful intervals, keyframes, expected fallback behavior, and optional ground-truth points. Feedback is saved locally beside this trace.</p>
            </div>
            <small>{savingFeedback ? 'Saving…' : draftSavedLocally ? 'Draft saved locally' : feedback?.updated_at ? `Saved ${displayTime(feedback.updated_at)}` : 'Not saved yet'}</small>
          </header>
          <div className="feedback-layout">
            <form className="annotation-editor" onSubmit={(event) => { event.preventDefault(); void saveDraftAnnotation(); }}>
              <div className="annotation-form-grid">
                <label>Judgment
                  <select value={draftAnnotation.status} onChange={(event) => setDraftAnnotation((current) => ({ ...current, status: event.target.value as FeedbackStatus }))}>
                    <option value="good">Good</option>
                    <option value="bad">Bad</option>
                    <option value="uncertain">Uncertain</option>
                  </select>
                </label>
                <label>Severity
                  <select value={draftAnnotation.severity} onChange={(event) => setDraftAnnotation((current) => ({ ...current, severity: event.target.value as FeedbackSeverity }))}>
                    <option value="visual_only">Visual only</option>
                    <option value="metric_changing">Metric changing</option>
                    <option value="blocking">Blocking</option>
                  </select>
                </label>
              </div>

              <div className="annotation-range">
                <div><strong>Interval</strong><small>{timestampLabel(draftAnnotation.start_ms)}–{timestampLabel(draftAnnotation.end_ms)}</small></div>
                <button type="button" className="secondary" onClick={() => setAnnotationBoundary('start_ms')}>Set start to current</button>
                <button type="button" className="secondary" onClick={() => setAnnotationBoundary('end_ms')}>Set end to current</button>
              </div>

              <div className="annotation-keyframes">
                <div><strong>Keyframes</strong><small>{draftAnnotation.keyframes.length ? draftAnnotation.keyframes.map((keyframe) => `${timestampLabel(keyframe.timestamp_ms)}${keyframe.source_frame_index === null ? '' : ` · frame ${keyframe.source_frame_index}`}`).join(', ') : 'None yet'}</small></div>
                <button type="button" className="secondary" onClick={addCurrentKeyframe}>Add current frame</button>
              </div>

              <fieldset>
                <legend>Affected systems</legend>
                <div className="checkbox-grid">{FEEDBACK_SYSTEMS.map((system) => <label key={system}><input type="checkbox" checked={draftAnnotation.systems.includes(system)} onChange={() => setDraftAnnotation((current) => ({ ...current, systems: toggleListValue(current.systems, system) }))} />{system.replace(/_/g, ' ')}</label>)}</div>
              </fieldset>
              <fieldset>
                <legend>Issue types</legend>
                <div className="checkbox-grid">{FEEDBACK_ISSUE_TYPES.map((issue) => <label key={issue}><input type="checkbox" checked={draftAnnotation.issue_types.includes(issue)} onChange={() => setDraftAnnotation((current) => ({ ...current, issue_types: toggleListValue(current.issue_types, issue) }))} />{issue.replace(/_/g, ' ')}</label>)}</div>
              </fieldset>
              <fieldset>
                <legend>Affected landmarks or barbell</legend>
                <div className="checkbox-grid">{annotationTargets.map((target) => <label key={target.key}><input type="checkbox" checked={draftAnnotation.landmarks.includes(target.key)} onChange={() => setDraftAnnotation((current) => ({ ...current, landmarks: toggleListValue(current.landmarks, target.key) }))} />{target.label}</label>)}</div>
              </fieldset>
              <fieldset>
                <legend>Expected fallback behavior</legend>
                <div className="checkbox-grid">{FEEDBACK_EXPECTED_BEHAVIORS.map((behavior) => <label key={behavior}><input type="checkbox" checked={draftAnnotation.expected_behaviors.includes(behavior)} onChange={() => setDraftAnnotation((current) => ({ ...current, expected_behaviors: toggleListValue(current.expected_behaviors, behavior) }))} />{behavior.replace(/_/g, ' ')}</label>)}</div>
              </fieldset>
              <fieldset>
                <legend>Responsible model stages</legend>
                <div className="checkbox-grid">{FEEDBACK_SOURCE_STAGES.map((stage) => <label key={stage}><input type="checkbox" checked={(draftAnnotation.source_stages || []).includes(stage)} onChange={() => setDraftAnnotation((current) => ({ ...current, source_stages: toggleListValue(current.source_stages || [], stage) as FeedbackSourceStage[] }))} />{stage.replace(/_/g, ' ')}</label>)}</div>
              </fieldset>

              <div className="annotation-form-grid">
                <label>Correct a point on the current frame
                  <select value={captureTarget || ''} onChange={(event) => setCaptureTarget(event.target.value || null)}>
                    <option value="">Choose a landmark or barbell center</option>
                    {annotationTargets.map((target) => <option key={target.key} value={target.key}>{target.label}</option>)}
                  </select>
                </label>
                <label>Correction visibility
                  <select value={correctionVisibility} onChange={(event) => setCorrectionVisibility(event.target.value as FeedbackVisibility)}>
                    <option value="visible">Visible</option>
                    <option value="occluded">Occluded</option>
                    <option value="invalid">Invalid</option>
                  </select>
                </label>
              </div>
              {captureTarget ? <p className="capture-notice">Click the video to record the expected {annotationTargetLabel(captureTarget)} position for {timestampLabel(selectedFrame?.timestamp_ms ?? Math.round(currentTime * 1000))}.</p> : null}
              {draftAnnotation.corrections.length ? <div className="correction-list">{draftAnnotation.corrections.map((correction, index) => <button type="button" className="correction-chip" key={`${correction.target}-${correction.timestamp_ms}-${index}`} onClick={() => setDraftAnnotation((current) => ({ ...current, corrections: current.corrections.filter((_entry, entryIndex) => entryIndex !== index) }))}>{annotationTargetLabel(correction.target)} · {timestampLabel(correction.timestamp_ms)} · {correction.visibility} ×</button>)}</div> : null}

              <label>What happened and what should improve?
                <textarea value={draftAnnotation.notes} maxLength={4000} onChange={(event) => setDraftAnnotation((current) => ({ ...current, notes: event.target.value }))} placeholder="Example: The right knee drifts to the left knee during plate occlusion. Hold its last reliable position, then recover when visible." />
              </label>
              <div className="annotation-actions">
                <button type="button" className="secondary" onClick={() => { if (draftRunId) clearAnnotationDraft(draftRunId); setDraftAnnotation(newAnnotation(currentTime)); setEditingAnnotationId(null); setCaptureTarget(null); setSaveError(null); setDraftSavedLocally(false); }}>Discard draft</button>
                <button type="submit" disabled={!selectedRun || savingFeedback}>{editingAnnotationId ? 'Update annotation' : saveError ? 'Retry save' : 'Save annotation'}</button>
              </div>
              {saveError ? <p className="error" role="alert">Save failed: {saveError}</p> : null}
            </form>

            <aside className="annotation-list" aria-label="Saved feedback annotations">
              <h4>Saved annotations</h4>
              {(feedback?.annotations || []).length ? feedback?.annotations.map((annotation) => (
                <article className={`annotation-card ${annotation.status}`} key={annotation.id}>
                  <div className="annotation-card-title"><strong>{annotation.status}</strong><span>{timestampLabel(annotation.start_ms)}–{timestampLabel(annotation.end_ms)}</span></div>
                  <small>{annotation.systems.map((system) => system.replace(/_/g, ' ')).join(', ') || 'No system selected'} · {annotation.severity.replace(/_/g, ' ')}</small>
                  <small>Responsible stages: {(annotation.source_stages || []).map((stage) => stage.replace(/_/g, ' ')).join(', ') || 'not attributed'}</small>
                  {annotation.notes ? <p>{annotation.notes}</p> : null}
                  <small>{annotation.keyframes.length} keyframes · {annotation.corrections.length} point corrections</small>
                  <div className="annotation-card-actions"><button type="button" className="secondary" onClick={() => editAnnotation(annotation)}>Edit</button><button type="button" className="danger" disabled={savingFeedback} onClick={() => void deleteAnnotation(annotation.id)}>Delete</button></div>
                </article>
              )) : <p className="muted">No saved annotations. Create one from the current frame or a scrubbed interval.</p>}
            </aside>
          </div>
        </section>

        {viewMode === 'diagnostics' ? <section className="diagnostics-grid">
          <JsonPanel title="Pin fusion and source decisions" value={pinSnapshot?.payload.tracking_assistance} />
          <JsonPanel title="Pose repair and occlusion decisions" value={repairSnapshot?.payload.pose_repair} />
          <JsonPanel title="Barbell and lift-specific diagnostics" value={barbellSnapshot?.payload.diagnostics} />
        </section> : null}
      </section>
    </main>
  );
}
