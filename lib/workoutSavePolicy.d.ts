export type LoadUnit = 'lb' | 'kg';

export type WorkoutSaveDetails = {
  performed_reps: number;
  load_value: number;
  load_unit: LoadUnit;
};

export type WorkoutSaveParseResult =
  | { ok: true; value: WorkoutSaveDetails }
  | { ok: false; error: string };

export function parseWorkoutSaveDetails(
  repsText: string,
  loadText: string,
  loadUnit: LoadUnit
): WorkoutSaveParseResult;

export function resolveStoredLoadUnit(value: string | null | undefined): LoadUnit;
