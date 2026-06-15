export const TRACKING_PIN_NAMES = ['shoulder', 'hip', 'knee', 'ankle', 'barbell'] as const;

export type TrackingPinName = (typeof TRACKING_PIN_NAMES)[number];

export type NormalizedTrackingPoint = {
  x: number;
  y: number;
};

export type TrackingSetup = {
  version: 1;
  reference_time_ms: number;
  barbell_target: 'near_side_collar';
  anchors: Record<TrackingPinName, NormalizedTrackingPoint>;
};

export type TrackingReference = {
  version: 1;
  timeMs: number;
  selectedSide?: 'left' | 'right' | null;
  anchors: Record<TrackingPinName, NormalizedTrackingPoint>;
};

export type TrackingAssistance = {
  requestedMode: 'automatic' | 'pins';
  actualMode: 'automatic' | 'pin_assisted' | 'automatic_fallback';
  used: boolean;
  fallbackReason?: string | null;
  selectedSide?: 'left' | 'right' | null;
  fusedLandmarkCount?: number;
  directlyAnchoredLandmarkCount?: number;
  blendedLandmarkCount?: number;
  fallbackLandmarkCount?: number;
  rejectedTrackCount?: number;
  rejectionReasons?: Record<string, number>;
  coverage?: Partial<Record<TrackingPinName, number>>;
  barbellSeedUsed?: boolean;
  manualBarbellPointCount?: number;
  automaticBarbellPointCount?: number;
  reference?: TrackingReference | null;
};
