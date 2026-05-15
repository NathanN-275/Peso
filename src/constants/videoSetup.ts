export const EXERCISE_OPTIONS = [
  'Squat',
  'Front Squat',
  'Bench Press',
  'Incline Bench Press',
  'Deadlift',
  'Romanian Deadlift',
  'Overhead Press',
  'Barbell Row',
] as const;

// The upload flow asks for both the lift and the camera angle.
export const ANGLE_OPTIONS = ['Side', 'Front', 'Angled'] as const;

export type ExerciseOption = (typeof EXERCISE_OPTIONS)[number];
export type CameraAngle = (typeof ANGLE_OPTIONS)[number];

export type VideoSetupSelection = {
  exercise: ExerciseOption;
  angle: CameraAngle;
};
