export type VideoCapabilities = {
  pin_assisted_tracking: boolean;
  tracking_setup_versions: number[];
  reason: string | null;
};

export const MISSING_MIGRATION_MESSAGE: string;

export function shouldCheckPinTrackingCapability(trackingSetup: unknown): boolean;

export function getPinTrackingCapabilityError(
  capabilities: VideoCapabilities | null | undefined,
  requestedVersion: number
): string | null;

export function verifyPinTrackingCapability(options: {
  trackingSetup: { version: number } | null | undefined;
  getAccessToken: () => Promise<string>;
  fetchCapabilities: (accessToken: string) => Promise<VideoCapabilities>;
}): Promise<string | null>;
