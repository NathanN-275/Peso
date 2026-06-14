export function withOptionalTrackingSetup<
  TPayload extends Record<string, unknown>,
  TTrackingSetup,
>(
  payload: TPayload,
  trackingSetup: TTrackingSetup | null | undefined
): TPayload | (TPayload & { tracking_setup: TTrackingSetup });
