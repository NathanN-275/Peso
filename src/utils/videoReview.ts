import {
  BarbellPathPoint,
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
  trackingState?: VideoPoseKeypoint['trackingState'];
};

export type SquatOverlayPoint = VideoPoseKeypoint & {
  label: string;
};

// Landmarks used by the review overlay and squat-specific summaries.
export const SQUAT_LANDMARK_NAMES = [
  'left_upper_back',
  'right_upper_back',
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
const ESTIMATED_CONFIDENCE_THRESHOLD = 0.15;
const MAX_BARBELL_POINT_GAP_SECONDS = 0.5;
const SQUAT_LABELS: Record<SquatLandmarkName, string> = {
  left_upper_back: 'Upper Back',
  right_upper_back: 'Upper Back',
  left_shoulder: 'Upper Back',
  right_shoulder: 'Upper Back',
  left_hip: 'Hip',
  right_hip: 'Hip',
  left_knee: 'Knee',
  right_knee: 'Knee',
  left_ankle: 'Ankle',
  right_ankle: 'Ankle',
};

export function findClosestPoseFrame(frames: VideoPoseFrame[] | undefined, currentTime: number) {
  // Binary search keeps pose lookup fast while the clip plays.
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

export function findInterpolatedPoseFrame(frames: VideoPoseFrame[] | undefined, currentTime: number) {
  // Interpolate between sampled backend pose frames so fast reps do not snap frame-to-frame.
  if (!frames?.length) {
    return null;
  }

  if (frames.length === 1 || currentTime <= frames[0].time) {
    return frames[0];
  }

  const lastFrame = frames[frames.length - 1];

  if (currentTime >= lastFrame.time) {
    return lastFrame;
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

  const nextFrame = frames[low];
  const previousFrame = frames[low - 1];

  if (!previousFrame) {
    return nextFrame;
  }

  const frameGap = nextFrame.time - previousFrame.time;

  if (frameGap <= 0 || frameGap > 0.5) {
    return Math.abs(previousFrame.time - currentTime) <= Math.abs(nextFrame.time - currentTime)
      ? previousFrame
      : nextFrame;
  }

  const progress = Math.min(Math.max((currentTime - previousFrame.time) / frameGap, 0), 1);
  const previousKeypoints = new Map(previousFrame.keypoints.map((keypoint) => [keypoint.name, keypoint]));
  const nextKeypoints = new Map(nextFrame.keypoints.map((keypoint) => [keypoint.name, keypoint]));
  const names = new Set([...previousKeypoints.keys(), ...nextKeypoints.keys()]);

  return {
    time: currentTime,
    keypoints: [...names].map((name) => {
      const previous = previousKeypoints.get(name);
      const next = nextKeypoints.get(name);

      if (!previous) {
        return next as VideoPoseKeypoint;
      }
      if (!next) {
        return previous;
      }

      return {
        name,
        x: previous.x + ((next.x - previous.x) * progress),
        y: previous.y + ((next.y - previous.y) * progress),
        confidence: Math.min(previous.confidence, next.confidence),
        trackingState: previous.trackingState === next.trackingState
          ? previous.trackingState
          : previous.userPinned || next.userPinned
            ? 'estimated'
            : undefined,
        manualSource: previous.manualSource === next.manualSource
          ? previous.manualSource
          : previous.manualSource ?? next.manualSource,
        acceptedSource: previous.acceptedSource === next.acceptedSource
          ? previous.acceptedSource
          : previous.acceptedSource ?? next.acceptedSource,
        userPinned: previous.userPinned || next.userPinned,
        visualFallback: previous.visualFallback && next.visualFallback
          ? {
            x: previous.visualFallback.x + ((next.visualFallback.x - previous.visualFallback.x) * progress),
            y: previous.visualFallback.y + ((next.visualFallback.y - previous.visualFallback.y) * progress),
            confidence: Math.min(previous.visualFallback.confidence, next.visualFallback.confidence),
            manualSource: previous.visualFallback.manualSource === next.visualFallback.manualSource
              ? previous.visualFallback.manualSource
              : previous.visualFallback.manualSource ?? next.visualFallback.manualSource,
            reason: previous.visualFallback.reason === next.visualFallback.reason
              ? previous.visualFallback.reason
              : previous.visualFallback.reason ?? next.visualFallback.reason,
          }
          : previous.visualFallback ?? next.visualFallback,
      };
    }),
  };
}

export function findInterpolatedBarbellPathPoint(
  points: BarbellPathPoint[] | undefined,
  currentTime: number
) {
  if (!points?.length) {
    return null;
  }

  if (currentTime < points[0].time) {
    return null;
  }

  if (points.length === 1) {
    return points[0];
  }

  if (currentTime === points[0].time) {
    return points[0];
  }

  const lastPoint = points[points.length - 1];

  if (currentTime >= lastPoint.time) {
    return currentTime - lastPoint.time <= MAX_BARBELL_POINT_GAP_SECONDS ? lastPoint : null;
  }

  let low = 0;
  let high = points.length - 1;

  while (low < high) {
    const mid = Math.floor((low + high) / 2);

    if (points[mid].time < currentTime) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }

  const nextPoint = points[low];
  const previousPoint = points[low - 1];

  if (!previousPoint) {
    return nextPoint;
  }

  const pointGap = nextPoint.time - previousPoint.time;

  if (pointGap <= 0 || pointGap > MAX_BARBELL_POINT_GAP_SECONDS) {
    return null;
  }

  const progress = Math.min(Math.max((currentTime - previousPoint.time) / pointGap, 0), 1);

  return {
    time: currentTime,
    x: previousPoint.x + ((nextPoint.x - previousPoint.x) * progress),
    y: previousPoint.y + ((nextPoint.y - previousPoint.y) * progress),
    confidence: Math.min(previousPoint.confidence, nextPoint.confidence),
    trackingState: previousPoint.trackingState === nextPoint.trackingState
      ? previousPoint.trackingState
      : 'estimated',
  };
}

export function filterSquatKeypoints(
  frame: VideoPoseFrame | null,
  confidenceThreshold = CONFIDENCE_THRESHOLD
) {
  // Keep only the landmarks that matter for squat review.
  if (!frame) {
    return [];
  }

  return frame.keypoints.flatMap((keypoint) => {
    if (!SQUAT_LANDMARK_SET.has(keypoint.name)) {
      return [];
    }

    if (keypoint.confidence >= confidenceThreshold) {
      return [keypoint];
    }

    const fallback = keypoint.visualFallback;
    if (fallback) {
      return [{
        ...keypoint,
        x: fallback.x,
        y: fallback.y,
        confidence: fallback.confidence,
        trackingState: 'estimated' as const,
        manualSource: fallback.manualSource ?? 'pin_visual_fallback',
        userPinned: true,
      }];
    }

    return keypoint.userPinned === true || keypoint.manualSource === 'pin_estimated'
      ? [keypoint]
      : [];
  });
}

function getAverageConfidence(keypoints: VideoPoseKeypoint[], side: 'left' | 'right') {
  // Compare the tracked left and right body sides.
  const sideKeypoints = keypoints.filter((keypoint) => keypoint.name.startsWith(`${side}_`));

  if (!sideKeypoints.length) {
    return 0;
  }

  return sideKeypoints.reduce((total, keypoint) => total + keypoint.confidence, 0) / sideKeypoints.length;
}

function findKeypoint(keypoints: VideoPoseKeypoint[], name: SquatLandmarkName) {
  // Convenience lookup for one named landmark.
  return keypoints.find((keypoint) => keypoint.name === name) ?? null;
}

function isSquatLandmarkName(name: string): name is SquatLandmarkName {
  return SQUAT_LANDMARK_SET.has(name);
}

export function shouldPreferSingleSideForSquat(keypoints: VideoPoseKeypoint[], cameraView?: string) {
  // Side-view clips sometimes track only the visible side well.
  if (cameraView?.toLowerCase() !== 'side') {
    return false;
  }

  const leftHip = findKeypoint(keypoints, 'left_hip');
  const rightHip = findKeypoint(keypoints, 'right_hip');
  const leftShoulder = findKeypoint(keypoints, 'left_upper_back') ?? findKeypoint(keypoints, 'left_shoulder');
  const rightShoulder = findKeypoint(keypoints, 'right_upper_back') ?? findKeypoint(keypoints, 'right_shoulder');

  if (!leftHip || !rightHip || !leftShoulder || !rightShoulder) {
    return false;
  }

  const hipOverlap = Math.abs(leftHip.x - rightHip.x) < 0.08;
  const shoulderOverlap = Math.abs(leftShoulder.x - rightShoulder.x) < 0.1;

  return hipOverlap || shoulderOverlap;
}

export function selectVisibleSquatSide(keypoints: VideoPoseKeypoint[]) {
  // Use the side with the stronger keypoint confidence.
  return getAverageConfidence(keypoints, 'left') >= getAverageConfidence(keypoints, 'right')
    ? 'left'
    : 'right';
}

export function getSquatPoseConnections(
  keypoints: VideoPoseKeypoint[],
  cameraView?: string,
  lockedSide?: string | null,
  preferUpperBackKeypoint = false
) {
  const torsoStart = (side: 'left' | 'right') => {
    const upperBackName = `${side}_upper_back`;
    if (keypoints.some((keypoint) => keypoint.name === upperBackName)) {
      return upperBackName;
    }
    return preferUpperBackKeypoint ? null : `${side}_shoulder`;
  };

  // Render either the full body or a single visible side.
  if (cameraView?.toLowerCase() !== 'side') {
    const leftTorso = torsoStart('left');
    const rightTorso = torsoStart('right');
    return [
      ...(leftTorso ? [[leftTorso, 'left_hip']] : []),
      ['left_hip', 'left_knee'],
      ['left_knee', 'left_ankle'],
      ...(rightTorso ? [[rightTorso, 'right_hip']] : []),
      ['right_hip', 'right_knee'],
      ['right_knee', 'right_ankle'],
      ['left_hip', 'right_hip'],
      ...(leftTorso && rightTorso ? [[leftTorso, rightTorso]] : []),
    ] as Array<[string, string]>;
  }

  const side = lockedSide === 'left' || lockedSide === 'right'
    ? lockedSide
    : selectVisibleSquatSide(keypoints);

  const sideTorso = torsoStart(side);

  return [
    ...(sideTorso ? [[sideTorso, `${side}_hip`]] : []),
    [`${side}_hip`, `${side}_knee`],
    [`${side}_knee`, `${side}_ankle`],
  ] as Array<[string, string]>;
}

export function getSquatOverlayKeypoints(
  frame: VideoPoseFrame | null,
  cameraView?: string,
  confidenceThreshold = CONFIDENCE_THRESHOLD,
  lockedSide?: string | null,
  preferUpperBackKeypoint = false
): SquatOverlayPoint[] {
  const keypoints = filterSquatKeypoints(
    frame,
    Math.min(confidenceThreshold, ESTIMATED_CONFIDENCE_THRESHOLD)
  );
  const normalizedLockedSide = lockedSide === 'left' || lockedSide === 'right' ? lockedSide : null;
  const selectedSide = normalizedLockedSide ?? (cameraView?.toLowerCase() === 'side'
    ? selectVisibleSquatSide(keypoints)
    : null);
  const upperBackSides = new Set(
    keypoints
      .filter((keypoint) => keypoint.name === 'left_upper_back' || keypoint.name === 'right_upper_back')
      .map((keypoint) => keypoint.name.split('_')[0])
  );

  return keypoints
    .filter((keypoint) => {
      if (!isSquatLandmarkName(keypoint.name)) {
        return false;
      }

      if (selectedSide && !keypoint.name.startsWith(`${selectedSide}_`)) {
        return false;
      }

      const side = keypoint.name.startsWith('left_') ? 'left' : 'right';
      if (
        keypoint.name === `${side}_shoulder`
        && (upperBackSides.has(side) || (preferUpperBackKeypoint && selectedSide === side))
      ) {
        return false;
      }

      return true;
    })
    .map((keypoint) => ({
      ...keypoint,
      label: SQUAT_LABELS[keypoint.name as SquatLandmarkName],
    }));
}

export function calculateVideoRect(container: Size, source: Size, contentFit: ContentFit = 'contain') {
  // Compute the on-screen video rectangle for pose projection.
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
  // Convert normalized pose coordinates into screen pixels.
  const rect = calculateVideoRect(container, source, contentFit);

  return {
    name: keypoint.name,
    x: rect.x + (keypoint.x * rect.width),
    y: rect.y + (keypoint.y * rect.height),
    confidence: keypoint.confidence,
    trackingState: keypoint.trackingState,
  };
}

export function normalizeResultFlags(result: VideoAnalysisResult) {
  // Accept either camelCase or snake_case result payloads.
  return result.summaryFlags ?? result.summary_flags ?? [];
}

export function normalizeCoachingFeedback(result: VideoAnalysisResult) {
  // Accept either backend field name for coaching text.
  return result.coachingFeedback ?? result.coach_feedback ?? [];
}

export function normalizeVideoQuality(result: VideoAnalysisResult) {
  // Merge the current response shape with older diagnostics fields.
  const diagnostics: VideoAnalysisDiagnostics | undefined = result.diagnostics;

  return {
    overallQuality: result.videoQuality?.overallQuality ?? diagnostics?.quality_score,
    poseCoverage: result.videoQuality?.poseCoverage ?? diagnostics?.pose_coverage,
    lowerBodyVisibility: result.videoQuality?.lowerBodyVisibility ?? diagnostics?.lower_body_visibility,
    sideViewConfidence: result.videoQuality?.sideViewConfidence ?? diagnostics?.side_view_score,
    squatMotionSignal:
      result.videoQuality?.squatMotionSignal ?? diagnostics?.rep_detection?.motion_amplitude,
    landmarkJitter: result.videoQuality?.landmarkJitter ?? diagnostics?.landmark_jitter,
    poseValidationReliability:
      result.videoQuality?.poseValidationReliability
      ?? (
        typeof diagnostics?.pose_validation?.quality_score_penalty === 'number'
          ? 1 - diagnostics.pose_validation.quality_score_penalty
          : undefined
      ),
  };
}

export function getRepDuration(rep: VideoAnalysisRep) {
  // Prefer the explicit duration, then derive it from timestamps.
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
  // Faster reps have a higher inverse-duration score.
  if (typeof rep.repSpeed === 'number') {
    return rep.repSpeed;
  }

  const duration = getRepDuration(rep);
  return duration > 0 ? 1 / duration : 0;
}

export function getRepVelocity(rep: VideoAnalysisRep) {
  // Surface the average and peak velocity in one helper.
  return {
    avgVelocity: rep.avgVelocity ?? rep.estimated_body_velocity?.avg_velocity ?? 0,
    peakVelocity: rep.peakVelocity ?? rep.estimated_body_velocity?.peak_velocity ?? 0,
  };
}

export function formatSeconds(value: number) {
  // Keep playback timestamps compact.
  if (!Number.isFinite(value)) {
    return '0:00';
  }

  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

export function formatPercent(value?: number | null) {
  // Round quality values for display.
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'n/a';
  }

  return `${Math.round(value * 100)}%`;
}

export function clampTimeToDuration(time: number, duration: number) {
  // Prevent scrubber values from leaving the clip range.
  if (!Number.isFinite(time) || !Number.isFinite(duration) || duration <= 0) {
    return Math.max(time || 0, 0);
  }

  return Math.min(Math.max(time, 0), duration);
}

export function getTimeFromTrackX(x: number, trackWidth: number, duration: number) {
  // Translate a scrubber x-coordinate into a playback time.
  if (trackWidth <= 0 || duration <= 0) {
    return 0;
  }

  const progress = Math.min(Math.max(x / trackWidth, 0), 1);
  return progress * duration;
}
