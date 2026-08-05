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
