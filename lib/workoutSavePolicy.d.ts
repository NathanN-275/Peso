export type LoadUnit = 'lb' | 'kg';

export type WorkoutSaveDetails = {
  performed_reps: number | null;
  load_value: number | null;
  load_unit: LoadUnit | null;
  user_notes?: string | null;
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
