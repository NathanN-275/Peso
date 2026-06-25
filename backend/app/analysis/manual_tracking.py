from __future__ import annotations

import copy
import logging
import math
from itertools import product
from statistics import median
from typing import Any


TRACKING_SETUP_VERSION = 1
LEGACY_UPPER_BACK_ANCHOR = "shoulder"
UPPER_BACK_ANCHOR = "upper_back"
USER_BODY_ANCHORS = (UPPER_BACK_ANCHOR, "hip", "knee", "ankle")
BODY_ANCHORS = (LEGACY_UPPER_BACK_ANCHOR, "hip", "knee", "ankle")
FUSED_BODY_ANCHORS = ("hip", "knee", "ankle")
DISPLAY_BODY_ANCHORS = ("upper_back", *FUSED_BODY_ANCHORS)
ALL_ANCHORS = (*USER_BODY_ANCHORS, "barbell")
MIN_TRACK_CONFIDENCE = 0.42
MIN_MODEL_VISIBILITY = 0.15
PIN_PERSISTENCE_CONFIDENCE = 0.24
MAX_JOINT_DISPLACEMENT_PX = 15
SOURCE_NAMES = (
  "reference",
  "pin_guided",
  "pin_estimated",
  "kinematic_estimate",
  "pin_visual_fallback",
  "automatic",
  "automatic_recovery",
  "stale_pin_rejected",
  "stale_pin_stuck",
  "gap",
)
JOINT_DISPLACEMENT_RATIOS = {
  UPPER_BACK_ANCHOR: 0.042,
  LEGACY_UPPER_BACK_ANCHOR: 0.042,
  "hip": 0.036,
  "knee": 0.052,
  "ankle": 0.044,
}
JOINT_DISPLACEMENT_FLOORS_PX = {
  UPPER_BACK_ANCHOR: 24.0,
  LEGACY_UPPER_BACK_ANCHOR: 24.0,
  "hip": 22.0,
  "knee": 32.0,
  "ankle": 28.0,
}
FAST_KNEE_CAP_MULTIPLIER = 2.35
FAST_KNEE_VELOCITY_RATIO_PER_SECOND = 0.45
MAX_SHORT_KNEE_ESTIMATE_FAILURES = 2
BODY_PIN_DIAGNOSTIC_FRAME_LIMIT = 150
KNEE_DEBUG_TRACK_FIELDS = (
  "velocity_cap_px",
  "actual_displacement_px",
  "rejected_candidate_displacement_px",
  "velocity_capped",
  "velocity_cap_reused_previous",
  "stale_track",
  "fast_motion_frame",
  "motion_velocity_px_per_sec",
  "tracking_frame_gap",
  "sampled_fps",
  "prediction_error_px",
  "smoothing_window_size",
  "smoothing_displacement_px",
  "fast_motion_smoothing_reduced",
)

logger = logging.getLogger(__name__)


def _normalize_anchor_map(anchors: dict[str, Any]) -> dict[str, Any]:
  normalized = dict(anchors)
  if UPPER_BACK_ANCHOR not in normalized and LEGACY_UPPER_BACK_ANCHOR in normalized:
    normalized[UPPER_BACK_ANCHOR] = normalized[LEGACY_UPPER_BACK_ANCHOR]
  return normalized


def _normalized_tracking_setup(setup: dict[str, Any]) -> dict[str, Any]:
  anchors = setup.get("anchors")
  if not isinstance(anchors, dict):
    return setup
  normalized_anchors = _normalize_anchor_map(anchors)
  return {**setup, "anchors": normalized_anchors}


def _anchor_track(
  tracking: dict[str, Any],
  name: str,
) -> dict[int, dict[str, Any]]:
  tracks = tracking.get("tracks") or {}
  if name == UPPER_BACK_ANCHOR:
    return (
      tracks.get(UPPER_BACK_ANCHOR)
      or tracks.get(LEGACY_UPPER_BACK_ANCHOR)
      or {}
    )
  return tracks.get(name) or {}


def validate_tracking_setup(value: Any, *, duration_ms: int | None = None) -> tuple[dict[str, Any] | None, str | None]:
  if value is None:
    return None, None
  if not isinstance(value, dict):
    return None, "tracking_setup_not_object"
  if value.get("version") != TRACKING_SETUP_VERSION:
    return None, "unsupported_tracking_setup_version"
  if value.get("barbell_target") != "near_side_collar":
    return None, "unsupported_barbell_target"

  reference_time_ms = value.get("reference_time_ms")
  if not isinstance(reference_time_ms, (int, float)) or not math.isfinite(reference_time_ms):
    return None, "invalid_reference_time"
  if reference_time_ms < 0 or (duration_ms is not None and reference_time_ms > duration_ms + 500):
    return None, "reference_time_out_of_bounds"

  anchors = value.get("anchors")
  if not isinstance(anchors, dict):
    return None, "missing_tracking_anchors"

  anchors = _normalize_anchor_map(anchors)
  normalized_anchors: dict[str, dict[str, float]] = {}
  for name in ALL_ANCHORS:
    point = anchors.get(name)
    if not isinstance(point, dict):
      return None, f"missing_{name}_anchor"
    x = point.get("x")
    y = point.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
      return None, f"invalid_{name}_anchor"
    if not math.isfinite(x) or not math.isfinite(y) or not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
      return None, f"invalid_{name}_anchor"
    normalized_anchors[name] = {"x": float(x), "y": float(y)}

  upper_back = normalized_anchors[UPPER_BACK_ANCHOR]
  hip = normalized_anchors["hip"]
  knee = normalized_anchors["knee"]
  ankle = normalized_anchors["ankle"]
  if not (upper_back["y"] < hip["y"] < ankle["y"]):
    return None, "invalid_body_anchor_order"
  if knee["y"] <= hip["y"] - 0.04 or knee["y"] >= ankle["y"] + 0.04:
    return None, "invalid_knee_anchor_order"

  return {
    "version": TRACKING_SETUP_VERSION,
    "reference_time_ms": int(round(reference_time_ms)),
    "barbell_target": "near_side_collar",
    "anchors": normalized_anchors,
  }, None


def _point_distance(first: dict[str, float], second: dict[str, float]) -> float:
  return math.hypot(first["x"] - second["x"], first["y"] - second["y"])


def is_body_point_inside_barbell_occluder(
  point: dict[str, float],
  barbell_diagnostics: dict[str, float] | None,
  margin_px: float = 0.0,
) -> bool:
  if not barbell_diagnostics:
    return False
  center_x = barbell_diagnostics.get("x")
  center_y = barbell_diagnostics.get("y")
  radius = barbell_diagnostics.get("radius")
  scale = float(barbell_diagnostics.get("scale") or 1.0)
  if not all(isinstance(value, (int, float)) for value in (center_x, center_y, radius)):
    return False
  effective_margin = float(margin_px) / max(scale, 1.0)
  return math.hypot(float(point["x"]) - float(center_x), float(point["y"]) - float(center_y)) <= (
    float(radius) + effective_margin
  )


def _landmark_point(
  landmarks: dict[str, Any],
  side: str,
  joint: str,
) -> dict[str, float] | None:
  point = landmarks.get(f"{side}_{joint}")
  if not point:
    return None
  return {
    "x": float(point.get("x", 0.0)),
    "y": float(point.get("y", 0.0)),
    "visibility": float(point.get("visibility", 0.0) or 0.0),
  }


def _upper_back_proxy(
  landmarks: dict[str, Any],
  side: str,
) -> dict[str, float] | None:
  shoulder = _landmark_point(landmarks, side, "shoulder")
  hip = _landmark_point(landmarks, side, "hip")
  if shoulder and hip:
    return {
      "x": (shoulder["x"] * 0.72) + (hip["x"] * 0.28),
      "y": (shoulder["y"] * 0.72) + (hip["y"] * 0.28),
      "visibility": min(shoulder["visibility"], hip["visibility"]),
    }
  return shoulder


def select_manual_tracking_side(reference_frame: dict[str, Any], anchors: dict[str, dict[str, float]]) -> str:
  anchors = _normalize_anchor_map(anchors)
  landmarks = reference_frame.get("landmarks") or {}
  scores: dict[str, float] = {}
  for side in ("left", "right"):
    score = 0.0
    for joint in USER_BODY_ANCHORS:
      model_point = (
        _upper_back_proxy(landmarks, side)
        if joint == UPPER_BACK_ANCHOR
        else _landmark_point(landmarks, side, joint)
      )
      if not model_point:
        score += 2.0
        continue
      weight = 0.65 if joint == UPPER_BACK_ANCHOR else 1.0
      score += _point_distance(anchors[joint], model_point) * weight
    scores[side] = score
  return min(scores, key=scores.get)


def select_reference_source_index(
  pose_frames: list[dict[str, Any]],
  *,
  reference_time_ms: int,
  fps: float | None,
) -> int | None:
  if not pose_frames:
    return None

  timestamped_frames = [
    frame
    for frame in pose_frames
    if isinstance(frame.get("timestamp_ms"), (int, float))
    and math.isfinite(float(frame["timestamp_ms"]))
  ]
  if timestamped_frames:
    selected = min(
      timestamped_frames,
      key=lambda frame: abs(float(frame["timestamp_ms"]) - reference_time_ms),
    )
    return int(selected["source_frame_index"])

  requested_source_index = int(round((reference_time_ms / 1000) * (fps or 0.0)))
  return min(
    (int(frame["source_frame_index"]) for frame in pose_frames),
    key=lambda index: abs(index - requested_source_index),
  )


def _read_sampled_gray_frames(
  file_path: str,
  *,
  source_indices: list[int],
  width: int,
  height: int,
) -> dict[int, Any]:
  import cv2

  wanted = set(source_indices)
  frames: dict[int, Any] = {}
  capture = cv2.VideoCapture(file_path)
  if not capture.isOpened():
    return frames
  if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
    capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

  frame_index = 0
  try:
    while capture.isOpened() and wanted:
      success, frame = capture.read()
      if not success:
        break
      if frame_index in wanted:
        if frame.shape[1] != width or frame.shape[0] != height:
          frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        frames[frame_index] = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        wanted.remove(frame_index)
      frame_index += 1
  finally:
    capture.release()
  return frames


def _feature_points(
  cv2: Any,
  gray: Any,
  point: tuple[float, float],
  *,
  barbell: bool = False,
) -> Any:
  import numpy as np

  height, width = gray.shape[:2]
  radius_ratio = 0.038 if barbell else 0.025
  radius = max(int(round(max(width, height) * radius_ratio)), 12)
  mask = np.zeros_like(gray)
  cv2.circle(mask, (int(round(point[0])), int(round(point[1]))), radius, 255, -1)
  features = cv2.goodFeaturesToTrack(
    gray,
    maxCorners=48 if barbell else 30,
    qualityLevel=0.008 if barbell else 0.01,
    minDistance=3,
    blockSize=5,
    mask=mask,
  )
  if features is not None and len(features) >= 4:
    return features

  offsets = [(-6, -6), (0, -6), (6, -6), (-6, 0), (0, 0), (6, 0), (-6, 6), (0, 6), (6, 6)]
  points = [
    [min(max(point[0] + dx, 0.0), width - 1.0), min(max(point[1] + dy, 0.0), height - 1.0)]
    for dx, dy in offsets
  ]
  return np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)


def _track_template(
  cv2: Any,
  previous_gray: Any,
  gray: Any,
  point: tuple[float, float],
  *,
  search_point: tuple[float, float] | None = None,
  patch_radius_ratio: float = 0.016,
  search_radius_ratio: float = 0.055,
  min_score: float = 0.54,
) -> tuple[tuple[float, float] | None, float]:
  height, width = gray.shape[:2]
  max_dimension = max(width, height)
  patch_radius = max(int(round(max_dimension * patch_radius_ratio)), 8)
  search_radius = max(int(round(max_dimension * search_radius_ratio)), 24)
  center_x = int(round(point[0]))
  center_y = int(round(point[1]))
  template_x0 = center_x - patch_radius
  template_y0 = center_y - patch_radius
  template_x1 = center_x + patch_radius + 1
  template_y1 = center_y + patch_radius + 1
  if template_x0 < 0 or template_y0 < 0 or template_x1 > width or template_y1 > height:
    return None, 0.0
  template = previous_gray[template_y0:template_y1, template_x0:template_x1]
  search_reference = search_point or point
  search_center_x = int(round(search_reference[0]))
  search_center_y = int(round(search_reference[1]))
  search_x0 = max(search_center_x - search_radius - patch_radius, 0)
  search_y0 = max(search_center_y - search_radius - patch_radius, 0)
  search_x1 = min(search_center_x + search_radius + patch_radius + 1, width)
  search_y1 = min(search_center_y + search_radius + patch_radius + 1, height)
  search = gray[search_y0:search_y1, search_x0:search_x1]
  if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
    return None, 0.0
  scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
  _, score, _, location = cv2.minMaxLoc(scores)
  if not math.isfinite(float(score)) or float(score) < min_score:
    return None, 0.0
  matched_center = (
    float(search_x0 + location[0] + patch_radius),
    float(search_y0 + location[1] + patch_radius),
  )
  if math.hypot(matched_center[0] - search_reference[0], matched_center[1] - search_reference[1]) > search_radius:
    return None, 0.0
  return matched_center, float(score)


def _template_settings(
  *,
  barbell: bool,
  joint_name: str | None,
) -> dict[str, float] | None:
  if barbell:
    return {
      "patch_radius_ratio": 0.016,
      "search_radius_ratio": 0.055,
      "min_score": 0.54,
    }
  if joint_name == "knee":
    return {
      "patch_radius_ratio": 0.018,
      "search_radius_ratio": 0.070,
      "min_score": 0.50,
    }
  if joint_name in {UPPER_BACK_ANCHOR, LEGACY_UPPER_BACK_ANCHOR}:
    return {
      "patch_radius_ratio": 0.018,
      "search_radius_ratio": 0.062,
      "min_score": 0.50,
    }
  return None


def _joint_displacement_cap_px(
  frame_shape: tuple[int, int],
  joint_name: str | None,
  *,
  frame_gap: int = 1,
) -> float:
  max_dimension = float(max(frame_shape))
  if joint_name not in JOINT_DISPLACEMENT_RATIOS:
    return float(MAX_JOINT_DISPLACEMENT_PX)
  base_cap = max(
    JOINT_DISPLACEMENT_FLOORS_PX[joint_name],
    max_dimension * JOINT_DISPLACEMENT_RATIOS[joint_name],
  )
  gap_scale = max(1.0, min(float(abs(frame_gap)), 8.0) ** 0.75)
  return base_cap * gap_scale


def _predict_track_point(
  history: list[tuple[int, tuple[float, float]]],
  frame_index: int,
) -> tuple[float, float] | None:
  if len(history) < 2:
    return None
  previous_index, previous_point = history[-2]
  last_index, last_point = history[-1]
  frame_delta = last_index - previous_index
  if frame_delta == 0:
    return None
  horizon = frame_index - last_index
  if horizon == 0 or (horizon > 0) != (frame_delta > 0):
    return None
  scale = horizon / frame_delta
  if abs(scale) > 2.5:
    return None
  return (
    last_point[0] + ((last_point[0] - previous_point[0]) * scale),
    last_point[1] + ((last_point[1] - previous_point[1]) * scale),
  )


def _track_step(
  cv2: Any,
  previous_gray: Any,
  gray: Any,
  point: tuple[float, float],
  *,
  barbell: bool = False,
  joint_name: str | None = None,
  predicted_point: tuple[float, float] | None = None,
  frame_gap: int = 1,
) -> tuple[tuple[float, float] | None, float, dict[str, float]]:
  import numpy as np

  template_config = _template_settings(barbell=barbell, joint_name=joint_name)
  if template_config and joint_name == "knee":
    template_config = {
      **template_config,
      "search_radius_ratio": float(template_config["search_radius_ratio"])
      * max(1.0, min(float(abs(frame_gap)), 8.0) ** 0.75),
    }
  template_search_point = predicted_point if joint_name == "knee" else None
  template_point, template_score = (
    _track_template(
      cv2,
      previous_gray,
      gray,
      point,
      search_point=template_search_point,
      **template_config,
    )
    if template_config
    else (None, 0.0)
  )

  def template_fallback() -> tuple[tuple[float, float] | None, float, dict[str, float]]:
    if template_point is None:
      return None, 0.0, {}
    confidence_multiplier = 0.82 if barbell else 0.72
    confidence_cap = 0.72 if barbell else 0.62
    return template_point, min(template_score * confidence_multiplier, confidence_cap), {
      "template_score": template_score,
      "template_fallback": 1.0,
      **({"prediction_assisted": 1.0} if template_search_point is not None else {}),
    }

  previous_points = _feature_points(cv2, previous_gray, point, barbell=barbell)
  next_points, status, _ = cv2.calcOpticalFlowPyrLK(previous_gray, gray, previous_points, None)
  if next_points is None or status is None:
    return template_fallback()

  valid_old = previous_points[status.flatten() == 1]
  valid_new = next_points[status.flatten() == 1]
  if len(valid_new) < 4:
    return template_fallback()

  back_points, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, previous_gray, valid_new, None)
  if back_points is None or back_status is None:
    return template_fallback()
  back_error = np.linalg.norm(back_points.reshape(-1, 2) - valid_old.reshape(-1, 2), axis=1)
  inlier_mask = (back_status.flatten() == 1) & (back_error <= 2.5)
  if int(inlier_mask.sum()) < 4:
    return template_fallback()

  old_inliers = valid_old.reshape(-1, 2)[inlier_mask]
  new_inliers = valid_new.reshape(-1, 2)[inlier_mask]
  if not barbell:
    motions = new_inliers - old_inliers
    dx = float(median(float(value) for value in motions[:, 0]))
    dy = float(median(float(value) for value in motions[:, 1]))
    next_point = (point[0] + dx, point[1] + dy)
    template_prediction_override = False
    if predicted_point is not None and template_point is not None and template_score >= 0.50:
      optical_flow_error = math.hypot(
        next_point[0] - predicted_point[0],
        next_point[1] - predicted_point[1],
      )
      template_error = math.hypot(
        template_point[0] - predicted_point[0],
        template_point[1] - predicted_point[1],
      )
      predicted_motion = math.hypot(
        predicted_point[0] - point[0],
        predicted_point[1] - point[1],
      )
      optical_flow_motion = math.hypot(dx, dy)
      if (
        template_error + max(4.0, max(gray.shape[:2]) * 0.018) < optical_flow_error
        or (
          predicted_motion > max(8.0, max(gray.shape[:2]) * 0.04)
          and optical_flow_motion < predicted_motion * 0.45
          and template_error < max(10.0, max(gray.shape[:2]) * 0.06)
        )
      ):
        next_point = template_point
        confidence = min(template_score * 0.78, 0.72)
        template_prediction_override = True
      else:
        confidence = min(1.0, (float(inlier_mask.sum()) / max(len(previous_points), 1)) * 1.15)
    else:
      confidence = min(1.0, (float(inlier_mask.sum()) / max(len(previous_points), 1)) * 1.15)
    max_jump = max(gray.shape[:2]) * 0.10 * max(1.0, min(float(abs(frame_gap)), 8.0) ** 0.75)
    height, width = gray.shape[:2]
    if math.hypot(next_point[0] - point[0], next_point[1] - point[1]) > max_jump or not (
      0 <= next_point[0] < width and 0 <= next_point[1] < height
    ):
      return None, 0.0, {}
    return next_point, confidence, {
      "tracked_features": float(len(previous_points)),
      "median_back_error": float(median(float(value) for value in back_error[inlier_mask])),
      **({"template_score": template_score} if template_point is not None else {}),
      **({"prediction_assisted": 1.0} if predicted_point is not None else {}),
      **({"template_prediction_override": 1.0} if template_prediction_override else {}),
      **(
        {
          "predicted_point_x": float(predicted_point[0]),
          "predicted_point_y": float(predicted_point[1]),
          "prediction_error_px": float(
            math.hypot(next_point[0] - predicted_point[0], next_point[1] - predicted_point[1])
          ),
        }
        if predicted_point is not None
        else {}
      ),
    }

  transform, affine_mask = cv2.estimateAffinePartial2D(
    old_inliers,
    new_inliers,
    method=cv2.RANSAC,
    ransacReprojThreshold=2.25,
    maxIters=1000,
    confidence=0.99,
    refineIters=10,
  )
  affine_inlier_count = int(affine_mask.sum()) if affine_mask is not None else 0
  if transform is None or affine_inlier_count < 4:
    motions = new_inliers - old_inliers
    dx = float(median(float(value) for value in motions[:, 0]))
    dy = float(median(float(value) for value in motions[:, 1]))
    motion_residuals = np.linalg.norm(motions - np.asarray([dx, dy]), axis=1)
    median_motion_residual = float(median(float(value) for value in motion_residuals))
    if len(motions) < 6 or median_motion_residual > 2.25:
      return template_fallback()
    next_point = (point[0] + dx, point[1] + dy)
    height, width = gray.shape[:2]
    if not (0 <= next_point[0] < width and 0 <= next_point[1] < height):
      return template_fallback()
    return next_point, min(0.58, float(len(motions)) / max(len(previous_points), 1)), {
      "affine_inliers": 0.0,
      "tracked_features": float(len(previous_points)),
      "median_back_error": float(median(float(value) for value in back_error[inlier_mask])),
      "translation_fallback": 1.0,
    }

  transformed = transform @ np.asarray([point[0], point[1], 1.0], dtype=np.float64)
  next_point = (float(transformed[0]), float(transformed[1]))
  dx = next_point[0] - point[0]
  dy = next_point[1] - point[1]
  max_jump = max(gray.shape[:2]) * 0.10
  if math.hypot(dx, dy) > max_jump:
    return template_fallback()
  height, width = gray.shape[:2]
  if not (0 <= next_point[0] < width and 0 <= next_point[1] < height):
    return template_fallback()
  valid_ratio = float(inlier_mask.sum()) / max(len(previous_points), 1)
  affine_ratio = affine_inlier_count / max(int(inlier_mask.sum()), 1)
  median_back_error = float(median(float(value) for value in back_error[inlier_mask]))
  confidence = min(1.0, (valid_ratio * 0.55) + (affine_ratio * 0.40) + 0.12)
  template_disagreement = None
  if template_point is not None and template_score >= 0.60:
    template_disagreement = math.hypot(
      next_point[0] - template_point[0],
      next_point[1] - template_point[1],
    )
    if template_disagreement > max(5.0, max(gray.shape[:2]) * 0.012):
      next_point = template_point
      confidence = min(template_score * 0.86, 0.78)
    else:
      template_weight = max(template_score, 0.01)
      affine_weight = max(confidence, 0.01)
      weight_sum = template_weight + affine_weight
      next_point = (
        ((next_point[0] * affine_weight) + (template_point[0] * template_weight)) / weight_sum,
        ((next_point[1] * affine_weight) + (template_point[1] * template_weight)) / weight_sum,
      )
  return next_point, confidence, {
    "affine_inliers": float(affine_inlier_count),
    "tracked_features": float(len(previous_points)),
    "median_back_error": median_back_error,
    **({"template_score": template_score} if template_point is not None else {}),
    **({"template_disagreement_px": template_disagreement} if template_disagreement is not None else {}),
  }


def _track_direction(
  cv2: Any,
  frames: dict[int, Any],
  ordered_indices: list[int],
  initial_point: tuple[float, float],
  *,
  barbell: bool = False,
  joint_name: str | None = None,
  fps: float | None = None,
) -> dict[int, dict[str, Any]]:
  if not ordered_indices:
    return {}
  tracks = {
    ordered_indices[0]: {"x": initial_point[0], "y": initial_point[1], "confidence": 1.0}
  }
  current_point = initial_point
  previous_index = ordered_indices[0]
  reference_index = ordered_indices[0]
  accepted_history: list[tuple[int, tuple[float, float]]] = [(previous_index, current_point)]
  consecutive_knee_failures = 0

  def motion_diagnostics(
    *,
    frame_shape: tuple[int, int],
    frame_gap: int,
    displacement_px: float,
    predicted_point: tuple[float, float] | None,
    candidate_point: tuple[float, float] | None,
    confidence: float,
  ) -> tuple[float, dict[str, Any]]:
    normal_cap = _joint_displacement_cap_px(frame_shape, joint_name, frame_gap=frame_gap)
    elapsed_seconds = (
      abs(frame_gap) / float(fps)
      if fps and fps > 0
      else abs(frame_gap) / 18.0
    )
    elapsed_seconds = max(elapsed_seconds, 1.0 / 120.0)
    velocity_px_per_sec = displacement_px / elapsed_seconds
    max_dimension = float(max(frame_shape))
    fast_threshold = max(90.0, max_dimension * FAST_KNEE_VELOCITY_RATIO_PER_SECOND)
    prediction_error = (
      math.hypot(candidate_point[0] - predicted_point[0], candidate_point[1] - predicted_point[1])
      if candidate_point is not None and predicted_point is not None
      else None
    )
    prediction_agrees = (
      prediction_error is None
      or prediction_error <= max(normal_cap, max_dimension * 0.14)
    )
    fast_motion_frame = bool(
      joint_name == "knee"
      and velocity_px_per_sec >= fast_threshold
      and prediction_agrees
      and confidence >= 0.42
    )
    velocity_cap_px = normal_cap * (FAST_KNEE_CAP_MULTIPLIER if fast_motion_frame else 1.0)
    sampled_fps = (float(fps) / max(abs(frame_gap), 1)) if fps and fps > 0 else 18.0 / max(abs(frame_gap), 1)
    return velocity_cap_px, {
      "fast_motion_frame": 1.0 if fast_motion_frame else 0.0,
      "motion_velocity_px_per_sec": velocity_px_per_sec,
      "motion_source": joint_name or "unknown",
      "tracking_frame_gap": float(abs(frame_gap)),
      "sampled_fps": sampled_fps,
      "velocity_cap_px": velocity_cap_px,
      **({"prediction_error_px": prediction_error} if prediction_error is not None else {}),
    }

  def write_knee_estimate(
    frame_index: int,
    fallback_point: tuple[float, float],
    *,
    confidence: float,
    diagnostics: dict[str, Any],
    reason: str,
  ) -> None:
    nonlocal current_point, previous_index, accepted_history
    tracks[frame_index] = {
      "x": fallback_point[0],
      "y": fallback_point[1],
      "confidence": max(min(confidence, 0.48), MIN_TRACK_CONFIDENCE + 0.01),
      **diagnostics,
      "kinematic_estimate": 1.0,
      "estimate_reason": reason,
    }
    current_point = fallback_point
    previous_index = frame_index
    accepted_history.append((frame_index, current_point))
    if len(accepted_history) > 4:
      accepted_history = accepted_history[-4:]

  for frame_index in ordered_indices[1:]:
    frame_gap = abs(frame_index - previous_index)
    predicted_point = _predict_track_point(accepted_history, frame_index) if joint_name == "knee" else None
    next_point, confidence, diagnostics = _track_step(
      cv2,
      frames[previous_index],
      frames[frame_index],
      current_point,
      barbell=barbell,
      joint_name=joint_name,
      predicted_point=predicted_point,
      frame_gap=frame_gap,
    )
    if next_point is None:
      if joint_name == "knee":
        consecutive_knee_failures += 1
        if predicted_point is not None and consecutive_knee_failures <= MAX_SHORT_KNEE_ESTIMATE_FAILURES:
          displacement_px = math.hypot(predicted_point[0] - current_point[0], predicted_point[1] - current_point[1])
          _velocity_cap_px, estimate_motion = motion_diagnostics(
            frame_shape=frames[frame_index].shape[:2],
            frame_gap=frame_gap,
            displacement_px=displacement_px,
            predicted_point=predicted_point,
            candidate_point=predicted_point,
            confidence=MIN_TRACK_CONFIDENCE + 0.06,
          )
          write_knee_estimate(
            frame_index,
            predicted_point,
            confidence=MIN_TRACK_CONFIDENCE + 0.06,
            diagnostics={
              **diagnostics,
              **estimate_motion,
              "predicted_point_x": float(predicted_point[0]),
              "predicted_point_y": float(predicted_point[1]),
              "actual_displacement_px": displacement_px,
            },
            reason="local_tracking_failed_velocity_prediction",
          )
          continue
        fallback_point = predicted_point or current_point
        tracks[frame_index] = {
          "x": fallback_point[0],
          "y": fallback_point[1],
          "confidence": 0.0,
          "tracking_lost": 1.0,
          "stale_track": 1.0,
          **(
            {
              "predicted_point_x": float(predicted_point[0]),
              "predicted_point_y": float(predicted_point[1]),
            }
            if predicted_point is not None
            else {}
          ),
        }
        continue
      break

    proposed_displacement_px = math.hypot(
      next_point[0] - current_point[0],
      next_point[1] - current_point[1],
    )
    max_joint_displacement_px = _joint_displacement_cap_px(
      frames[frame_index].shape[:2],
      joint_name,
      frame_gap=frame_gap,
    )
    velocity_cap_px, adaptive_motion = motion_diagnostics(
      frame_shape=frames[frame_index].shape[:2],
      frame_gap=frame_gap,
      displacement_px=proposed_displacement_px,
      predicted_point=predicted_point,
      candidate_point=next_point,
      confidence=confidence,
    )
    max_joint_displacement_px = velocity_cap_px
    if not barbell and proposed_displacement_px > max_joint_displacement_px:
      logger.debug(
        "Rejected manual %s track at frame %s: %.2f px exceeds %.2f px velocity cap",
        joint_name or "unknown",
        frame_index,
        proposed_displacement_px,
        max_joint_displacement_px,
      )
      if joint_name == "knee":
        consecutive_knee_failures += 1
        fallback_point = predicted_point or current_point
        if predicted_point is not None and consecutive_knee_failures <= MAX_SHORT_KNEE_ESTIMATE_FAILURES:
          estimate_displacement_px = math.hypot(
            fallback_point[0] - current_point[0],
            fallback_point[1] - current_point[1],
          )
          write_knee_estimate(
            frame_index,
            fallback_point,
            confidence=MIN_TRACK_CONFIDENCE + 0.04,
            diagnostics={
              **diagnostics,
              **adaptive_motion,
              "predicted_point_x": float(predicted_point[0]),
              "predicted_point_y": float(predicted_point[1]),
              "actual_displacement_px": estimate_displacement_px,
              "rejected_candidate_displacement_px": proposed_displacement_px,
            },
            reason="velocity_cap_velocity_prediction",
          )
          continue
        tracks[frame_index] = {
          "x": fallback_point[0],
          "y": fallback_point[1],
          "confidence": min(confidence * 0.25, MIN_TRACK_CONFIDENCE - 0.05),
          **diagnostics,
          **adaptive_motion,
          "velocity_capped": 1.0,
          "velocity_cap_reused_previous": 1.0,
          "stale_track": 1.0,
          "velocity_cap_distance_px": proposed_displacement_px,
          "proposed_displacement_px": proposed_displacement_px,
          "max_joint_displacement_px": max_joint_displacement_px,
          **(
            {
              "predicted_point_x": float(predicted_point[0]),
              "predicted_point_y": float(predicted_point[1]),
            }
            if predicted_point is not None
            else {}
          ),
        }
        continue
      next_point = current_point
      confidence = min(confidence * 0.45, MIN_TRACK_CONFIDENCE - 0.02)
      diagnostics = {
        **diagnostics,
        **adaptive_motion,
        "velocity_capped": 1.0,
        "velocity_cap_reused_previous": 1.0,
        "stale_track": 1.0,
        "velocity_cap_distance_px": proposed_displacement_px,
        "proposed_displacement_px": proposed_displacement_px,
        "max_joint_displacement_px": max_joint_displacement_px,
      }

    direct_point = None
    direct_confidence = 0.0
    if barbell and previous_index != reference_index:
      direct_point, direct_confidence, _ = _track_step(
        cv2,
        frames[reference_index],
        frames[frame_index],
        initial_point,
        barbell=True,
        joint_name=joint_name,
      )
    agreement_px = None
    if direct_point is not None and direct_confidence >= 0.55:
      agreement_px = math.hypot(next_point[0] - direct_point[0], next_point[1] - direct_point[1])
      agreement_limit = max(5.0, max(frames[frame_index].shape[:2]) * 0.012)
      if agreement_px > agreement_limit:
        confidence *= 0.82
      else:
        direct_weight = max(direct_confidence, 0.01)
        sequential_weight = max(confidence, 0.01)
        weight_sum = direct_weight + sequential_weight
        next_point = (
          ((next_point[0] * sequential_weight) + (direct_point[0] * direct_weight)) / weight_sum,
          ((next_point[1] * sequential_weight) + (direct_point[1] * direct_weight)) / weight_sum,
        )
        confidence = min(confidence, direct_confidence) + (0.08 if agreement_px <= 2.0 else 0.0)

    tracks[frame_index] = {
      "x": next_point[0],
      "y": next_point[1],
      "confidence": min(confidence, 1.0),
      **diagnostics,
      **adaptive_motion,
      "actual_displacement_px": proposed_displacement_px,
      **({"direction_agreement_px": agreement_px} if agreement_px is not None else {}),
    }
    current_point = next_point
    previous_index = frame_index
    consecutive_knee_failures = 0
    accepted_history.append((frame_index, current_point))
    if len(accepted_history) > 4:
      accepted_history = accepted_history[-4:]
  return tracks


def _smooth_anchor_track(
  tracks: dict[int, dict[str, Any]],
  *,
  reference_index: int,
) -> dict[int, dict[str, Any]]:
  ordered_indices = sorted(tracks)
  if len(ordered_indices) < 3:
    return tracks

  smoothed: dict[int, dict[str, Any]] = {}
  for position, source_index in enumerate(ordered_indices):
    point = tracks[source_index]
    if (
      source_index == reference_index
      or position == 0
      or position == len(ordered_indices) - 1
      or point.get("velocity_cap_reused_previous")
      or point.get("fast_motion_frame")
    ):
      smoothed[source_index] = {
        **point,
        "smoothing_window_size": 1.0,
        "smoothing_displacement_px": 0.0,
        **({"fast_motion_smoothing_reduced": 1.0} if point.get("fast_motion_frame") else {}),
      }
      continue
    neighbor_indices = ordered_indices[max(position - 1, 0):min(position + 2, len(ordered_indices))]
    neighbors = [tracks[index] for index in neighbor_indices]
    smoothed_x = float(median(float(item["x"]) for item in neighbors))
    smoothed_y = float(median(float(item["y"]) for item in neighbors))
    smoothed[source_index] = {
      **point,
      "x": smoothed_x,
      "y": smoothed_y,
      "confidence": float(point["confidence"]),
      "smoothing_window_size": float(len(neighbor_indices)),
      "smoothing_displacement_px": math.hypot(smoothed_x - float(point["x"]), smoothed_y - float(point["y"])),
    }
  return smoothed


def _manual_track_is_usable(track: dict[str, Any] | None) -> bool:
  if not track:
    return False
  if float(track.get("confidence") or 0.0) < MIN_TRACK_CONFIDENCE:
    return False
  return not (
    track.get("velocity_cap_reused_previous")
    or track.get("stale_track")
    or track.get("tracking_lost")
  )


def track_manual_anchors(
  file_path: str,
  *,
  setup: dict[str, Any],
  pose_frames: list[dict[str, Any]],
  fps: float | None,
  width: int,
  height: int,
) -> dict[str, Any]:
  import cv2

  setup = _normalized_tracking_setup(setup)

  source_indices = sorted({int(frame["source_frame_index"]) for frame in pose_frames})
  if not source_indices or width <= 0 or height <= 0:
    return {
      "tracks": {},
      "reference_source_index": None,
      "coverage": {name: 0.0 for name in ALL_ANCHORS},
      "velocity_cap_count": 0,
      "velocity_cap_counts": {name: 0 for name in USER_BODY_ANCHORS},
    }

  reference_index = select_reference_source_index(
    pose_frames,
    reference_time_ms=setup["reference_time_ms"],
    fps=fps,
  )
  if reference_index is None:
    return {
      "tracks": {},
      "reference_source_index": None,
      "coverage": {name: 0.0 for name in ALL_ANCHORS},
      "velocity_cap_count": 0,
      "velocity_cap_counts": {name: 0 for name in USER_BODY_ANCHORS},
    }
  gray_frames = _read_sampled_gray_frames(
    file_path,
    source_indices=source_indices,
    width=width,
    height=height,
  )
  available_indices = [index for index in source_indices if index in gray_frames]
  if reference_index not in gray_frames or not available_indices:
    return {
      "tracks": {},
      "reference_source_index": reference_index,
      "coverage": {name: 0.0 for name in ALL_ANCHORS},
      "velocity_cap_count": 0,
      "velocity_cap_counts": {name: 0 for name in USER_BODY_ANCHORS},
    }

  reference_position = available_indices.index(reference_index)
  tracks: dict[str, dict[int, dict[str, float]]] = {}
  velocity_cap_counts = {name: 0 for name in USER_BODY_ANCHORS}
  stale_track_counts = {name: 0 for name in USER_BODY_ANCHORS}
  for name in ALL_ANCHORS:
    anchor = setup["anchors"][name]
    initial_point = (anchor["x"] * width, anchor["y"] * height)
    is_barbell = name == "barbell"
    forward = _track_direction(
      cv2,
      gray_frames,
      available_indices[reference_position:],
      initial_point,
      barbell=is_barbell,
      joint_name=None if is_barbell else name,
      fps=fps,
    )
    backward = _track_direction(
      cv2,
      gray_frames,
      list(reversed(available_indices[:reference_position + 1])),
      initial_point,
      barbell=is_barbell,
      joint_name=None if is_barbell else name,
      fps=fps,
    )
    combined = {**backward, **forward}
    if not is_barbell:
      velocity_cap_counts[name] = sum(
        1 for point in combined.values() if point.get("velocity_capped")
      )
      stale_track_counts[name] = sum(
        1 for point in combined.values() if point.get("stale_track")
      )
    normalized_tracks = {
      index: {
        "x": point["x"] / width,
        "y": point["y"] / height,
        "confidence": point["confidence"],
        **({"tracking_state": "reference"} if index == reference_index else {"tracking_state": "guided"}),
        **({key: value for key, value in point.items() if key not in {"x", "y", "confidence"}}),
      }
      for index, point in combined.items()
    }
    tracks[name] = _smooth_anchor_track(
      normalized_tracks,
      reference_index=reference_index,
    )

  if UPPER_BACK_ANCHOR in tracks:
    tracks[LEGACY_UPPER_BACK_ANCHOR] = tracks[UPPER_BACK_ANCHOR]
    velocity_cap_counts[LEGACY_UPPER_BACK_ANCHOR] = velocity_cap_counts.get(UPPER_BACK_ANCHOR, 0)
    stale_track_counts[LEGACY_UPPER_BACK_ANCHOR] = stale_track_counts.get(UPPER_BACK_ANCHOR, 0)

  coverage = {
    name: round(
      sum(1 for point in anchor_tracks.values() if _manual_track_is_usable(point)) / max(len(available_indices), 1),
      3,
    )
    for name, anchor_tracks in tracks.items()
  }
  return {
    "tracks": tracks,
    "reference_source_index": reference_index,
    "coverage": coverage,
    "velocity_cap_count": sum(velocity_cap_counts.values()),
    "velocity_cap_counts": velocity_cap_counts,
    "stale_track_count": sum(stale_track_counts.values()),
    "stale_track_counts": stale_track_counts,
  }


def fuse_manual_body_tracks(
  pose_frames: list[dict[str, Any]],
  *,
  setup: dict[str, Any],
  tracking: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  setup = _normalized_tracking_setup(setup)
  base_diagnostics = {
    "upper_back_anchor_key": UPPER_BACK_ANCHOR,
    "upper_back_anchor_semantics": "upper_back_anchor",
    "fused_anchor_names": list(FUSED_BODY_ANCHORS),
    "upper_back_anchor_used_count": 0,
    "pin_owned_landmark_count": 0,
    "model_divergence_accepted_count": 0,
    "body_barbell_occluder_rejection_count": 0,
    "body_pin_frames": [],
    "source_counts": {
      name: {source: 0 for source in SOURCE_NAMES}
      for name in DISPLAY_BODY_ANCHORS
    },
  }
  if not pose_frames or not tracking.get("tracks"):
    return pose_frames, {
      "used": False,
      "selected_side": None,
      "fused_landmark_count": 0,
      "directly_anchored_landmark_count": 0,
      "blended_landmark_count": 0,
      "fallback_landmark_count": 0,
      "rejected_track_count": 0,
      "rejection_reasons": {},
      "coverage": tracking.get("coverage") or {},
      **base_diagnostics,
    }

  reference_source_index = tracking.get("reference_source_index")
  reference_frame = min(
    pose_frames,
    key=lambda frame: abs(int(frame.get("source_frame_index", 0)) - int(reference_source_index or 0)),
  )
  selected_side = select_manual_tracking_side(reference_frame, setup["anchors"])
  fused_frames = copy.deepcopy(pose_frames)
  fused_count = 0
  directly_anchored_count = 0
  blended_count = 0
  pin_owned_count = 0
  fallback_count = 0
  rejected_count = 0
  upper_back_anchor_used_count = 0
  model_divergence_accepted_count = 0
  body_barbell_occluder_rejection_count = 0
  rejection_reasons: dict[str, int] = {}
  source_counts = {
    name: {source: 0 for source in SOURCE_NAMES}
    for name in DISPLAY_BODY_ANCHORS
  }
  manual_active = {joint: False for joint in FUSED_BODY_ANCHORS}
  manual_has_activated = {joint: False for joint in FUSED_BODY_ANCHORS}
  manual_reentry_streak = {joint: 0 for joint in FUSED_BODY_ANCHORS}
  manual_loss_streak = {joint: 0 for joint in FUSED_BODY_ANCHORS}
  knee_stuck_streak = 0
  previous_manual_points: dict[str, dict[str, float]] = {}
  manual_history: dict[str, list[dict[str, float]]] = {joint: [] for joint in FUSED_BODY_ANCHORS}
  previous_valid_chain: dict[str, dict[str, float]] | None = None
  valid_chains: dict[int, dict[str, dict[str, float]]] = {}
  unresolved_frame_positions: list[int] = []
  frame_diagnostics: list[dict[str, Any]] = []
  torso_scale = max(_point_distance(setup["anchors"][UPPER_BACK_ANCHOR], setup["anchors"]["hip"]), 0.08)
  reference_lengths = {
    "torso": _point_distance(setup["anchors"][UPPER_BACK_ANCHOR], setup["anchors"]["hip"]),
    "thigh": _point_distance(setup["anchors"]["hip"], setup["anchors"]["knee"]),
    "shin": _point_distance(setup["anchors"]["knee"], setup["anchors"]["ankle"]),
  }
  reference_torso_vector = {
    "x": setup["anchors"][UPPER_BACK_ANCHOR]["x"] - setup["anchors"]["hip"]["x"],
    "y": setup["anchors"][UPPER_BACK_ANCHOR]["y"] - setup["anchors"]["hip"]["y"],
  }

  def reject(joint: str, reason: str) -> None:
    nonlocal fallback_count, rejected_count
    rejected_count += 1
    fallback_count += 1
    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    manual_active[joint] = False
    manual_reentry_streak[joint] = 0

  def note_rejection(reason: str) -> None:
    nonlocal fallback_count, rejected_count
    rejected_count += 1
    fallback_count += 1
    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

  def barbell_occluder_for_frame(source_index: int) -> dict[str, float] | None:
    barbell_track = _anchor_track(tracking, "barbell").get(source_index)
    if not barbell_track:
      return None
    x = barbell_track.get("x")
    y = barbell_track.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
      return None
    if not math.isfinite(float(x)) or not math.isfinite(float(y)):
      return None
    return {
      "x": float(x),
      "y": float(y),
      "radius": max(0.075, torso_scale * 0.68),
      "scale": 1.0,
    }

  def point_in_barbell_occluder(
    joint: str,
    point: dict[str, float],
    source_index: int,
  ) -> bool:
    if joint not in {UPPER_BACK_ANCHOR, "hip", "knee"}:
      return False
    return is_body_point_inside_barbell_occluder(
      point,
      barbell_occluder_for_frame(source_index),
      margin_px=0.0,
    )

  def note_barbell_occluder_rejection(joint: str) -> None:
    nonlocal body_barbell_occluder_rejection_count
    body_barbell_occluder_rejection_count += 1
    note_rejection(f"{joint}_plate_latch_or_occlusion")

  def record_source(joint: str, source: str) -> None:
    if joint not in source_counts:
      return
    if source not in source_counts[joint]:
      return
    source_counts[joint][source] += 1

  def rounded_debug_value(value: Any, digits: int = 3) -> Any:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
      return round(float(value), digits)
    return value

  def debug_pin_payload(raw_track: dict[str, Any] | None, *, stale: bool | None = None) -> dict[str, Any] | None:
    if not raw_track:
      return None
    payload: dict[str, Any] = {
      "x": round(float(raw_track["x"]), 4),
      "y": round(float(raw_track["y"]), 4),
      "confidence": round(float(raw_track.get("confidence") or 0.0), 3),
    }
    if stale is not None:
      payload["stale"] = stale
    for key in KNEE_DEBUG_TRACK_FIELDS:
      if key in raw_track:
        payload[key] = rounded_debug_value(raw_track.get(key))
    if "predicted_point_x" in raw_track and "predicted_point_y" in raw_track:
      payload["predicted_knee"] = {
        "x": round(float(raw_track["predicted_point_x"]), 4),
        "y": round(float(raw_track["predicted_point_y"]), 4),
      }
    if "estimate_reason" in raw_track:
      payload["estimate_reason"] = raw_track["estimate_reason"]
    return payload

  def debug_recovery_payload(recovery: dict[str, Any] | None) -> dict[str, Any]:
    if not recovery:
      return {}
    payload: dict[str, Any] = {}
    prediction = recovery.get("prediction")
    if prediction:
      payload["predicted_knee"] = {
        "x": round(float(prediction["x"]), 4),
        "y": round(float(prediction["y"]), 4),
      }
    kinematic_point = recovery.get("kinematic_point")
    if kinematic_point:
      payload["kinematic_knee"] = {
        "x": round(float(kinematic_point["x"]), 4),
        "y": round(float(kinematic_point["y"]), 4),
      }
    return payload

  def write_upper_back_landmark(
    landmarks: dict[str, Any],
    point: dict[str, float] | None,
    *,
    source: str,
    raw_shoulder: dict[str, float] | None = None,
  ) -> None:
    landmark_name = f"{selected_side}_upper_back"
    if point is None:
      landmarks.pop(landmark_name, None)
      record_source("upper_back", "gap")
      return

    confidence = min(float(point.get("visibility", point.get("confidence", 0.0)) or 0.0), 0.92)
    tracking_state = "guided"
    manual_source = "pin_guided"
    manual_assisted = True
    user_pinned = True
    accepted_source = source
    if source == "reference":
      tracking_state = "reference"
      manual_source = "reference_pin"
    elif source == "pin_estimated":
      tracking_state = "estimated"
      manual_source = "pin_estimated"
      confidence = max(min(confidence, 0.48), PIN_PERSISTENCE_CONFIDENCE)
      manual_assisted = False
    elif source == "pin_visual_fallback":
      tracking_state = "estimated"
      manual_source = "pin_visual_fallback"
      confidence = max(min(confidence, 0.35), PIN_PERSISTENCE_CONFIDENCE)
      manual_assisted = False
      accepted_source = "visual_fallback"
    elif source == "automatic":
      tracking_state = "automatic"
      manual_source = "automatic"
      manual_assisted = False
      user_pinned = False

    landmarks[landmark_name] = {
      "x": float(point["x"]),
      "y": float(point["y"]),
      "z": float(raw_shoulder.get("z", 0.0)) if raw_shoulder else 0.0,
      "visibility": confidence,
      "manual_assisted": manual_assisted,
      "manual_source": manual_source,
      "user_pinned": user_pinned,
      "accepted_source": accepted_source,
      "tracking_state": tracking_state,
      "upper_back_anchor": True,
    }
    record_source("upper_back", source)

  def chain_lengths(chain: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
      "torso": _point_distance(chain[UPPER_BACK_ANCHOR], chain["hip"]),
      "thigh": _point_distance(chain["hip"], chain["knee"]),
      "shin": _point_distance(chain["knee"], chain["ankle"]),
    }

  def chain_is_valid(chain: dict[str, dict[str, float]]) -> bool:
    if chain["hip"]["y"] < chain[UPPER_BACK_ANCHOR]["y"] - 0.10:
      return False
    if chain["ankle"]["y"] < chain["knee"]["y"] + 0.01:
      return False
    lengths = chain_lengths(chain)
    if min(lengths.values()) <= 1e-5:
      return False
    for segment, length in lengths.items():
      reference_length = max(reference_lengths[segment], 1e-5)
      if not 0.30 <= length / reference_length <= 2.25:
        return False
    shin_length = max(lengths["shin"], 1e-5)
    if not 0.22 <= lengths["thigh"] / shin_length <= 2.55:
      return False
    if not 0.16 <= lengths["torso"] / shin_length <= 3.00:
      return False
    if previous_valid_chain is not None:
      previous_lengths = chain_lengths(previous_valid_chain)
      for segment, length in lengths.items():
        if not 0.38 <= length / max(previous_lengths[segment], 1e-5) <= 2.10:
          return False
    return True

  def knee_context_prediction(source_index: int) -> dict[str, float] | None:
    if previous_valid_chain is None:
      return None
    deltas: list[dict[str, float]] = []
    for context_joint in ("hip", "ankle"):
      track = (tracking["tracks"].get(context_joint) or {}).get(source_index)
      if not _manual_track_is_usable(track):
        continue
      previous_context = previous_valid_chain.get(context_joint)
      if not previous_context:
        continue
      deltas.append({
        "x": float(track["x"]) - previous_context["x"],
        "y": float(track["y"]) - previous_context["y"],
      })
    if not deltas:
      return None
    previous_knee = previous_valid_chain.get("knee")
    if not previous_knee:
      return None
    return {
      "x": previous_knee["x"] + (sum(delta["x"] for delta in deltas) / len(deltas)),
      "y": previous_knee["y"] + (sum(delta["y"] for delta in deltas) / len(deltas)),
    }

  def manual_velocity_prediction(joint: str, source_index: int) -> dict[str, float] | None:
    history = manual_history[joint]
    if len(history) < 2:
      return None
    previous = history[-2]
    last = history[-1]
    frame_delta = last["source_index"] - previous["source_index"]
    if frame_delta == 0:
      return None
    horizon = source_index - last["source_index"]
    if horizon == 0 or (horizon > 0) != (frame_delta > 0):
      return None
    scale = horizon / frame_delta
    if abs(scale) > 2.5:
      return None
    return {
      "x": last["x"] + ((last["x"] - previous["x"]) * scale),
      "y": last["y"] + ((last["y"] - previous["y"]) * scale),
    }

  def knee_velocity_prediction(source_index: int) -> dict[str, float] | None:
    return manual_velocity_prediction("knee", source_index)

  def automatic_knee_recovery_option(
    *,
    source_index: int,
    model_point: dict[str, float],
    model_visibility: float,
  ) -> dict[str, Any] | None:
    prediction = knee_velocity_prediction(source_index) or knee_context_prediction(source_index)
    if prediction is None:
      return None
    residual = _point_distance(model_point, prediction)
    if residual > max(0.025, torso_scale * 0.12):
      return None
    return {
      "source": "automatic_recovery",
      "point": model_point,
      "visibility": min(model_visibility, 0.55),
      "score": 0.58 + (model_visibility * 0.20) - residual,
      "tracking_state": "estimated",
      "model_distance": residual,
      "prediction": prediction,
    }

  def knee_pin_stuck_metrics(
    *,
    track_point: dict[str, float],
    source_index: int,
  ) -> dict[str, Any]:
    if previous_valid_chain is None:
      return {"stuck": False}
    previous_knee = previous_valid_chain.get("knee")
    previous_hip = previous_valid_chain.get("hip")
    previous_ankle = previous_valid_chain.get("ankle")
    if not previous_knee or not previous_hip or not previous_ankle:
      return {"stuck": False}
    hip_point = current_body_point("hip")
    ankle_point = current_body_point("ankle")
    if not hip_point or not ankle_point:
      return {"stuck": False}

    knee_displacement = _point_distance(track_point, previous_knee)
    hip_displacement = _point_distance(hip_point, previous_hip)
    ankle_displacement = _point_distance(ankle_point, previous_ankle)
    context_displacement = max(hip_displacement, ankle_displacement)
    active_motion_threshold = max(0.022, torso_scale * 0.13)
    stuck_motion_limit = max(0.006, context_displacement * 0.28)
    return {
      "stuck": context_displacement >= active_motion_threshold and knee_displacement <= stuck_motion_limit,
      "knee_actual_displacement": knee_displacement,
      "hip_displacement": hip_displacement,
      "ankle_displacement": ankle_displacement,
      "context_displacement": context_displacement,
      "stuck_motion_limit": stuck_motion_limit,
    }

  def kinematic_knee_estimate(
    *,
    hip_point: dict[str, float] | None,
    ankle_point: dict[str, float] | None,
    predicted_point: dict[str, float] | None,
  ) -> dict[str, float] | None:
    if not hip_point or not ankle_point:
      return None
    thigh_length = max(reference_lengths["thigh"], 1e-5)
    shin_length = max(reference_lengths["shin"], 1e-5)
    dx = ankle_point["x"] - hip_point["x"]
    dy = ankle_point["y"] - hip_point["y"]
    distance = math.hypot(dx, dy)
    if distance <= 1e-5:
      return None
    if distance > (thigh_length + shin_length) * 1.20:
      return None
    unit_x = dx / distance
    unit_y = dy / distance
    projected = ((thigh_length * thigh_length) - (shin_length * shin_length) + (distance * distance)) / (2 * distance)
    projected = max(min(projected, thigh_length), 0.0)
    height_sq = max((thigh_length * thigh_length) - (projected * projected), 0.0)
    bend_height = math.sqrt(height_sq)
    base = {
      "x": hip_point["x"] + (unit_x * projected),
      "y": hip_point["y"] + (unit_y * projected),
    }
    perpendicular = (-unit_y, unit_x)
    candidates = [
      {"x": base["x"] + (perpendicular[0] * bend_height), "y": base["y"] + (perpendicular[1] * bend_height)},
      {"x": base["x"] - (perpendicular[0] * bend_height), "y": base["y"] - (perpendicular[1] * bend_height)},
    ]
    reference_hip = setup["anchors"]["hip"]
    reference_ankle = setup["anchors"]["ankle"]
    reference_knee = setup["anchors"]["knee"]
    reference_cross = (
      (reference_ankle["x"] - reference_hip["x"]) * (reference_knee["y"] - reference_hip["y"])
      - (reference_ankle["y"] - reference_hip["y"]) * (reference_knee["x"] - reference_hip["x"])
    )
    target = predicted_point or previous_valid_chain.get("knee") if previous_valid_chain else predicted_point

    def candidate_score(candidate: dict[str, float]) -> float:
      cross = (dx * (candidate["y"] - hip_point["y"])) - (dy * (candidate["x"] - hip_point["x"]))
      bend_penalty = 0.0 if reference_cross == 0 or cross == 0 or (cross > 0) == (reference_cross > 0) else 0.18
      target_penalty = _point_distance(candidate, target) if target else 0.0
      vertical_penalty = 0.08 if candidate["y"] < min(hip_point["y"], ankle_point["y"]) - 0.08 else 0.0
      return target_penalty + bend_penalty + vertical_penalty

    selected = min(candidates, key=candidate_score)
    if not (0.0 <= selected["x"] <= 1.0 and 0.0 <= selected["y"] <= 1.0):
      return None
    return {
      "x": selected["x"],
      "y": selected["y"],
      "visibility": PIN_PERSISTENCE_CONFIDENCE,
    }

  def kinematic_knee_option(
    *,
    source_index: int,
    hip_point: dict[str, float] | None,
    ankle_point: dict[str, float] | None,
  ) -> dict[str, Any] | None:
    predicted = knee_velocity_prediction(source_index) or knee_context_prediction(source_index)
    estimate = kinematic_knee_estimate(
      hip_point=hip_point,
      ankle_point=ankle_point,
      predicted_point=predicted,
    )
    if estimate is None:
      return None
    if point_in_barbell_occluder("knee", estimate, source_index):
      return None
    return {
      "source": "kinematic_estimate",
      "point": {"x": estimate["x"], "y": estimate["y"]},
      "visibility": min(max(float(estimate["visibility"]), PIN_PERSISTENCE_CONFIDENCE), 0.48),
      "score": 0.66,
      "manual_weight": 0.0,
      "tracking_state": "estimated",
      "prediction": predicted,
      "kinematic_point": {"x": estimate["x"], "y": estimate["y"]},
    }

  def persistent_anchor_estimate(
    joint: str,
    source_index: int,
    *,
    raw_track: dict[str, Any] | None = None,
  ) -> dict[str, float]:
    track_is_stale = bool(
      raw_track
      and (
        raw_track.get("velocity_cap_reused_previous")
        or raw_track.get("stale_track")
        or raw_track.get("tracking_lost")
      )
    )
    if joint == "knee":
      contextual_prediction = knee_velocity_prediction(source_index) or knee_context_prediction(source_index)
      if contextual_prediction is not None:
        return {
          "x": contextual_prediction["x"],
          "y": contextual_prediction["y"],
          "visibility": PIN_PERSISTENCE_CONFIDENCE,
        }
    if joint == UPPER_BACK_ANCHOR:
      hip_track = _anchor_track(tracking, "hip").get(source_index)
      if _manual_track_is_usable(hip_track):
        return {
          "x": float(hip_track["x"]) + reference_torso_vector["x"],
          "y": float(hip_track["y"]) + reference_torso_vector["y"],
          "visibility": PIN_PERSISTENCE_CONFIDENCE,
        }

    if raw_track and not track_is_stale:
      x = raw_track.get("x")
      y = raw_track.get("y")
      if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        if math.isfinite(float(x)) and math.isfinite(float(y)):
          return {
            "x": float(x),
            "y": float(y),
            "visibility": max(
              min(float(raw_track.get("confidence") or 0.0), 0.48),
              PIN_PERSISTENCE_CONFIDENCE,
            ),
          }

    predicted = manual_velocity_prediction(joint, source_index) if joint in FUSED_BODY_ANCHORS else None
    if predicted is not None:
      return {
        "x": predicted["x"],
        "y": predicted["y"],
        "visibility": PIN_PERSISTENCE_CONFIDENCE,
      }

    if previous_valid_chain is not None and joint in previous_valid_chain:
      previous_point = previous_valid_chain[joint]
      return {
        "x": previous_point["x"],
        "y": previous_point["y"],
        "visibility": PIN_PERSISTENCE_CONFIDENCE,
      }

    anchor_key = UPPER_BACK_ANCHOR if joint == UPPER_BACK_ANCHOR else joint
    setup_anchor = setup["anchors"][anchor_key]
    return {
      "x": float(setup_anchor["x"]),
      "y": float(setup_anchor["y"]),
      "visibility": PIN_PERSISTENCE_CONFIDENCE,
    }

  def attach_visual_fallback(
    landmark: dict[str, Any],
    joint: str,
    source_index: int,
    *,
    raw_track: dict[str, Any] | None = None,
    reason: str,
  ) -> dict[str, float]:
    estimate = persistent_anchor_estimate(joint, source_index, raw_track=raw_track)
    landmark["prefer_visual_fallback"] = True
    landmark["visual_fallback"] = {
      "source": "pin_visual_fallback",
      "reason": reason,
      "user_pinned": True,
      "manual_source": "pin_visual_fallback",
      "tracking_state": "estimated",
      "confidence": estimate["visibility"],
      "point": {
        "x": estimate["x"],
        "y": estimate["y"],
      },
    }
    return estimate

  for frame_position, frame in enumerate(fused_frames):
    source_index = int(frame.get("source_frame_index", -1))
    landmarks = frame.get("landmarks") or {}
    model_upper_back = _upper_back_proxy(landmarks, selected_side)
    raw_model_shoulder = _landmark_point(landmarks, selected_side, "shoulder")
    upper_back_track = _anchor_track(tracking, UPPER_BACK_ANCHOR).get(source_index)
    upper_back_point = model_upper_back
    upper_back_source = "automatic"
    upper_back_track_point = (
      {
        "x": float(upper_back_track["x"]),
        "y": float(upper_back_track["y"]),
        "visibility": min(float(upper_back_track.get("confidence") or 0.0), 0.92),
      }
      if _manual_track_is_usable(upper_back_track)
      else None
    )
    upper_back_reference_frame = (
      reference_source_index is not None
      and source_index == int(reference_source_index)
    )
    upper_back_raw_track_for_fallback = upper_back_track
    if (
      upper_back_track_point is not None
      and not upper_back_reference_frame
      and point_in_barbell_occluder(UPPER_BACK_ANCHOR, upper_back_track_point, source_index)
    ):
      note_barbell_occluder_rejection("upper_back")
      upper_back_track_point = None
      upper_back_raw_track_for_fallback = None
    if upper_back_track_point is not None:
      upper_back_point = {
        "x": upper_back_track_point["x"],
        "y": upper_back_track_point["y"],
        "visibility": upper_back_track_point["visibility"],
      }
      upper_back_source = (
        "reference"
        if upper_back_track.get("tracking_state") == "reference"
        else "pin_guided"
      )
      upper_back_anchor_used_count += 1
      write_upper_back_landmark(
        landmarks,
        upper_back_point,
        source=upper_back_source,
        raw_shoulder=raw_model_shoulder,
      )
    elif model_upper_back is not None:
      fallback_estimate = persistent_anchor_estimate(
        UPPER_BACK_ANCHOR,
        source_index,
        raw_track=upper_back_raw_track_for_fallback,
      )
      model_residual = _point_distance(model_upper_back, fallback_estimate)
      upper_back_inside_occluder = point_in_barbell_occluder(
        UPPER_BACK_ANCHOR,
        model_upper_back,
        source_index,
      )
      if upper_back_inside_occluder or model_residual > max(0.16, torso_scale * 1.15):
        if upper_back_inside_occluder:
          note_barbell_occluder_rejection("upper_back")
        else:
          note_rejection("upper_back_outside_dynamic_envelope")
        upper_back_point = fallback_estimate
        upper_back_source = "pin_visual_fallback"
        write_upper_back_landmark(
          landmarks,
          upper_back_point,
          source="pin_visual_fallback",
          raw_shoulder=raw_model_shoulder,
        )
      else:
        upper_back_point = model_upper_back
        upper_back_source = "automatic"
        write_upper_back_landmark(
          landmarks,
          upper_back_point,
          source="automatic",
          raw_shoulder=raw_model_shoulder,
        )
    else:
      upper_back_point = persistent_anchor_estimate(
        UPPER_BACK_ANCHOR,
        source_index,
        raw_track=upper_back_raw_track_for_fallback,
      )
      upper_back_source = "pin_visual_fallback"
      write_upper_back_landmark(
        landmarks,
        upper_back_point,
        source="pin_visual_fallback",
        raw_shoulder=raw_model_shoulder,
      )

    frame_diagnostic: dict[str, Any] | None = None
    if len(frame_diagnostics) < BODY_PIN_DIAGNOSTIC_FRAME_LIMIT:
      frame_diagnostic = {
        "source_index": source_index,
        "upper_back_source": upper_back_source,
        "raw_model_shoulder": (
          {
            "x": round(raw_model_shoulder["x"], 4),
            "y": round(raw_model_shoulder["y"], 4),
            "visibility": round(raw_model_shoulder["visibility"], 3),
          }
          if raw_model_shoulder
          else None
        ),
        "accepted_upper_back": (
          {
            "x": round(upper_back_point["x"], 4),
            "y": round(upper_back_point["y"], 4),
            "visibility": round(upper_back_point.get("visibility", 0.0), 3),
          }
          if upper_back_point
          else None
        ),
        "joints": {},
      }
    raw_points: dict[str, dict[str, float]] = {}
    available_points: dict[str, dict[str, float]] = {}
    for joint in FUSED_BODY_ANCHORS:
      track = (tracking["tracks"].get(joint) or {}).get(source_index)
      if track:
        raw_points[joint] = track
      if _manual_track_is_usable(track):
        available_points[joint] = track

    def current_body_point(joint: str) -> dict[str, float] | None:
      track = available_points.get(joint)
      if track:
        return {"x": float(track["x"]), "y": float(track["y"])}
      landmark = landmarks.get(f"{selected_side}_{joint}")
      if not landmark or float(landmark.get("visibility") or 0.0) < MIN_MODEL_VISIBILITY:
        return None
      point = {"x": float(landmark["x"]), "y": float(landmark["y"])}
      if point_in_barbell_occluder(joint, point, source_index):
        return None
      return point

    options_by_joint: dict[str, list[dict[str, Any]]] = {}
    for joint in FUSED_BODY_ANCHORS:
      landmark = landmarks.get(f"{selected_side}_{joint}")
      if not landmark:
        note_rejection("missing_pose_landmark")
        estimate = persistent_anchor_estimate(
          joint,
          source_index,
          raw_track=raw_points.get(joint),
        )
        landmarks[f"{selected_side}_{joint}"] = {
          "x": estimate["x"],
          "y": estimate["y"],
          "z": 0.0,
          "visibility": 0.0,
          "tracking_state": "estimated",
          "manual_source": "pin_visual_fallback",
          "user_pinned": True,
          "prefer_visual_fallback": True,
          "accepted_source": "gap",
          "visual_fallback": {
            "source": "pin_visual_fallback",
            "reason": "missing_pose_landmark",
            "user_pinned": True,
            "manual_source": "pin_visual_fallback",
            "tracking_state": "estimated",
            "confidence": estimate["visibility"],
            "point": {"x": estimate["x"], "y": estimate["y"]},
          },
        }
        options_by_joint[joint] = []
        continue
      model_visibility = float(landmark.get("visibility") or 0.0)
      model_point = {"x": float(landmark["x"]), "y": float(landmark["y"])}
      model_inside_occluder = point_in_barbell_occluder(joint, model_point, source_index)
      if model_inside_occluder:
        note_barbell_occluder_rejection(joint)
        attach_visual_fallback(
          landmark,
          joint,
          source_index,
          raw_track=raw_points.get(joint),
          reason="plate_latch_or_occlusion",
        )
        record_source(joint, "pin_visual_fallback")
        options_by_joint[joint] = []
      else:
        options_by_joint[joint] = [
          {
            "source": "automatic",
            "point": model_point,
            "visibility": model_visibility,
            "score": 0.25 + (model_visibility * 0.35),
          }
        ]
      raw_track = raw_points.get(joint)
      track = available_points.get(joint)
      if not track:
        manual_loss_streak[joint] += 1
        track_stale = bool(
          raw_track
          and (
            raw_track.get("velocity_cap_reused_previous")
            or raw_track.get("stale_track")
            or raw_track.get("tracking_lost")
          )
        )
        if joint == "knee" and track_stale:
          note_rejection("stale_pin_rejected")
          record_source("knee", "stale_pin_rejected")
          manual_active[joint] = False
          manual_reentry_streak[joint] = 0
          recovery = automatic_knee_recovery_option(
            source_index=source_index,
            model_point=model_point,
            model_visibility=model_visibility,
          )
          if recovery is None:
            recovery = (
              kinematic_knee_option(
                source_index=source_index,
                hip_point=current_body_point("hip"),
                ankle_point=current_body_point("ankle"),
              )
              if manual_loss_streak[joint] <= 2
              and available_points.get("hip")
              and available_points.get("ankle")
              else None
            )
          if recovery is not None:
            options_by_joint[joint] = [recovery]
            if frame_diagnostic is not None:
              frame_diagnostic["joints"][joint] = {
                "source": recovery["source"],
                "raw_model": {
                  "x": round(model_point["x"], 4),
                  "y": round(model_point["y"], 4),
                  "visibility": round(model_visibility, 3),
                },
                "raw_pin": debug_pin_payload(raw_track, stale=True),
                "residual": (
                  round(float(recovery["model_distance"]), 4)
                  if recovery.get("model_distance") is not None
                  else None
                ),
                "rejection_reason": "stale_pin_rejected",
                **debug_recovery_payload(recovery),
              }
            continue
          options_by_joint[joint] = []
          if frame_diagnostic is not None:
            frame_diagnostic["joints"][joint] = {
              "source": "gap",
              "raw_model": {
                "x": round(model_point["x"], 4),
                "y": round(model_point["y"], 4),
                "visibility": round(model_visibility, 3),
              },
              "raw_pin": debug_pin_payload(raw_track, stale=True),
              "residual": None,
              "rejection_reason": "stale_pin_rejected",
            }
          continue
        if track_stale:
          note_rejection("stale_pin_rejected")
          record_source(joint, "stale_pin_rejected")
          manual_active[joint] = False
          manual_reentry_streak[joint] = 0
          attach_visual_fallback(
            landmark,
            joint,
            source_index,
            raw_track=raw_track,
            reason="stale_pin_rejected",
          )
          record_source(joint, "pin_visual_fallback")
          if frame_diagnostic is not None:
            frame_diagnostic["joints"][joint] = {
              "source": "pin_visual_fallback",
              "raw_model": {
                "x": round(model_point["x"], 4),
                "y": round(model_point["y"], 4),
                "visibility": round(model_visibility, 3),
              },
              "raw_pin": debug_pin_payload(raw_track, stale=True),
              "residual": None,
              "rejection_reason": "stale_pin_rejected",
            }
          continue
        if joint == "knee" and (
          manual_has_activated[joint] or previous_manual_points.get(joint) is not None
        ):
          note_rejection("pin_track_missing_recent")
          manual_active[joint] = False
          manual_reentry_streak[joint] = 0
          recovery = automatic_knee_recovery_option(
            source_index=source_index,
            model_point=model_point,
            model_visibility=model_visibility,
          )
          if recovery is None:
            recovery = (
              kinematic_knee_option(
                source_index=source_index,
                hip_point=current_body_point("hip"),
                ankle_point=current_body_point("ankle"),
              )
              if manual_loss_streak[joint] <= 2
              and available_points.get("hip")
              and available_points.get("ankle")
              else None
            )
          options_by_joint[joint] = [recovery] if recovery is not None else []
          if frame_diagnostic is not None:
            frame_diagnostic["joints"][joint] = {
              "source": recovery["source"] if recovery is not None else "gap",
              "raw_model": {
                "x": round(model_point["x"], 4),
                "y": round(model_point["y"], 4),
                "visibility": round(model_visibility, 3),
              },
              "raw_pin": None,
              "residual": (
                round(float(recovery["model_distance"]), 4)
                if recovery is not None and recovery.get("model_distance") is not None
                else None
              ),
              "rejection_reason": "pin_track_missing_recent",
              **debug_recovery_payload(recovery),
            }
          continue
        if manual_has_activated[joint] or previous_manual_points.get(joint) is not None:
          note_rejection("pin_track_missing_recent")
          manual_active[joint] = False
          manual_reentry_streak[joint] = 0
          attach_visual_fallback(
            landmark,
            joint,
            source_index,
            raw_track=raw_track,
            reason="pin_track_missing_recent",
          )
          record_source(joint, "pin_visual_fallback")
          if frame_diagnostic is not None:
            frame_diagnostic["joints"][joint] = {
              "source": "pin_visual_fallback",
              "raw_model": {
                "x": round(model_point["x"], 4),
                "y": round(model_point["y"], 4),
                "visibility": round(model_visibility, 3),
              },
              "raw_pin": None,
              "residual": None,
              "rejection_reason": "pin_track_missing_recent",
            }
          continue
        manual_active[joint] = False
        manual_reentry_streak[joint] = 0
        if frame_diagnostic is not None:
          frame_diagnostic["joints"][joint] = {
            "source": "automatic",
            "raw_model": {
              "x": round(model_point["x"], 4),
              "y": round(model_point["y"], 4),
              "visibility": round(model_visibility, 3),
            },
            "raw_pin": None,
            "residual": None,
            "rejection_reason": "pin_track_missing",
          }
        continue

      force_reference_anchor = (
        reference_source_index is not None
        and source_index == int(reference_source_index)
      )
      manual_loss_streak[joint] = 0
      use_manual_track = force_reference_anchor or not manual_has_activated[joint] or manual_active[joint]
      if not use_manual_track:
        manual_reentry_streak[joint] += 1
        use_manual_track = manual_reentry_streak[joint] >= 2
      if not use_manual_track:
        if frame_diagnostic is not None:
          frame_diagnostic["joints"][joint] = {
            "source": "automatic",
            "raw_model": {
              "x": round(model_point["x"], 4),
              "y": round(model_point["y"], 4),
              "visibility": round(model_visibility, 3),
            },
            "raw_pin": debug_pin_payload(track),
            "residual": round(_point_distance(track, model_point), 4),
            "rejection_reason": "manual_reentry_wait",
          }
        continue
      track_point = {
        "x": float(track["x"]),
        "y": float(track["y"]),
      }
      knee_stuck_debug: dict[str, Any] | None = None
      if joint == "knee" and not force_reference_anchor:
        knee_stuck_debug = knee_pin_stuck_metrics(
          track_point=track_point,
          source_index=source_index,
        )
        if knee_stuck_debug.get("stuck"):
          knee_stuck_streak += 1
        else:
          knee_stuck_streak = 0

        if knee_stuck_streak >= 2:
          note_rejection("stale_pin_stuck")
          record_source("knee", "stale_pin_stuck")
          manual_active[joint] = False
          manual_reentry_streak[joint] = 0
          recovery = kinematic_knee_option(
            source_index=source_index,
            hip_point=current_body_point("hip"),
            ankle_point=current_body_point("ankle"),
          )
          if recovery is None and not model_inside_occluder:
            recovery = automatic_knee_recovery_option(
              source_index=source_index,
              model_point=model_point,
              model_visibility=model_visibility,
            )
          if recovery is not None:
            options_by_joint[joint] = [recovery]
          if frame_diagnostic is not None:
            frame_diagnostic["joints"][joint] = {
              "source": recovery["source"] if recovery is not None else ("automatic" if options_by_joint.get(joint) else "gap"),
              "raw_model": {
                "x": round(model_point["x"], 4),
                "y": round(model_point["y"], 4),
                "visibility": round(model_visibility, 3),
              },
              "raw_pin": debug_pin_payload(track, stale=True),
              "residual": (
                round(float(recovery["model_distance"]), 4)
                if recovery is not None and recovery.get("model_distance") is not None
                else round(_point_distance(track_point, model_point), 4)
              ),
              "rejection_reason": "stale_pin_stuck",
              "knee_pin_stuck": True,
              "knee_actual_displacement": round(float(knee_stuck_debug.get("knee_actual_displacement") or 0.0), 4),
              "hip_displacement": round(float(knee_stuck_debug.get("hip_displacement") or 0.0), 4),
              "ankle_displacement": round(float(knee_stuck_debug.get("ankle_displacement") or 0.0), 4),
              "knee_selected_source": recovery["source"] if recovery is not None else "automatic",
              **debug_recovery_payload(recovery),
            }
          continue
      if (
        not force_reference_anchor
        and point_in_barbell_occluder(joint, track_point, source_index)
      ):
        note_barbell_occluder_rejection(joint)
        manual_active[joint] = False
        manual_reentry_streak[joint] = 0
        attach_visual_fallback(
          landmark,
          joint,
          source_index,
          raw_track=None,
          reason="plate_latch_or_occlusion",
        )
        record_source(joint, "pin_visual_fallback")
        if frame_diagnostic is not None:
          frame_diagnostic["joints"][joint] = {
            "source": "pin_visual_fallback",
            "raw_model": {
              "x": round(model_point["x"], 4),
              "y": round(model_point["y"], 4),
              "visibility": round(model_visibility, 3),
            },
            "raw_pin": debug_pin_payload(track),
            "residual": None,
            "rejection_reason": "plate_latch_or_occlusion",
            "inside_barbell_occluder": True,
          }
        continue
      model_distance = _point_distance(track, model_point)
      track_confidence = min(max(float(track["confidence"]), 0.0), 1.0)
      max_model_distance = max(
        0.16,
        torso_scale * (2.00 if model_visibility < MIN_MODEL_VISIBILITY else 1.20),
      )
      accept_pose_divergence = (
        joint == "knee"
        and track_confidence >= 0.70
        and model_distance <= max(max_model_distance, torso_scale * 1.55, 0.24)
      )
      if not force_reference_anchor and model_distance > max_model_distance and not accept_pose_divergence:
        reject(joint, "pose_divergence")
        if frame_diagnostic is not None:
          frame_diagnostic["joints"][joint] = {
            "source": "automatic",
            "raw_model": {
              "x": round(model_point["x"], 4),
              "y": round(model_point["y"], 4),
              "visibility": round(model_visibility, 3),
            },
            "raw_pin": debug_pin_payload(track),
            "residual": round(model_distance, 4),
            "rejection_reason": "pose_divergence",
          }
        continue
      if accept_pose_divergence and model_distance > max_model_distance:
        model_divergence_accepted_count += 1

      previous_point = previous_manual_points.get(joint)
      if (
        not force_reference_anchor
        and previous_point is not None
        and _point_distance(track, previous_point) > max(0.12, torso_scale * 0.95)
      ):
        reject(joint, "temporal_jump")
        if frame_diagnostic is not None:
          frame_diagnostic["joints"][joint] = {
            "source": "automatic",
            "raw_model": {
              "x": round(model_point["x"], 4),
              "y": round(model_point["y"], 4),
              "visibility": round(model_visibility, 3),
            },
            "raw_pin": debug_pin_payload(track),
            "residual": round(model_distance, 4),
            "rejection_reason": "temporal_jump",
          }
        continue

      if force_reference_anchor:
        manual_weight = 1.0
        manual_source = "reference_pin"
        tracking_state = "reference"
      elif track.get("kinematic_estimate"):
        manual_weight = 0.0
        manual_source = "kinematic_estimate"
        tracking_state = "estimated"
      else:
        manual_weight = 1.0
        manual_source = "pin_guided"
        tracking_state = "guided"
      manual_visibility = max(model_visibility, min(track_confidence, 0.92))
      if manual_source == "kinematic_estimate":
        manual_visibility = min(max(track_confidence, PIN_PERSISTENCE_CONFIDENCE), 0.48)
      if accept_pose_divergence and model_distance > max_model_distance:
        manual_visibility = min(manual_visibility, 0.72)
      options_by_joint[joint].append(
        {
          "source": manual_source,
          "point": {
            "x": float(track["x"]),
            "y": float(track["y"]),
          },
          "visibility": manual_visibility,
          "score": 1.15 + (track_confidence * 0.55) - (model_distance * 0.20),
          "manual_weight": manual_weight,
          "track": track,
          "tracking_state": tracking_state,
          "model_distance": model_distance,
          "pose_divergence_accepted": accept_pose_divergence and model_distance > max_model_distance,
        }
      )
      if frame_diagnostic is not None:
        frame_diagnostic["joints"][joint] = {
          "source": manual_source,
          "raw_model": {
            "x": round(model_point["x"], 4),
            "y": round(model_point["y"], 4),
            "visibility": round(model_visibility, 3),
          },
          "raw_pin": debug_pin_payload(track),
          "residual": round(model_distance, 4),
          "rejection_reason": None,
          "pose_divergence_accepted": accept_pose_divergence and model_distance > max_model_distance,
        }

    if frame_diagnostic is not None:
      frame_diagnostics.append(frame_diagnostic)

    if upper_back_point is None or any(not options_by_joint.get(joint) for joint in FUSED_BODY_ANCHORS):
      if frame_diagnostic is not None:
        frame_diagnostic["chain"] = {
          "selected_side": selected_side,
          "valid": False,
          "failure_reason": "missing_chain_candidate",
        }
      unresolved_frame_positions.append(frame_position)
      continue

    combinations: list[tuple[float, tuple[dict[str, Any], ...]]] = []
    for options in product(*(options_by_joint[joint] for joint in FUSED_BODY_ANCHORS)):
      chain = {
        UPPER_BACK_ANCHOR: upper_back_point,
        **{
          joint: options[index]["point"]
          for index, joint in enumerate(FUSED_BODY_ANCHORS)
        },
      }
      if chain_is_valid(chain):
        combinations.append((sum(float(option["score"]) for option in options), options))

    if not combinations:
      if frame_diagnostic is not None:
        frame_diagnostic["chain"] = {
          "selected_side": selected_side,
          "valid": False,
          "failure_reason": "invalid_body_geometry",
        }
      unresolved_frame_positions.append(frame_position)
      for joint in available_points:
        reject(joint, "invalid_body_geometry")
      continue

    _score, selected_options = max(combinations, key=lambda item: item[0])
    chain_has_kinematic_estimate = any(
      option["source"] == "kinematic_estimate"
      for option in selected_options
    )
    selected_chain: dict[str, dict[str, float]] = {}
    selected_chain[UPPER_BACK_ANCHOR] = dict(upper_back_point)
    for joint, option in zip(FUSED_BODY_ANCHORS, selected_options):
      landmark = landmarks[f"{selected_side}_{joint}"]
      selected_chain[joint] = dict(option["point"])
      landmark["x"] = float(option["point"]["x"])
      landmark["y"] = float(option["point"]["y"])
      landmark["visibility"] = float(option["visibility"])
      if frame_diagnostic is not None:
        joint_debug = frame_diagnostic["joints"].setdefault(joint, {})
        joint_debug["accepted"] = {
          "x": round(float(option["point"]["x"]), 4),
          "y": round(float(option["point"]["y"]), 4),
          "confidence": round(float(option["visibility"]), 3),
        }
        joint_debug["accepted_source"] = option["source"]
        if joint == "knee":
          joint_debug["knee_selected_source"] = option["source"]
      if option["source"] == "automatic":
        landmark["tracking_state"] = "automatic"
        landmark.pop("manual_assisted", None)
        landmark.pop("manual_source", None)
        landmark.pop("manual_weight", None)
        landmark["accepted_source"] = "automatic"
        record_source(joint, "automatic")
        if any(
          candidate["source"] != "automatic"
          for candidate in options_by_joint[joint]
        ):
          reject(joint, "whole_chain_fallback")
        continue

      if option["source"] == "automatic_recovery":
        landmark["tracking_state"] = "estimated"
        landmark.pop("manual_assisted", None)
        landmark["manual_source"] = "automatic_recovery"
        landmark["accepted_source"] = "automatic_recovery"
        landmark.pop("manual_weight", None)
        record_source(joint, "automatic_recovery")
        continue

      if option["source"] == "pin_estimated":
        landmark["tracking_state"] = "estimated"
        landmark.pop("manual_assisted", None)
        landmark["manual_source"] = "pin_estimated"
        landmark["manual_weight"] = round(float(option["manual_weight"]), 3)
        landmark["user_pinned"] = True
        record_source(joint, "pin_estimated")
        continue

      if option["source"] == "kinematic_estimate":
        landmark["tracking_state"] = "estimated"
        landmark.pop("manual_assisted", None)
        landmark["manual_source"] = "kinematic_estimate"
        landmark["manual_weight"] = round(float(option["manual_weight"]), 3)
        landmark["user_pinned"] = True
        landmark["accepted_source"] = "kinematic_estimate"
        record_source(joint, "kinematic_estimate")
        continue

      manual_active[joint] = True
      manual_has_activated[joint] = True
      manual_reentry_streak[joint] = 0
      landmark["manual_assisted"] = True
      landmark["manual_source"] = option["source"]
      landmark["manual_weight"] = round(float(option["manual_weight"]), 3)
      landmark["user_pinned"] = True
      landmark["accepted_source"] = option["source"]
      landmark["tracking_state"] = option["tracking_state"]
      if option.get("pose_divergence_accepted"):
        landmark["pose_divergence_accepted"] = True
      record_source(joint, "reference" if option["tracking_state"] == "reference" else "pin_guided")
      previous_manual_points[joint] = {
        "x": float(option["track"]["x"]),
        "y": float(option["track"]["y"]),
        "source_index": float(source_index),
      }
      manual_history[joint].append({
        "x": float(option["track"]["x"]),
        "y": float(option["track"]["y"]),
        "source_index": float(source_index),
      })
      if len(manual_history[joint]) > 4:
        manual_history[joint] = manual_history[joint][-4:]
      fused_count += 1
      pin_owned_count += 1
      if option["source"] == "reference_pin":
        directly_anchored_count += 1
      else:
        blended_count += 1
    if frame_diagnostic is not None:
      selected_lengths = chain_lengths(selected_chain)
      frame_diagnostic["chain"] = {
        "selected_side": selected_side,
        "valid": True,
        "torso_length_ratio": round(selected_lengths["torso"] / max(reference_lengths["torso"], 1e-5), 3),
        "thigh_length_ratio": round(selected_lengths["thigh"] / max(reference_lengths["thigh"], 1e-5), 3),
        "shin_length_ratio": round(selected_lengths["shin"] / max(reference_lengths["shin"], 1e-5), 3),
      }
    if not chain_has_kinematic_estimate:
      valid_chains[frame_position] = selected_chain
      previous_valid_chain = selected_chain

  for frame_position in unresolved_frame_positions:
    landmarks = fused_frames[frame_position].get("landmarks") or {}
    previous_positions = [position for position in valid_chains if position < frame_position]
    following_positions = [position for position in valid_chains if position > frame_position]
    previous_position = max(previous_positions) if previous_positions else None
    following_position = min(following_positions) if following_positions else None
    current_source_index = int(fused_frames[frame_position].get("source_frame_index", -1))

    def context_motion_estimate(
      joint: str,
      anchor_position: int,
    ) -> dict[str, float] | None:
      if joint != "knee":
        return None
      anchor_chain = valid_chains.get(anchor_position)
      if not anchor_chain:
        return None
      deltas: list[dict[str, float]] = []
      for context_joint in ("hip", "ankle"):
        current_track = (tracking["tracks"].get(context_joint) or {}).get(current_source_index)
        if not _manual_track_is_usable(current_track):
          continue
        anchor_point = anchor_chain.get(context_joint)
        if not anchor_point:
          continue
        deltas.append({
          "x": float(current_track["x"]) - anchor_point["x"],
          "y": float(current_track["y"]) - anchor_point["y"],
        })
      if not deltas:
        return None
      anchor_point = anchor_chain.get(joint)
      if not anchor_point:
        return None
      return {
        "x": anchor_point["x"] + (sum(delta["x"] for delta in deltas) / len(deltas)),
        "y": anchor_point["y"] + (sum(delta["y"] for delta in deltas) / len(deltas)),
        "visibility": min(float(anchor_point.get("visibility", 0.48) or 0.48), 0.48),
      }

    def estimated_chain_point(joint: str) -> dict[str, float] | None:
      if joint == "knee":
        if previous_position is not None and frame_position - previous_position <= 2:
          context_estimate = context_motion_estimate(joint, previous_position)
          if context_estimate is not None:
            return context_estimate
        if following_position is not None and following_position - frame_position <= 2:
          context_estimate = context_motion_estimate(joint, following_position)
          if context_estimate is not None:
            return context_estimate
      if previous_position is not None and following_position is not None:
        if following_position - previous_position > 3:
          return None
        span = following_position - previous_position
        weight = (frame_position - previous_position) / max(span, 1)
        previous_point = valid_chains[previous_position][joint]
        following_point = valid_chains[following_position][joint]
        return {
          "x": previous_point["x"] + ((following_point["x"] - previous_point["x"]) * weight),
          "y": previous_point["y"] + ((following_point["y"] - previous_point["y"]) * weight),
          "visibility": min(
            float(previous_point.get("visibility", 0.48) or 0.48),
            float(following_point.get("visibility", 0.48) or 0.48),
            0.48,
          ),
        }
      if previous_position is not None:
        if frame_position - previous_position > 2:
          return None
        context_estimate = context_motion_estimate(joint, previous_position)
        if context_estimate is not None:
          return context_estimate
        previous_point = valid_chains[previous_position][joint]
        return {
          "x": previous_point["x"],
          "y": previous_point["y"],
          "visibility": min(float(previous_point.get("visibility", 0.48) or 0.48), 0.48),
        }
      if following_position is not None:
        if following_position - frame_position > 2:
          return None
        context_estimate = context_motion_estimate(joint, following_position)
        if context_estimate is not None:
          return context_estimate
        following_point = valid_chains[following_position][joint]
        return {
          "x": following_point["x"],
          "y": following_point["y"],
          "visibility": min(float(following_point.get("visibility", 0.48) or 0.48), 0.48),
        }
      return None

    upper_back_landmark_name = f"{selected_side}_upper_back"
    if upper_back_landmark_name not in landmarks:
      upper_back_estimate = (
        estimated_chain_point(UPPER_BACK_ANCHOR)
      )
      if upper_back_estimate is not None:
        write_upper_back_landmark(
          landmarks,
          upper_back_estimate,
          source="pin_estimated",
          raw_shoulder=_landmark_point(landmarks, selected_side, "shoulder"),
        )
      else:
        write_upper_back_landmark(
          landmarks,
          persistent_anchor_estimate(UPPER_BACK_ANCHOR, current_source_index),
          source="pin_visual_fallback",
          raw_shoulder=_landmark_point(landmarks, selected_side, "shoulder"),
        )

    for joint in FUSED_BODY_ANCHORS:
      landmark = landmarks.get(f"{selected_side}_{joint}")
      if not landmark:
        estimate = persistent_anchor_estimate(joint, current_source_index)
        landmarks[f"{selected_side}_{joint}"] = {
          "x": estimate["x"],
          "y": estimate["y"],
          "z": 0.0,
          "visibility": 0.0,
          "tracking_state": "estimated",
          "manual_source": "pin_visual_fallback",
          "user_pinned": True,
          "prefer_visual_fallback": True,
          "accepted_source": "gap",
          "visual_fallback": {
            "source": "pin_visual_fallback",
            "reason": "missing_pose_landmark",
            "user_pinned": True,
            "manual_source": "pin_visual_fallback",
            "tracking_state": "estimated",
            "confidence": estimate["visibility"],
            "point": {"x": estimate["x"], "y": estimate["y"]},
          },
        }
        record_source(joint, "pin_visual_fallback")
        continue
      estimate = estimated_chain_point(joint)
      if estimate is None:
        if not isinstance(landmark.get("visual_fallback"), dict):
          attach_visual_fallback(
            landmark,
            joint,
            current_source_index,
            raw_track=(tracking["tracks"].get(joint) or {}).get(current_source_index),
            reason="long_pin_track_loss",
          )
        record_source(joint, "pin_visual_fallback")
        continue
      landmark["x"] = estimate["x"]
      landmark["y"] = estimate["y"]
      landmark["visibility"] = max(
        min(float(landmark.get("visibility") or 0.0), estimate["visibility"], 0.48),
        PIN_PERSISTENCE_CONFIDENCE,
      )
      landmark["tracking_state"] = "estimated"
      landmark.pop("manual_assisted", None)
      landmark["manual_source"] = "pin_estimated"
      landmark["user_pinned"] = True
      landmark["accepted_source"] = "pin_estimated"
      record_source(joint, "pin_estimated")

  return fused_frames, {
    "used": fused_count > 0,
    "selected_side": selected_side,
    "fused_landmark_count": fused_count,
    "directly_anchored_landmark_count": directly_anchored_count,
    "blended_landmark_count": blended_count,
    "fallback_landmark_count": fallback_count,
    "rejected_track_count": rejected_count,
    "rejection_reasons": rejection_reasons,
    "coverage": tracking.get("coverage") or {},
    "upper_back_anchor_key": UPPER_BACK_ANCHOR,
    "upper_back_anchor_semantics": "upper_back_anchor",
    "fused_anchor_names": list(FUSED_BODY_ANCHORS),
    "upper_back_anchor_used_count": upper_back_anchor_used_count,
    "upper_back_anchor_coverage": (tracking.get("coverage") or {}).get(UPPER_BACK_ANCHOR, 0.0),
    "pin_owned_landmark_count": pin_owned_count,
    "model_divergence_accepted_count": model_divergence_accepted_count,
    "body_barbell_occluder_rejection_count": body_barbell_occluder_rejection_count,
    "body_pin_frames": frame_diagnostics,
    "source_counts": source_counts,
  }


def barbell_track_priors(tracking: dict[str, Any]) -> dict[int, dict[str, float]]:
  return {
    int(source_index): point
    for source_index, point in ((tracking.get("tracks") or {}).get("barbell") or {}).items()
    if float(point.get("confidence") or 0.0) >= MIN_TRACK_CONFIDENCE
  }
