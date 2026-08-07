from __future__ import annotations

import logging
import math
import os
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


logger = logging.getLogger(__name__)

QUALITY_PREFLIGHT_MODEL_VERSION = "mediapipe-pose-full-hog-v1"
QUALITY_PREFLIGHT_THRESHOLD_VERSION = "side-squat-preflight-v1"

_REQUIRED_CHECKS = (
  "sideView",
  "bodyChain",
  "subjectScale",
  "motionBlur",
  "dominantLifter",
  "multiplePeople",
)


def _float_from_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
  raw_value = os.getenv(name, "").strip()
  if not raw_value:
    return default

  try:
    value = float(raw_value)
  except ValueError:
    logger.warning("Ignoring invalid %s=%r; using default %s.", name, raw_value, default)
    return default

  if value < minimum or value > maximum:
    logger.warning("Ignoring out-of-range %s=%r; using default %s.", name, raw_value, default)
    return default

  return value


def _int_from_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
  raw_value = os.getenv(name, "").strip()
  if not raw_value:
    return default

  try:
    value = int(raw_value)
  except ValueError:
    logger.warning("Ignoring invalid %s=%r; using default %s.", name, raw_value, default)
    return default

  if value < minimum or value > maximum:
    logger.warning("Ignoring out-of-range %s=%r; using default %s.", name, raw_value, default)
    return default

  return value


@dataclass(frozen=True)
class QualityPreflightThresholds:
  sample_count: int = 12
  max_frame_dimension: int = 512
  pose_visibility: float = 0.35
  side_view_block: float = 0.42
  side_view_warning: float = 0.58
  body_chain_block: float = 0.55
  body_chain_warning: float = 0.75
  subject_height_block: float = 0.28
  subject_height_warning: float = 0.38
  blur_variance_block: float = 30.0
  blur_variance_warning: float = 55.0
  comparable_person_area_ratio: float = 0.55
  ambiguous_people_block: float = 0.30
  ambiguous_people_warning: float = 0.15
  camera_shift_warning: float = 0.035
  lighting_mean_low: float = 45.0
  lighting_mean_high: float = 210.0
  lighting_contrast_low: float = 30.0

  @classmethod
  def from_env(cls) -> "QualityPreflightThresholds":
    return cls(
      sample_count=_int_from_env("SIDE_SQUAT_PREFLIGHT_SAMPLE_COUNT", 12, minimum=6, maximum=30),
      max_frame_dimension=_int_from_env(
        "SIDE_SQUAT_PREFLIGHT_MAX_FRAME_DIMENSION",
        512,
        minimum=256,
        maximum=1280,
      ),
      pose_visibility=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_POSE_VISIBILITY",
        0.35,
        minimum=0.0,
        maximum=1.0,
      ),
      side_view_block=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_SIDE_BLOCK",
        0.42,
        minimum=0.0,
        maximum=1.0,
      ),
      side_view_warning=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_SIDE_WARNING",
        0.58,
        minimum=0.0,
        maximum=1.0,
      ),
      body_chain_block=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_CHAIN_BLOCK",
        0.55,
        minimum=0.0,
        maximum=1.0,
      ),
      body_chain_warning=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_CHAIN_WARNING",
        0.75,
        minimum=0.0,
        maximum=1.0,
      ),
      subject_height_block=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_SUBJECT_BLOCK",
        0.28,
        minimum=0.0,
        maximum=1.0,
      ),
      subject_height_warning=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_SUBJECT_WARNING",
        0.38,
        minimum=0.0,
        maximum=1.0,
      ),
      blur_variance_block=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_BLUR_BLOCK",
        30.0,
        minimum=1.0,
        maximum=10000.0,
      ),
      blur_variance_warning=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_BLUR_WARNING",
        55.0,
        minimum=1.0,
        maximum=10000.0,
      ),
      comparable_person_area_ratio=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_SECOND_PERSON_RATIO",
        0.55,
        minimum=0.0,
        maximum=1.0,
      ),
      ambiguous_people_block=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_PEOPLE_BLOCK",
        0.30,
        minimum=0.0,
        maximum=1.0,
      ),
      ambiguous_people_warning=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_PEOPLE_WARNING",
        0.15,
        minimum=0.0,
        maximum=1.0,
      ),
      camera_shift_warning=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_CAMERA_SHIFT_WARNING",
        0.035,
        minimum=0.0,
        maximum=1.0,
      ),
      lighting_mean_low=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_LIGHTING_MEAN_LOW",
        45.0,
        minimum=0.0,
        maximum=255.0,
      ),
      lighting_mean_high=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_LIGHTING_MEAN_HIGH",
        210.0,
        minimum=0.0,
        maximum=255.0,
      ),
      lighting_contrast_low=_float_from_env(
        "SIDE_SQUAT_PREFLIGHT_LIGHTING_CONTRAST_LOW",
        30.0,
        minimum=0.0,
        maximum=127.5,
      ),
    )


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
  return max(minimum, min(maximum, value))


def _numbers(observations: Iterable[dict[str, Any]], key: str) -> list[float]:
  values: list[float] = []
  for observation in observations:
    value = observation.get(key)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
      values.append(float(value))
  return values


def _mean(values: list[float], default: float = 0.0) -> float:
  return statistics.fmean(values) if values else default


def _median(values: list[float], default: float = 0.0) -> float:
  return float(statistics.median(values)) if values else default


def _check(
  *,
  status: str,
  score: float | None,
  reason_code: str | None,
  details: dict[str, Any],
) -> dict[str, Any]:
  return {
    "status": status,
    "score": round(_clamp(score), 4) if isinstance(score, (int, float)) else None,
    "reasonCode": reason_code,
    "details": details,
  }


def _threshold_status(value: float, *, block: float, warning: float) -> str:
  if value < block:
    return "blocked"
  if value < warning:
    return "warning"
  return "pass"


def _check_reason(status: str, warning_code: str, blocked_code: str) -> str | None:
  if status == "blocked":
    return blocked_code
  if status == "warning":
    return warning_code
  return None


def evaluate_quality_observations(
  observations: list[dict[str, Any]],
  *,
  exercise_type: str,
  frame_count: int,
  fps: float,
  duration_ms: int,
  thresholds: QualityPreflightThresholds | None = None,
  processing_duration_ms: int = 0,
) -> dict[str, Any]:
  """Turn sampled-frame evidence into a persisted, explainable gate result.

  This pure function is the authoritative decision layer. Frame decoding and
  model inference deliberately live outside it so every policy branch can be
  regression-tested without video or ML dependencies.
  """
  resolved = thresholds or QualityPreflightThresholds.from_env()
  sample_count = len(observations)
  pose_frames = [observation for observation in observations if observation.get("poseDetected") is True]
  pose_coverage = len(pose_frames) / sample_count if sample_count else 0.0

  side_view_score = _mean(_numbers(pose_frames, "sideViewScore")) * _clamp(pose_coverage / 0.75)
  body_chain_coverage = _mean(_numbers(observations, "bodyChainVisible"))
  subject_height = _median(_numbers(pose_frames, "subjectHeight"))
  blur_variance = _median(_numbers(observations, "blurVariance"))
  feet_coverage = _mean(_numbers(observations, "feetVisible"))

  comparable_person_frames = [
    observation
    for observation in observations
    if int(observation.get("personDetectionCount") or 0) >= 2
    and float(observation.get("secondPersonAreaRatio") or 0.0) >= resolved.comparable_person_area_ratio
  ]
  ambiguous_people_coverage = len(comparable_person_frames) / sample_count if sample_count else 0.0
  dominant_lifter_score = _clamp(1.0 - ambiguous_people_coverage)

  side_status = _threshold_status(
    side_view_score,
    block=resolved.side_view_block,
    warning=resolved.side_view_warning,
  )
  body_status = _threshold_status(
    body_chain_coverage,
    block=resolved.body_chain_block,
    warning=resolved.body_chain_warning,
  )
  subject_status = _threshold_status(
    subject_height,
    block=resolved.subject_height_block,
    warning=resolved.subject_height_warning,
  )
  blur_status = _threshold_status(
    blur_variance,
    block=resolved.blur_variance_block,
    warning=resolved.blur_variance_warning,
  )
  people_status = (
    "blocked"
    if ambiguous_people_coverage >= resolved.ambiguous_people_block
    else "warning"
    if ambiguous_people_coverage >= resolved.ambiguous_people_warning
    else "pass"
  )

  blur_score = _clamp(blur_variance / max(resolved.blur_variance_warning, 1.0))
  people_details = {
    "ambiguousSampleCoverage": round(ambiguous_people_coverage, 4),
    "comparablePersonAreaRatioThreshold": resolved.comparable_person_area_ratio,
    "warningCoverageThreshold": resolved.ambiguous_people_warning,
    "blockCoverageThreshold": resolved.ambiguous_people_block,
    "supportingDetector": "opencv_hog",
  }
  checks = {
    "sideView": _check(
      status=side_status,
      score=side_view_score,
      reason_code=_check_reason(side_status, "side_view_imperfect", "camera_not_side_facing"),
      details={
        "poseCoverage": round(pose_coverage, 4),
        "warningThreshold": resolved.side_view_warning,
        "blockThreshold": resolved.side_view_block,
      },
    ),
    "bodyChain": _check(
      status=body_status,
      score=body_chain_coverage,
      reason_code=_check_reason(body_status, "body_chain_intermittent", "body_chain_not_visible"),
      details={
        "visibleSampleCoverage": round(body_chain_coverage, 4),
        "warningThreshold": resolved.body_chain_warning,
        "blockThreshold": resolved.body_chain_block,
        "requiredJoints": ["visible shoulder", "visible hip", "visible knee", "visible ankle"],
      },
    ),
    "subjectScale": _check(
      status=subject_status,
      score=_clamp(subject_height / max(resolved.subject_height_warning, 0.001)),
      reason_code=_check_reason(subject_status, "lifter_somewhat_small", "lifter_too_small"),
      details={
        "medianShoulderToAnkleHeight": round(subject_height, 4),
        "warningThreshold": resolved.subject_height_warning,
        "blockThreshold": resolved.subject_height_block,
      },
    ),
    "motionBlur": _check(
      status=blur_status,
      score=blur_score,
      reason_code=_check_reason(blur_status, "motion_blur_warning", "motion_blur_excessive"),
      details={
        "medianLaplacianVariance": round(blur_variance, 3),
        "warningThreshold": resolved.blur_variance_warning,
        "blockThreshold": resolved.blur_variance_block,
      },
    ),
    "dominantLifter": _check(
      status=people_status,
      score=dominant_lifter_score,
      reason_code=_check_reason(people_status, "dominant_lifter_uncertain", "dominant_lifter_unresolved"),
      details=dict(people_details),
    ),
    "multiplePeople": _check(
      status=people_status,
      score=dominant_lifter_score,
      reason_code=_check_reason(people_status, "multiple_people_present", "multiple_people_ambiguous"),
      details=dict(people_details),
    ),
  }

  camera_shifts = _numbers(observations, "cameraShiftRatio")
  camera_shift = _median(camera_shifts)
  camera_status = "warning" if camera_shift > resolved.camera_shift_warning else "pass"
  checks["cameraMovement"] = _check(
    status=camera_status,
    score=_clamp(1.0 - camera_shift / max(resolved.camera_shift_warning * 2.0, 0.001)),
    reason_code="camera_movement_detected" if camera_status == "warning" else None,
    details={
      "medianNormalizedShift": round(camera_shift, 5),
      "warningThreshold": resolved.camera_shift_warning,
    },
  )

  luminance_mean = _median(_numbers(observations, "luminanceMean"))
  luminance_contrast = _median(_numbers(observations, "luminanceStd"))
  lighting_status = (
    "warning"
    if luminance_mean < resolved.lighting_mean_low
    or luminance_mean > resolved.lighting_mean_high
    or luminance_contrast < resolved.lighting_contrast_low
    else "pass"
  )
  checks["lighting"] = _check(
    status=lighting_status,
    score=_clamp(luminance_contrast / max(resolved.lighting_contrast_low, 1.0)),
    reason_code="lighting_quality_low" if lighting_status == "warning" else None,
    details={
      "medianLuminance": round(luminance_mean, 3),
      "medianContrast": round(luminance_contrast, 3),
      "meanRange": [resolved.lighting_mean_low, resolved.lighting_mean_high],
      "contrastWarningThreshold": resolved.lighting_contrast_low,
    },
  )
  checks["feetVisibility"] = _check(
    status="warning" if feet_coverage < resolved.body_chain_warning else "pass",
    score=feet_coverage,
    reason_code="feet_intermittently_visible" if feet_coverage < resolved.body_chain_warning else None,
    details={"visibleSampleCoverage": round(feet_coverage, 4)},
  )
  checks["barbellCollarVisibility"] = _check(
    status="not_applicable" if exercise_type == "goblet squat" else "unmeasured",
    score=None,
    reason_code=(
      "goblet_squat_has_no_barbell_collar"
      if exercise_type == "goblet squat"
      else "dedicated_collar_localizer_not_available"
    ),
    details={"blocking": False},
  )
  checks["rackOcclusion"] = _check(
    status="unmeasured",
    score=None,
    reason_code="rack_occlusion_detector_not_available",
    details={"blocking": False},
  )
  checks["sourceFrameRate"] = _check(
    status="pass",
    score=None,
    reason_code=None,
    details={"framesPerSecond": round(max(fps, 0.0), 3)},
  )
  checks["videoDuration"] = _check(
    status="pass",
    score=None,
    reason_code=None,
    details={"durationMs": max(duration_ms, 0)},
  )

  required_statuses = [checks[name]["status"] for name in _REQUIRED_CHECKS]
  non_blocking_warnings = [
    name
    for name, check in checks.items()
    if name not in _REQUIRED_CHECKS and check["status"] == "warning"
  ]
  status_value = (
    "blocked"
    if "blocked" in required_statuses
    else "warning"
    if "warning" in required_statuses or non_blocking_warnings
    else "pass"
  )
  confidence_scores = [
    float(checks[name]["score"])
    for name in _REQUIRED_CHECKS
    if isinstance(checks[name].get("score"), (int, float))
  ]
  overall_confidence = _mean(confidence_scores)

  message_by_reason = {
    "camera_not_side_facing": "Record from a more direct side angle so the visible joints overlap cleanly.",
    "body_chain_not_visible": "Keep the visible shoulder, hip, knee, ankle, and foot in frame through every rep.",
    "lifter_too_small": "Move the camera closer while keeping the full body visible.",
    "motion_blur_excessive": "Add light and keep the camera steady so the lifter stays sharp during the rep.",
    "dominant_lifter_unresolved": "Record with one clear lifter and keep other people out of the lifting area.",
    "multiple_people_ambiguous": "Keep other people from crossing or standing near the lifter.",
    "side_view_imperfect": "A more direct side angle will improve squat geometry confidence.",
    "body_chain_intermittent": "Keep the visible joints and feet unobstructed for the whole set.",
    "lifter_somewhat_small": "Move a little closer while preserving full-body framing.",
    "motion_blur_warning": "More light or a steadier camera will improve tracking.",
    "dominant_lifter_uncertain": "Keep the lifter visually separated from other people.",
    "multiple_people_present": "Avoid people crossing the background during the set.",
    "camera_movement_detected": "Place the phone on a stable surface or tripod.",
    "lighting_quality_low": "Use brighter, more even lighting on the lifter and barbell.",
    "feet_intermittently_visible": "Keep both feet inside the frame for the entire set.",
  }
  user_messages: list[str] = []
  recording_tips: list[str] = []
  for check in checks.values():
    reason_code = check.get("reasonCode")
    message = message_by_reason.get(reason_code)
    if not message or message in user_messages:
      continue
    user_messages.append(message)
    if check["status"] != "blocked":
      recording_tips.append(message)

  sampled_frames = [
    {
      "frameIndex": int(observation.get("frameIndex") or 0),
      "timestampMs": int(observation.get("timestampMs") or 0),
      "poseDetected": observation.get("poseDetected") is True,
      "sideViewScore": observation.get("sideViewScore"),
      "bodyChainVisible": observation.get("bodyChainVisible"),
      "subjectHeight": observation.get("subjectHeight"),
      "feetVisible": observation.get("feetVisible"),
      "blurVariance": observation.get("blurVariance"),
      "personDetectionCount": int(observation.get("personDetectionCount") or 0),
      "secondPersonAreaRatio": observation.get("secondPersonAreaRatio"),
      "cameraShiftRatio": observation.get("cameraShiftRatio"),
      "luminanceMean": observation.get("luminanceMean"),
      "luminanceStd": observation.get("luminanceStd"),
    }
    for observation in observations
  ]

  return {
    "status": status_value,
    "overallConfidence": round(_clamp(overall_confidence), 4),
    "checks": checks,
    "userMessages": user_messages,
    "recordingTips": recording_tips,
    "modelVersion": QUALITY_PREFLIGHT_MODEL_VERSION,
    "thresholdVersion": QUALITY_PREFLIGHT_THRESHOLD_VERSION,
    "thresholds": asdict(resolved),
    "sampledFrameMetadata": {
      "requestedSampleCount": resolved.sample_count,
      "sampledFrameCount": sample_count,
      "sourceFrameCount": max(frame_count, 0),
      "sourceFrameRate": round(max(fps, 0.0), 3),
      "videoDurationMs": max(duration_ms, 0),
      "frames": sampled_frames,
    },
    "processingDurationMs": max(processing_duration_ms, 0),
  }


def _scaled_dimensions(width: int, height: int, max_dimension: int) -> tuple[int, int]:
  longest = max(width, height)
  if longest <= max_dimension or longest <= 0:
    return width, height
  scale = max_dimension / longest
  return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _landmark_value(landmarks: Any, index: int, key: str) -> float:
  return float(getattr(landmarks.landmark[index], key, 0.0))


def _pose_observation(landmarks: Any, visibility_threshold: float) -> dict[str, float | bool]:
  # MediaPipe indices: shoulders 11/12, hips 23/24, knees 25/26,
  # ankles 27/28, heels 29/30, and foot indices 31/32.
  side_candidates: list[tuple[float, list[int], int, int]] = []
  for chain, heel, foot in (([11, 23, 25, 27], 29, 31), ([12, 24, 26, 28], 30, 32)):
    visibility = [_landmark_value(landmarks, index, "visibility") for index in chain]
    side_candidates.append((_mean(visibility), chain, heel, foot))

  _, selected_chain, heel_index, foot_index = max(side_candidates, key=lambda value: value[0])
  chain_visibility = [_landmark_value(landmarks, index, "visibility") for index in selected_chain]
  chain_inside_frame = all(
    -0.03 <= _landmark_value(landmarks, index, "x") <= 1.03
    and -0.03 <= _landmark_value(landmarks, index, "y") <= 1.03
    for index in selected_chain
  )
  body_chain_visible = float(
    chain_inside_frame and all(value >= visibility_threshold for value in chain_visibility)
  )
  shoulder_y = _landmark_value(landmarks, selected_chain[0], "y")
  ankle_y = _landmark_value(landmarks, selected_chain[-1], "y")
  subject_height = abs(ankle_y - shoulder_y)
  bilateral_gap = _mean([
    abs(_landmark_value(landmarks, 11, "x") - _landmark_value(landmarks, 12, "x")),
    abs(_landmark_value(landmarks, 23, "x") - _landmark_value(landmarks, 24, "x")),
  ])
  side_view_score = _clamp(1.0 - bilateral_gap / max(subject_height * 0.42, 0.08))
  feet_visible = float(
    _landmark_value(landmarks, heel_index, "visibility") >= visibility_threshold
    and _landmark_value(landmarks, foot_index, "visibility") >= visibility_threshold
    and -0.03 <= _landmark_value(landmarks, heel_index, "y") <= 1.03
    and -0.03 <= _landmark_value(landmarks, foot_index, "y") <= 1.03
  )
  return {
    "poseDetected": True,
    "sideViewScore": round(side_view_score, 4),
    "bodyChainVisible": body_chain_visible,
    "subjectHeight": round(subject_height, 4),
    "feetVisible": feet_visible,
  }


class SideSquatQualityPreflight:
  """Decode sparse frames and produce the versioned preflight contract."""

  def __init__(self, thresholds: QualityPreflightThresholds | None = None) -> None:
    self.thresholds = thresholds or QualityPreflightThresholds.from_env()

  def evaluate_file(self, file_path: str | Path, *, exercise_type: str) -> dict[str, Any]:
    started = time.perf_counter()

    try:
      import cv2  # type: ignore
      import mediapipe as mp  # type: ignore
      import numpy as np  # type: ignore
    except ImportError as error:
      raise RuntimeError("Quality preflight requires OpenCV, NumPy, and MediaPipe.") from error

    capture = cv2.VideoCapture(str(file_path))
    if not capture.isOpened():
      capture.release()
      raise RuntimeError("Unable to open the uploaded video for quality preflight.")

    frame_count = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
    fps = max(0.0, float(capture.get(cv2.CAP_PROP_FPS) or 0.0))
    duration_ms = int(round(frame_count / fps * 1000)) if frame_count > 0 and fps > 0 else 0
    if frame_count <= 0:
      capture.release()
      raise RuntimeError("Uploaded video has no decodable frames.")

    # Avoid codec-dependent blank boundary frames while still covering the
    # full set from its opening through its closing movement.
    edge_inset = frame_count // 50
    first_sample = min(edge_inset, frame_count - 1)
    last_sample = max(first_sample, frame_count - 1 - edge_inset)
    indices = sorted({
      int(round(value))
      for value in np.linspace(
        first_sample,
        last_sample,
        num=min(self.thresholds.sample_count, frame_count),
      )
    })
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    observations: list[dict[str, Any]] = []
    previous_gray = None
    decoded_indices: set[int] = set()
    decode_retry_step = max(1, frame_count // max(len(indices) * 8, 1))

    try:
      with mp.solutions.pose.Pose(
        static_image_mode=True,
        # Complexity 1 uses MediaPipe's bundled full model. Complexity 0
        # attempts a runtime download in this dependency version, which is not
        # acceptable for offline local development or Render workers.
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.45,
      ) as pose:
        for requested_frame_index in indices:
          read_ok = False
          frame = None
          frame_index = requested_frame_index
          retry_candidates = [requested_frame_index]
          retry_candidates.extend(
            max(first_sample, requested_frame_index - decode_retry_step * retry_index)
            for retry_index in range(1, 9)
          )
          for candidate_index in dict.fromkeys(retry_candidates):
            if candidate_index in decoded_indices:
              continue
            capture.set(cv2.CAP_PROP_POS_FRAMES, candidate_index)
            read_ok, frame = capture.read()
            if read_ok and frame is not None:
              frame_index = candidate_index
              decoded_indices.add(candidate_index)
              break
          if not read_ok or frame is None:
            continue

          height, width = frame.shape[:2]
          scaled_width, scaled_height = _scaled_dimensions(
            width,
            height,
            self.thresholds.max_frame_dimension,
          )
          if (scaled_width, scaled_height) != (width, height):
            frame = cv2.resize(frame, (scaled_width, scaled_height), interpolation=cv2.INTER_AREA)

          gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
          rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
          pose_result = pose.process(rgb)
          observation: dict[str, Any] = {
            "frameIndex": frame_index,
            "timestampMs": int(round(frame_index / fps * 1000)) if fps > 0 else 0,
            "poseDetected": False,
            "sideViewScore": 0.0,
            "bodyChainVisible": 0.0,
            "subjectHeight": 0.0,
            "feetVisible": 0.0,
            "blurVariance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
            "cameraShiftRatio": 0.0,
            "luminanceMean": round(float(gray.mean()), 3),
            "luminanceStd": round(float(gray.std()), 3),
          }
          if pose_result.pose_landmarks is not None:
            observation.update(
              _pose_observation(pose_result.pose_landmarks, self.thresholds.pose_visibility)
            )

          # HOG is supporting evidence only. Blocking requires a comparable
          # second person on a sustained share of sampled frames.
          boxes, _weights = hog.detectMultiScale(
            gray,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
          )
          areas = sorted((int(box[2]) * int(box[3]) for box in boxes), reverse=True)
          observation["personDetectionCount"] = len(areas)
          observation["secondPersonAreaRatio"] = (
            round(areas[1] / max(areas[0], 1), 4) if len(areas) >= 2 else 0.0
          )

          if previous_gray is not None and previous_gray.shape == gray.shape:
            shift, _response = cv2.phaseCorrelate(
              previous_gray.astype(np.float32),
              gray.astype(np.float32),
            )
            diagonal = math.hypot(gray.shape[1], gray.shape[0])
            observation["cameraShiftRatio"] = round(
              math.hypot(float(shift[0]), float(shift[1])) / max(diagonal, 1.0),
              5,
            )
          previous_gray = gray
          observations.append(observation)
    finally:
      capture.release()

    processing_duration_ms = int(round((time.perf_counter() - started) * 1000))
    return evaluate_quality_observations(
      observations,
      exercise_type=exercise_type,
      frame_count=frame_count,
      fps=fps,
      duration_ms=duration_ms,
      thresholds=self.thresholds,
      processing_duration_ms=processing_duration_ms,
    )
