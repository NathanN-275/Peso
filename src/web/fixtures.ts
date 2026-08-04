export type PrototypeScenario =
  | 'empty'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'quota'
  | 'expired';

export type SavedLiftFixture = {
  id: string;
  exercise: 'Squat' | 'Bench press' | 'Deadlift';
  date: string;
  load: string;
  performedReps: number;
  detectedReps: number;
  cameraView: string;
  status: string;
  cue: string;
  webEligible: boolean;
};

export const prototypeScenarios: Array<{
  value: PrototypeScenario;
  label: string;
}> = [
  { value: 'empty', label: 'Empty' },
  { value: 'queued', label: 'Queued' },
  { value: 'processing', label: 'Processing' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'quota', label: 'Quota used' },
  { value: 'expired', label: 'Expired' },
];

export const savedLifts: SavedLiftFixture[] = [
  {
    id: 'lift-225',
    exercise: 'Squat',
    date: 'Today, 8:42 AM',
    load: '225 lb',
    performedReps: 3,
    detectedReps: 3,
    cameraView: 'Side view',
    status: '3 coaching cues',
    cue: 'Depth stayed consistent across all three reps.',
    webEligible: true,
  },
  {
    id: 'lift-215',
    exercise: 'Squat',
    date: 'August 1',
    load: '215 lb',
    performedReps: 5,
    detectedReps: 5,
    cameraView: 'Side view',
    status: '2 coaching cues',
    cue: 'The bar remained over mid-foot through the middle reps.',
    webEligible: true,
  },
  {
    id: 'lift-bench-165',
    exercise: 'Bench press',
    date: 'July 28',
    load: '165 lb',
    performedReps: 6,
    detectedReps: 6,
    cameraView: 'Three-quarter view',
    status: 'Saved on mobile',
    cue: 'This existing lift remains available on web as read-only history.',
    webEligible: false,
  },
  {
    id: 'lift-deadlift-315',
    exercise: 'Deadlift',
    date: 'July 24',
    load: '315 lb',
    performedReps: 4,
    detectedReps: 4,
    cameraView: 'Side view',
    status: 'Saved on mobile',
    cue: 'This existing lift remains available on web as read-only history.',
    webEligible: false,
  },
];

export const activityCopy: Record<
  PrototypeScenario,
  { title: string; detail: string; tone: 'neutral' | 'info' | 'success' | 'danger' | 'warning' }
> = {
  empty: {
    title: 'No active analysis',
    detail: 'Record or upload a side-view squat to start your first web analysis.',
    tone: 'neutral',
  },
  queued: {
    title: 'Squat set is queued',
    detail: 'Position 1 of 2 · You can cancel until processing begins.',
    tone: 'info',
  },
  processing: {
    title: 'Analyzing your squat',
    detail: 'Tracking movement and bar position · About 35 seconds remaining.',
    tone: 'info',
  },
  completed: {
    title: 'Analysis ready to review',
    detail: 'Your result is ready. Save or discard it within 24 hours.',
    tone: 'success',
  },
  failed: {
    title: 'Analysis could not finish',
    detail: 'Peso hit a system problem. This attempt did not use a slot.',
    tone: 'danger',
  },
  quota: {
    title: 'Daily capacity used',
    detail: 'All 3 rolling slots are in use. The next slot opens today at 6:18 PM.',
    tone: 'warning',
  },
  expired: {
    title: 'Unsaved result expired',
    detail: 'Completed results are available for 24 hours. This upload was removed.',
    tone: 'warning',
  },
};
