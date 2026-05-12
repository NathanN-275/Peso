import {
  VideoAnalysisDiagnostics,
  VideoAnalysisRep,
  VideoAnalysisResult,
  VideoPoseFrame,
  VideoPoseKeypoint,
} from '../types/videoAnalysis';

export type ContentFit = 'contain' | 'cover';

export type Size = {
  width: number;
  height: number;
};

export type MappedPoint = {
  name: string;
  x: number;
  y: number;
  confidence: number;
};

export const SQUAT_LANDMARK_NAMES = [
  'left_shoulder',
  'right_shoulder',
  'left_hip',
  'right_hip',
  'left_knee',
  'right_knee',
  'left_ankle',
  'right_ankle',
] as const;

export const SQUAT_BODY_CONNECTIONS = [
  ['left_shoulder', 'left_hip'],
  ['left_hip', 'left_knee'],
  ['left_knee', 'left_ankle'],
  ['right_shoulder', 'right_hip'],
  ['right_hip', 'right_knee'],
  ['right_knee', 'right_ankle'],
  ['left_hip', 'right_hip'],
  ['left_shoulder', 'right_shoulder'],
] as const;

export type SquatLandmarkName = (typeof SQUAT_LANDMARK_NAMES)[number];

const SQUAT_LANDMARK_SET = new Set<string>(SQUAT_LANDMARK_NAMES);
const CONFIDENCE_THRESHOLD = 0.35;

export function findClosestPoseFrame(frames: VideoPoseFrame[] | undefined, currentTime: number) {
  if (!frames?.length) {
    return null;
  }

  let low = 0;
  let high = frames.length - 1;

  while (low < high) {
    const mid = Math.floor((low + high) / 2);

    if (frames[mid].time < currentTime) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }

  const current = frames[low];
  const previous = frames[low - 1];

  if (!previous) {
    return current;
  }

  return Math.abs(previous.time - currentTime) <= Math.abs(current.time - currentTime)
    ? previous
    : current;
}

export function filterSquatKeypoints(frame: VideoPoseFrame | null, confidenceThreshold = CONFIDENCE_THRESHOLD) {
  if (!frame) {
    return [];
  }

  return frame.keypoints.filter(
    (keypoint) => SQUAT_LANDMARK_SET.has(keypoint.name) && keypoint.confidence >= confidenceThreshold
  );
}

function getAverageConfidence(keypoints: VideoPoseKeypoint[], side: 'left' | 'right') {
  const sideKeypoints = keypoints.filter((keypoint) => keypoint.name.startsWith(`${side}_`));

  if (!sideKeypoints.length) {
    return 0;
  }

  return sideKeypoints.reduce((total, keypoint) => total + keypoint.confidence, 0) / sideKeypoints.length;
}

function findKeypoint(keypoints: VideoPoseKeypoint[], name: SquatLandmarkName) {
  return keypoints.find((keypoint) => keypoint.name === name) ?? null;
}

export function shouldPreferSingleSideForSquat(keypoints: VideoPoseKeypoint[], cameraView?: string) {
  if (cameraView?.toLowerCase() !== 'side') {
    return false;
  }

  const leftHip = findKeypoint(keypoints, 'left_hip');
  const rightHip = findKeypoint(keypoints, 'right_hip');
  const leftShoulder = findKeypoint(keypoints, 'left_shoulder');
  const rightShoulder = findKeypoint(keypoints, 'right_shoulder');

  if (!leftHip || !rightHip || !leftShoulder || !rightShoulder) {
    return false;
  }

  const hipOverlap = Math.abs(leftHip.x - rightHip.x) < 0.08;
  const shoulderOverlap = Math.abs(leftShoulder.x - rightShoulder.x) < 0.1;

  return hipOverlap || shoulderOverlap;
}

export function selectVisibleSquatSide(keypoints: VideoPoseKeypoint[]) {
  return getAverageConfidence(keypoints, 'left') >= getAverageConfidence(keypoints, 'right')
    ? 'left'
    : 'right';
}

export function getSquatPoseConnections(keypoints: VideoPoseKeypoint[], cameraView?: string) {
  if (!shouldPreferSingleSideForSquat(keypoints, cameraView)) {
    return SQUAT_BODY_CONNECTIONS;
  }

  const side = selectVisibleSquatSide(keypoints);

  return [
    [`${side}_shoulder`, `${side}_hip`],
    [`${side}_hip`, `${side}_knee`],
    [`${side}_knee`, `${side}_ankle`],
  ] as const;
}

export function calculateVideoRect(container: Size, source: Size, contentFit: ContentFit = 'contain') {
  if (container.width <= 0 || container.height <= 0 || source.width <= 0 || source.height <= 0) {
    return {
      x: 0,
      y: 0,
      width: container.width,
      height: container.height,
    };
  }

  const containerRatio = container.width / container.height;
  const sourceRatio = source.width / source.height;
  const fitByWidth = contentFit === 'contain'
    ? sourceRatio >= containerRatio
    : sourceRatio < containerRatio;
  const width = fitByWidth ? container.width : container.height * sourceRatio;
  const height = fitByWidth ? container.width / sourceRatio : container.height;

  return {
    x: (container.width - width) / 2,
    y: (container.height - height) / 2,
    width,
    height,
  };
}

export function mapNormalizedKeypoint(
  keypoint: VideoPoseKeypoint,
  container: Size,
  source: Size,
  contentFit: ContentFit = 'contain'
): MappedPoint {
  const rect = calculateVideoRect(container, source, contentFit);

  return {
    name: keypoint.name,
    x: rect.x + (keypoint.x * rect.width),
    y: rect.y + (keypoint.y * rect.height),
    confidence: keypoint.confidence,
  };
}

export function normalizeResultFlags(result: VideoAnalysisResult) {
  return result.summaryFlags ?? result.summary_flags ?? [];
}

export function normalizeCoachingFeedback(result: VideoAnalysisResult) {
  return result.coachingFeedback ?? result.coach_feedback ?? [];
}

export function normalizeVideoQuality(result: VideoAnalysisResult) {
  const diagnostics: VideoAnalysisDiagnostics | undefined = result.diagnostics;

  return {
    overallQuality: result.videoQuality?.overallQuality ?? diagnostics?.quality_score,
    poseCoverage: result.videoQuality?.poseCoverage ?? diagnostics?.pose_coverage,
    lowerBodyVisibility: result.videoQuality?.lowerBodyVisibility ?? diagnostics?.lower_body_visibility,
    sideViewConfidence: result.videoQuality?.sideViewConfidence ?? diagnostics?.side_view_score,
    squatMotionSignal:
      result.videoQuality?.squatMotionSignal ?? diagnostics?.rep_detection?.motion_amplitude,
  };
}

export function getRepDuration(rep: VideoAnalysisRep) {
  if (typeof rep.duration === 'number') {
    return rep.duration;
  }

  if (typeof rep.startTime === 'number' && typeof rep.endTime === 'number') {
    return Math.max(rep.endTime - rep.startTime, 0);
  }

  if (rep.timestamps_ms) {
    return Math.max((rep.timestamps_ms.end - rep.timestamps_ms.start) / 1000, 0);
  }

  return 0;
}

export function getRepSpeed(rep: VideoAnalysisRep) {
  if (typeof rep.repSpeed === 'number') {
    return rep.repSpeed;
  }

  const duration = getRepDuration(rep);
  return duration > 0 ? 1 / duration : 0;
}

export function getRepVelocity(rep: VideoAnalysisRep) {
  return {
    avgVelocity: rep.avgVelocity ?? rep.estimated_body_velocity?.avg_velocity ?? 0,
    peakVelocity: rep.peakVelocity ?? rep.estimated_body_velocity?.peak_velocity ?? 0,
  };
}

export function formatSeconds(value: number) {
  if (!Number.isFinite(value)) {
    return '0:00';
  }

  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

export function formatPercent(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'n/a';
  }

  return `${Math.round(value * 100)}%`;
}

export function clampTimeToDuration(time: number, duration: number) {
  if (!Number.isFinite(time) || !Number.isFinite(duration) || duration <= 0) {
    return Math.max(time || 0, 0);
  }

  return Math.min(Math.max(time, 0), duration);
}

export function getTimeFromTrackX(x: number, trackWidth: number, duration: number) {
  if (trackWidth <= 0 || duration <= 0) {
    return 0;
  }

  const progress = Math.min(Math.max(x / trackWidth, 0), 1);
  return progress * duration;
}
