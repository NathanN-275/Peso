import { TRACKING_PIN_NAMES, type TrackingPinName } from '../types/trackingSetup';

export const EXERCISE_OPTIONS = [
  'Squat',
  'Front Squat',
  'Zercher Squat',
  'Box Squat',
  'Goblet Squat',
  'Bench Press',
  'Incline Bench Press',
  'Deadlift',
  'Romanian Deadlift',
  'Overhead Press',
  'Barbell Row',
] as const;

// The upload flow asks for both the lift and the camera angle.
export const ANGLE_OPTIONS = ['Side', 'Front'] as const;

export type ExerciseOption = (typeof EXERCISE_OPTIONS)[number];
export type CameraAngle = (typeof ANGLE_OPTIONS)[number];

export type VideoSetupSelection = {
  exercise: ExerciseOption;
  angle: CameraAngle;
};

const PRESSING_EXERCISES: ReadonlySet<ExerciseOption> = new Set([
  'Bench Press',
  'Incline Bench Press',
  'Overhead Press',
]);
const PRESSING_PIN_NAMES: readonly TrackingPinName[] = ['wrist', 'elbow'];

export function supportsPinAssistedTracking(selection: VideoSetupSelection | null) {
  return Boolean(
    (selection?.angle === 'Side' && selection.exercise.endsWith('Squat'))
    || (selection && PRESSING_EXERCISES.has(selection.exercise))
  );
}

export function trackingPinNames(selection: VideoSetupSelection | null): readonly TrackingPinName[] {
  if (selection && PRESSING_EXERCISES.has(selection.exercise)) {
    return PRESSING_PIN_NAMES;
  }

  return TRACKING_PIN_NAMES;
}

export function trackingBarbellTarget(selection: VideoSetupSelection | null) {
  return selection?.angle === 'Front' ? ('bar_center' as const) : ('near_side_collar' as const);
}
