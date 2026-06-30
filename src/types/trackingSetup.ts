export const TRACKING_PIN_NAMES = ['shoulder', 'hip', 'knee', 'ankle', 'barbell'] as const;

export type TrackingPinName = (typeof TRACKING_PIN_NAMES)[number];
export type TrackingBodySource =
  | 'reference'
  | 'pin_guided'
  | 'pin_estimated'
  | 'kinematic_estimate'
  | 'pin_visual_fallback'
  | 'automatic'
  | 'automatic_recovery'
  | 'stale_pin_rejected'
  | 'stale_pin_stuck'
  | 'gap';
export type TrackingBodySourceName = 'upper_back' | 'hip' | 'knee' | 'ankle';
export type TrackingDiagnosticPinName = TrackingPinName | 'upper_back';
export type TrackingBarbellSource =
  | 'manual_pin_lane'
  | 'manual_pin_blend'
  | 'automatic_lane'
  | 'kinematic_coast'
  | 'detector_tracklet'
  | 'detector_pin_prior'
  | 'pending_lock'
  | 'coast'
  | 'gap';

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
  trackingCore?: 'legacy' | 'apache_v1' | string;
  used: boolean;
  fallbackReason?: string | null;
  selectedSide?: 'left' | 'right' | null;
  fusedLandmarkCount?: number;
  directlyAnchoredLandmarkCount?: number;
  blendedLandmarkCount?: number;
  fallbackLandmarkCount?: number;
  rejectedTrackCount?: number;
  rejectionReasons?: Record<string, number>;
  velocityCapCount?: number;
  velocityCapCounts?: Partial<Record<TrackingDiagnosticPinName, number>>;
  coverage?: Partial<Record<TrackingDiagnosticPinName, number>>;
  barbellSeedUsed?: boolean;
  manualBarbellPointCount?: number;
  automaticBarbellPointCount?: number;
  barbellCoastingPointCount?: number;
  barbellGapPointCount?: number;
  barbellSourceCounts?: Partial<Record<TrackingBarbellSource, number>>;
  upperBackAnchorKey?: 'shoulder' | 'upper_back';
  upperBackAnchorSemantics?: 'upper_back_anchor';
  upperBackAnchorUsedCount?: number;
  upperBackAnchorCoverage?: number;
  pinOwnedLandmarkCount?: number;
  modelDivergenceAcceptedCount?: number;
  bodyBarbellOccluderRejectionCount?: number;
  sourceCounts?: Partial<Record<TrackingBodySourceName, Partial<Record<TrackingBodySource, number>>>>;
  bodyPinFrames?: Array<Record<string, unknown>>;
  reference?: TrackingReference | null;
};
