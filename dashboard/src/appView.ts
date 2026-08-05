export type AppViewPoint = {
  x?: number;
  y?: number;
  visibility?: number;
  confidence?: number;
  accepted_source?: string;
  tracking_state?: string;
  manual_source?: string;
  chain_failure_reason?: string;
};

export type AppViewFrame = {
  landmarks?: Record<string, AppViewPoint>;
};

export type AppViewKeypoint = Required<Pick<AppViewPoint, 'x' | 'y'>> & {
  name: string;
  label: string;
  confidence: number;
  estimated: boolean;
  visualOnly: boolean;
};

export type AnnotationTarget = {
  key: string;
  label: string;
};

export type AppViewBarbellPoint = {
  x: number;
  y: number;
  time: number;
  tracking_state?: string;
  selected_source?: string;
  coasting_frame?: boolean;
  stationary_hardware_rejected?: boolean;
  hardware_rejected?: boolean;
  gap_reason?: string;
};

const SQUAT_LABELS: Record<string, string> = {
  left_upper_back: 'Upper back', right_upper_back: 'Upper back',
  left_shoulder: 'Upper back', right_shoulder: 'Upper back',
  left_hip: 'Hip', right_hip: 'Hip', left_knee: 'Knee', right_knee: 'Knee',
  left_ankle: 'Ankle', right_ankle: 'Ankle',
};

const PRESSING_LABELS: Record<string, string> = {
  left_shoulder: 'Shoulder', right_shoulder: 'Shoulder', left_elbow: 'Elbow',
  right_elbow: 'Elbow', left_wrist: 'Wrist', right_wrist: 'Wrist',
  left_hip: 'Hip', right_hip: 'Hip',
};

const SQUAT_NAMES = new Set(Object.keys(SQUAT_LABELS));
const PRESSING_NAMES = new Set(Object.keys(PRESSING_LABELS));
const MIN_CONFIDENCE = 0.15;

function confidenceFor(point: AppViewPoint) {
  return point.visibility ?? point.confidence ?? 1;
}

function isPressingExercise(exercise?: string | null) {
  const normalized = exercise?.trim().toLowerCase();
  return normalized === 'bench press' || normalized === 'incline bench press' || normalized === 'overhead press';
}

function selectedSide(points: Array<{ name: string; confidence: number }>) {
  const average = (side: 'left' | 'right') => {
    const sidePoints = points.filter((point) => point.name.startsWith(`${side}_`));
    return sidePoints.length ? sidePoints.reduce((total, point) => total + point.confidence, 0) / sidePoints.length : 0;
  };
  return average('left') >= average('right') ? 'left' : 'right';
}

export function appViewKeypoints(frame: AppViewFrame | null, exercise?: string | null, cameraView?: string): AppViewKeypoint[] {
  const source = Object.entries(frame?.landmarks || {}).flatMap(([name, point]) => {
    if (typeof point.x !== 'number' || typeof point.y !== 'number') {
      return [];
    }
    const confidence = confidenceFor(point);
    const pinned = point.manual_source === 'pin_estimated';
    if (confidence < MIN_CONFIDENCE && !pinned) {
      return [];
    }
    return [{ name, ...point, confidence }];
  });
  const pressing = isPressingExercise(exercise);
  const allowed = pressing ? PRESSING_NAMES : SQUAT_NAMES;
  const candidates = source.filter((point) => allowed.has(point.name));
  const side = cameraView?.toLowerCase() === 'side' ? selectedSide(candidates) : null;
  const upperBackSides = new Set(candidates.filter((point) => point.name.endsWith('_upper_back')).map((point) => point.name.split('_')[0]));

  return candidates.filter((point) => {
    if (side && !point.name.startsWith(`${side}_`)) {
      return false;
    }
    const pointSide = point.name.split('_')[0];
    return pressing || point.name !== `${pointSide}_shoulder` || !upperBackSides.has(pointSide);
  }).map((point) => ({
    name: point.name,
    label: (pressing ? PRESSING_LABELS : SQUAT_LABELS)[point.name],
    x: point.x as number,
    y: point.y as number,
    confidence: point.confidence,
    estimated: point.confidence < 0.5 || point.tracking_state === 'automatic' || point.tracking_state === 'estimated',
    visualOnly: Boolean(point.chain_failure_reason),
  }));
}

export function appViewConnections(points: AppViewKeypoint[], exercise?: string | null, cameraView?: string): Array<[string, string]> {
  const names = new Set(points.map((point) => point.name));
  const pressing = isPressingExercise(exercise);
  const side = cameraView?.toLowerCase() === 'side' ? selectedSide(points) : null;
  const pairs: Array<[string, string]> = pressing
    ? side ? [[`${side}_shoulder`, `${side}_elbow`], [`${side}_elbow`, `${side}_wrist`], [`${side}_shoulder`, `${side}_hip`]]
      : [['left_wrist', 'left_elbow'], ['left_elbow', 'left_shoulder'], ['right_wrist', 'right_elbow'], ['right_elbow', 'right_shoulder'], ['left_shoulder', 'right_shoulder'], ['left_shoulder', 'left_hip'], ['right_shoulder', 'right_hip'], ['left_hip', 'right_hip']]
    : side ? [[`${side}_upper_back`, `${side}_hip`], [`${side}_shoulder`, `${side}_hip`], [`${side}_hip`, `${side}_knee`], [`${side}_knee`, `${side}_ankle`]]
      : [['left_upper_back', 'left_hip'], ['left_shoulder', 'left_hip'], ['left_hip', 'left_knee'], ['left_knee', 'left_ankle'], ['right_upper_back', 'right_hip'], ['right_shoulder', 'right_hip'], ['right_hip', 'right_knee'], ['right_knee', 'right_ankle'], ['left_hip', 'right_hip']];
  return pairs.filter(([from, to]) => names.has(from) && names.has(to));
}

export function sideSquatAnnotationTargets(frame: AppViewFrame | null): AnnotationTarget[] {
  const points = appViewKeypoints(frame, 'back_squat', 'side');
  const source = frame?.landmarks || {};
  const visibleSide = points.find((point) => point.name.startsWith('left_') || point.name.startsWith('right_'))?.name.split('_')[0];
  const targetFor = (label: string, fallback: string) => {
    const point = points.find((candidate) => candidate.label === label);
    if (point) {
      return { key: point.name, label };
    }
    if (visibleSide) {
      const suffix = label === 'Upper back' ? ['upper_back', 'shoulder'] : [label.toLowerCase()];
      const persistedKey = suffix.map((name) => `${visibleSide}_${name}`).find((name) => name in source);
      return { key: persistedKey || `${visibleSide}_${suffix[0]}`, label };
    }
    return { key: fallback, label };
  };

  return [
    targetFor('Upper back', 'upper_back'),
    targetFor('Hip', 'hip'),
    targetFor('Knee', 'knee'),
    targetFor('Ankle', 'ankle'),
    { key: 'barbell_center', label: 'Barbell center' },
  ];
}

export function mapPointToCoverStage(point: { x: number; y: number }, sourceAspectRatio: number, stageAspectRatio = 9 / 16) {
  if (!Number.isFinite(sourceAspectRatio) || sourceAspectRatio <= 0) {
    return point;
  }
  if (sourceAspectRatio > stageAspectRatio) {
    const width = sourceAspectRatio / stageAspectRatio;
    return { x: ((1 - width) / 2) + (point.x * width), y: point.y };
  }
  const height = stageAspectRatio / sourceAspectRatio;
  return { x: point.x, y: ((1 - height) / 2) + (point.y * height) };
}

export function visibleBarbellPoints(points: AppViewBarbellPoint[], currentTime: number) {
  return points.filter((point) => point.time <= currentTime && !point.coasting_frame && !point.stationary_hardware_rejected && !point.hardware_rejected && !point.gap_reason && point.selected_source !== 'gap');
}
