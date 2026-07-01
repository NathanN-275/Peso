export type LabelPoint = {
  id: string;
  x: number;
  y: number;
  labelWidth?: number;
  labelHeight?: number;
};

export type LaidOutLabelPoint = LabelPoint & {
  labelX: number;
  labelY: number;
  labelWidth: number;
  labelHeight: number;
  displaced: boolean;
};

export function intersectionArea(
  first: { x: number; y: number; width: number; height: number },
  second: { x: number; y: number; width: number; height: number }
): number;

export function layoutTrackingLabels(
  points: LabelPoint[],
  bounds: { width: number; height: number },
  options?: { labelWidth?: number; labelHeight?: number; gap?: number }
): LaidOutLabelPoint[];

export function isReferenceTrackingTime(
  currentTimeSeconds: number,
  referenceTimeMs: number,
  toleranceMs?: number
): boolean;

export function resolveSelectedTrackingSide(
  trackingAssistance?: { selectedSide?: 'left' | 'right' | null } | null,
  diagnostics?: {
    selected_side?: string | null;
    tracking_assistance?: { selectedSide?: 'left' | 'right' | null } | null;
    pose_validation?: { selected_side?: string | null } | null;
  } | null
): string | null;
