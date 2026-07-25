export function normalizePositiveDurationMs(value: unknown): number | null;

export function resolveVideoDurationMs(options: {
  playerDurationSeconds?: number | null;
  pickerDurationMs?: number | null;
}): number | null;

export function clampTrackingReferenceTimeMs(
  currentTimeSeconds: number,
  durationMs?: number | null
): number;
