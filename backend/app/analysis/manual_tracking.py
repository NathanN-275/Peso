from __future__ import annotations

import copy
import logging
import math
from itertools import product
from statistics import median
from typing import Any


TRACKING_SETUP_VERSION = 1
BODY_ANCHORS = ("shoulder", "hip", "knee", "ankle")
UPPER_BACK_ANCHOR = "shoulder"
FUSED_BODY_ANCHORS = ("hip", "knee", "ankle")
ALL_ANCHORS = (*BODY_ANCHORS, "barbell")
MIN_TRACK_CONFIDENCE = 0.42
MIN_MODEL_VISIBILITY = 0.15
MAX_JOINT_DISPLACEMENT_PX = 15

logger = logging.getLogger(__name__)


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

  shoulder = normalized_anchors["shoulder"]
  hip = normalized_anchors["hip"]
  knee = normalized_anchors["knee"]
  ankle = normalized_anchors["ankle"]
  if not (shoulder["y"] < hip["y"] < ankle["y"]):
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
  landmarks = reference_frame.get("landmarks") or {}
  scores: dict[str, float] = {}
  for side in ("left", "right"):
    score = 0.0
    for joint in BODY_ANCHORS:
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
) -> tuple[tuple[float, float] | None, float]:
  height, width = gray.shape[:2]
  max_dimension = max(width, height)
  patch_radius = max(int(round(max_dimension * 0.016)), 8)
  search_radius = max(int(round(max_dimension * 0.055)), 24)
  center_x = int(round(point[0]))
  center_y = int(round(point[1]))
  template_x0 = center_x - patch_radius
  template_y0 = center_y - patch_radius
  template_x1 = center_x + patch_radius + 1
  template_y1 = center_y + patch_radius + 1
  if template_x0 < 0 or template_y0 < 0 or template_x1 > width or template_y1 > height:
    return None, 0.0
  template = previous_gray[template_y0:template_y1, template_x0:template_x1]
  search_x0 = max(center_x - search_radius - patch_radius, 0)
  search_y0 = max(center_y - search_radius - patch_radius, 0)
  search_x1 = min(center_x + search_radius + patch_radius + 1, width)
  search_y1 = min(center_y + search_radius + patch_radius + 1, height)
  search = gray[search_y0:search_y1, search_x0:search_x1]
  if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
    return None, 0.0
  scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
  _, score, _, location = cv2.minMaxLoc(scores)
  if not math.isfinite(float(score)) or float(score) < 0.54:
    return None, 0.0
  matched_center = (
    float(search_x0 + location[0] + patch_radius),
    float(search_y0 + location[1] + patch_radius),
  )
  if math.hypot(matched_center[0] - point[0], matched_center[1] - point[1]) > search_radius:
    return None, 0.0
  return matched_center, float(score)


def _track_step(
  cv2: Any,
  previous_gray: Any,
  gray: Any,
  point: tuple[float, float],
  *,
  barbell: bool = False,
) -> tuple[tuple[float, float] | None, float, dict[str, float]]:
  import numpy as np

  template_point, template_score = (
    _track_template(cv2, previous_gray, gray, point)
    if barbell
    else (None, 0.0)
  )

  def template_fallback() -> tuple[tuple[float, float] | None, float, dict[str, float]]:
    if template_point is None:
      return None, 0.0, {}
    return template_point, min(template_score * 0.82, 0.72), {
      "template_score": template_score,
      "template_fallback": 1.0,
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
    max_jump = max(gray.shape[:2]) * 0.10
    height, width = gray.shape[:2]
    if math.hypot(dx, dy) > max_jump or not (
      0 <= next_point[0] < width and 0 <= next_point[1] < height
    ):
      return None, 0.0, {}
    confidence = min(1.0, (float(inlier_mask.sum()) / max(len(previous_points), 1)) * 1.15)
    return next_point, confidence, {
      "tracked_features": float(len(previous_points)),
      "median_back_error": float(median(float(value) for value in back_error[inlier_mask])),
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
) -> dict[int, dict[str, Any]]:
  if not ordered_indices:
    return {}
  tracks = {
    ordered_indices[0]: {"x": initial_point[0], "y": initial_point[1], "confidence": 1.0}
  }
  current_point = initial_point
  previous_index = ordered_indices[0]
  reference_index = ordered_indices[0]
  for frame_index in ordered_indices[1:]:
    next_point, confidence, diagnostics = _track_step(
      cv2,
      frames[previous_index],
      frames[frame_index],
      current_point,
      barbell=barbell,
    )
    if next_point is None:
      break

    proposed_displacement_px = math.hypot(
      next_point[0] - current_point[0],
      next_point[1] - current_point[1],
    )
    if not barbell and proposed_displacement_px > MAX_JOINT_DISPLACEMENT_PX:
      logger.debug(
        "Rejected manual %s track at frame %s: %.2f px exceeds %.2f px velocity cap",
        joint_name or "unknown",
        frame_index,
        proposed_displacement_px,
        MAX_JOINT_DISPLACEMENT_PX,
      )
      next_point = current_point
      confidence *= 0.55
      diagnostics = {
        **diagnostics,
        "velocity_capped": 1.0,
        "velocity_cap_reused_previous": 1.0,
        "velocity_cap_distance_px": proposed_displacement_px,
        "proposed_displacement_px": proposed_displacement_px,
        "max_joint_displacement_px": MAX_JOINT_DISPLACEMENT_PX,
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
      **({"direction_agreement_px": agreement_px} if agreement_px is not None else {}),
    }
    current_point = next_point
    previous_index = frame_index
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
    if source_index == reference_index or point.get("velocity_cap_reused_previous"):
      smoothed[source_index] = dict(point)
      continue
    neighbor_indices = ordered_indices[max(position - 1, 0):min(position + 2, len(ordered_indices))]
    neighbors = [tracks[index] for index in neighbor_indices]
    smoothed[source_index] = {
      **point,
      "x": float(median(float(item["x"]) for item in neighbors)),
      "y": float(median(float(item["y"]) for item in neighbors)),
      "confidence": float(point["confidence"]),
    }
  return smoothed


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

  source_indices = sorted({int(frame["source_frame_index"]) for frame in pose_frames})
  if not source_indices or width <= 0 or height <= 0:
    return {
      "tracks": {},
      "reference_source_index": None,
      "coverage": {name: 0.0 for name in ALL_ANCHORS},
      "velocity_cap_count": 0,
      "velocity_cap_counts": {name: 0 for name in BODY_ANCHORS},
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
      "velocity_cap_counts": {name: 0 for name in BODY_ANCHORS},
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
      "velocity_cap_counts": {name: 0 for name in BODY_ANCHORS},
    }

  reference_position = available_indices.index(reference_index)
  tracks: dict[str, dict[int, dict[str, float]]] = {}
  velocity_cap_counts = {name: 0 for name in BODY_ANCHORS}
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
    )
    backward = _track_direction(
      cv2,
      gray_frames,
      list(reversed(available_indices[:reference_position + 1])),
      initial_point,
      barbell=is_barbell,
      joint_name=None if is_barbell else name,
    )
    combined = {**backward, **forward}
    if not is_barbell:
      velocity_cap_counts[name] = sum(
        1 for point in combined.values() if point.get("velocity_capped")
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

  coverage = {
    name: round(len(anchor_tracks) / max(len(available_indices), 1), 3)
    for name, anchor_tracks in tracks.items()
  }
  return {
    "tracks": tracks,
    "reference_source_index": reference_index,
    "coverage": coverage,
    "velocity_cap_count": sum(velocity_cap_counts.values()),
    "velocity_cap_counts": velocity_cap_counts,
  }


def fuse_manual_body_tracks(
  pose_frames: list[dict[str, Any]],
  *,
  setup: dict[str, Any],
  tracking: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  base_diagnostics = {
    "upper_back_anchor_key": UPPER_BACK_ANCHOR,
    "upper_back_anchor_semantics": "upper_back_anchor",
    "fused_anchor_names": list(FUSED_BODY_ANCHORS),
    "upper_back_anchor_used_count": 0,
    "pin_owned_landmark_count": 0,
    "model_divergence_accepted_count": 0,
    "body_pin_frames": [],
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
  rejection_reasons: dict[str, int] = {}
  manual_active = {joint: False for joint in FUSED_BODY_ANCHORS}
  manual_has_activated = {joint: False for joint in FUSED_BODY_ANCHORS}
  manual_reentry_streak = {joint: 0 for joint in FUSED_BODY_ANCHORS}
  previous_manual_points: dict[str, dict[str, float]] = {}
  previous_valid_chain: dict[str, dict[str, float]] | None = None
  valid_chains: dict[int, dict[str, dict[str, float]]] = {}
  unresolved_frame_positions: list[int] = []
  frame_diagnostics: list[dict[str, Any]] = []
  torso_scale = max(_point_distance(setup["anchors"]["shoulder"], setup["anchors"]["hip"]), 0.08)
  reference_lengths = {
    "torso": _point_distance(setup["anchors"]["shoulder"], setup["anchors"]["hip"]),
    "thigh": _point_distance(setup["anchors"]["hip"], setup["anchors"]["knee"]),
    "shin": _point_distance(setup["anchors"]["knee"], setup["anchors"]["ankle"]),
  }

  def reject(joint: str, reason: str) -> None:
    nonlocal fallback_count, rejected_count
    rejected_count += 1
    fallback_count += 1
    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    manual_active[joint] = False
    manual_reentry_streak[joint] = 0

  def chain_lengths(chain: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
      "torso": _point_distance(chain["shoulder"], chain["hip"]),
      "thigh": _point_distance(chain["hip"], chain["knee"]),
      "shin": _point_distance(chain["knee"], chain["ankle"]),
    }

  def chain_is_valid(chain: dict[str, dict[str, float]]) -> bool:
    if chain["hip"]["y"] < chain["shoulder"]["y"] - 0.10:
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

  for frame_position, frame in enumerate(fused_frames):
    source_index = int(frame.get("source_frame_index", -1))
    landmarks = frame.get("landmarks") or {}
    model_upper_back = _upper_back_proxy(landmarks, selected_side)
    raw_model_shoulder = _landmark_point(landmarks, selected_side, "shoulder")
    upper_back_track = (tracking["tracks"].get(UPPER_BACK_ANCHOR) or {}).get(source_index)
    upper_back_point = model_upper_back
    upper_back_source = "automatic"
    if (
      upper_back_track
      and float(upper_back_track.get("confidence") or 0.0) >= MIN_TRACK_CONFIDENCE
    ):
      upper_back_point = {
        "x": float(upper_back_track["x"]),
        "y": float(upper_back_track["y"]),
        "visibility": min(float(upper_back_track.get("confidence") or 0.0), 0.92),
      }
      upper_back_source = (
        "reference"
        if upper_back_track.get("tracking_state") == "reference"
        else "pin_guided"
      )
      upper_back_anchor_used_count += 1

    frame_diagnostic: dict[str, Any] | None = None
    if len(frame_diagnostics) < 120:
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
    available_points: dict[str, dict[str, float]] = {}
    for joint in FUSED_BODY_ANCHORS:
      track = (tracking["tracks"].get(joint) or {}).get(source_index)
      if track and float(track.get("confidence") or 0.0) >= MIN_TRACK_CONFIDENCE:
        available_points[joint] = track

    options_by_joint: dict[str, list[dict[str, Any]]] = {}
    for joint in FUSED_BODY_ANCHORS:
      landmark = landmarks.get(f"{selected_side}_{joint}")
      if not landmark:
        reject(joint, "missing_pose_landmark")
        options_by_joint[joint] = []
        continue
      model_visibility = float(landmark.get("visibility") or 0.0)
      model_point = {"x": float(landmark["x"]), "y": float(landmark["y"])}
      options_by_joint[joint] = [
        {
          "source": "automatic",
          "point": model_point,
          "visibility": model_visibility,
          "score": 0.25 + (model_visibility * 0.35),
        }
      ]
      track = available_points.get(joint)
      if not track:
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
            "raw_pin": {
              "x": round(float(track["x"]), 4),
              "y": round(float(track["y"]), 4),
              "confidence": round(float(track.get("confidence") or 0.0), 3),
            },
            "residual": round(_point_distance(track, model_point), 4),
            "rejection_reason": "manual_reentry_wait",
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
            "raw_pin": {
              "x": round(float(track["x"]), 4),
              "y": round(float(track["y"]), 4),
              "confidence": round(track_confidence, 3),
            },
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
            "raw_pin": {
              "x": round(float(track["x"]), 4),
              "y": round(float(track["y"]), 4),
              "confidence": round(track_confidence, 3),
            },
            "residual": round(model_distance, 4),
            "rejection_reason": "temporal_jump",
          }
        continue

      if force_reference_anchor:
        manual_weight = 1.0
        manual_source = "reference_pin"
        tracking_state = "reference"
      else:
        manual_weight = 1.0
        manual_source = "pin_guided"
        tracking_state = "guided"
      manual_visibility = max(model_visibility, min(track_confidence, 0.92))
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
          "raw_pin": {
            "x": round(float(track["x"]), 4),
            "y": round(float(track["y"]), 4),
            "confidence": round(track_confidence, 3),
          },
          "residual": round(model_distance, 4),
          "rejection_reason": None,
          "pose_divergence_accepted": accept_pose_divergence and model_distance > max_model_distance,
        }

    if frame_diagnostic is not None:
      frame_diagnostics.append(frame_diagnostic)

    if upper_back_point is None or any(not options_by_joint.get(joint) for joint in FUSED_BODY_ANCHORS):
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
      unresolved_frame_positions.append(frame_position)
      for joint in available_points:
        reject(joint, "invalid_body_geometry")
      continue

    _score, selected_options = max(combinations, key=lambda item: item[0])
    selected_chain: dict[str, dict[str, float]] = {}
    selected_chain[UPPER_BACK_ANCHOR] = dict(upper_back_point)
    for joint, option in zip(FUSED_BODY_ANCHORS, selected_options):
      landmark = landmarks[f"{selected_side}_{joint}"]
      selected_chain[joint] = dict(option["point"])
      landmark["x"] = float(option["point"]["x"])
      landmark["y"] = float(option["point"]["y"])
      landmark["visibility"] = float(option["visibility"])
      if option["source"] == "automatic":
        landmark["tracking_state"] = "automatic"
        landmark.pop("manual_assisted", None)
        landmark.pop("manual_source", None)
        landmark.pop("manual_weight", None)
        if any(
          candidate["source"] != "automatic"
          for candidate in options_by_joint[joint]
        ):
          reject(joint, "whole_chain_fallback")
        continue

      manual_active[joint] = True
      manual_has_activated[joint] = True
      manual_reentry_streak[joint] = 0
      landmark["manual_assisted"] = True
      landmark["manual_source"] = option["source"]
      landmark["manual_weight"] = round(float(option["manual_weight"]), 3)
      landmark["tracking_state"] = option["tracking_state"]
      if option.get("pose_divergence_accepted"):
        landmark["pose_divergence_accepted"] = True
      previous_manual_points[joint] = {
        "x": float(option["track"]["x"]),
        "y": float(option["track"]["y"]),
      }
      fused_count += 1
      pin_owned_count += 1
      if option["source"] == "reference_pin":
        directly_anchored_count += 1
      else:
        blended_count += 1
    valid_chains[frame_position] = selected_chain
    previous_valid_chain = selected_chain

  for frame_position in unresolved_frame_positions:
    landmarks = fused_frames[frame_position].get("landmarks") or {}
    previous_positions = [position for position in valid_chains if position < frame_position]
    following_positions = [position for position in valid_chains if position > frame_position]
    previous_position = max(previous_positions) if previous_positions else None
    following_position = min(following_positions) if following_positions else None
    for joint in FUSED_BODY_ANCHORS:
      landmark = landmarks.get(f"{selected_side}_{joint}")
      if not landmark:
        continue
      if previous_position is not None and following_position is not None:
        span = following_position - previous_position
        weight = (frame_position - previous_position) / max(span, 1)
        previous_point = valid_chains[previous_position][joint]
        following_point = valid_chains[following_position][joint]
        landmark["x"] = previous_point["x"] + ((following_point["x"] - previous_point["x"]) * weight)
        landmark["y"] = previous_point["y"] + ((following_point["y"] - previous_point["y"]) * weight)
      elif previous_position is not None:
        landmark.update(valid_chains[previous_position][joint])
      elif following_position is not None:
        landmark.update(valid_chains[following_position][joint])
      landmark["visibility"] = min(float(landmark.get("visibility") or 0.0), 0.48)
      landmark["tracking_state"] = "estimated"

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
    "body_pin_frames": frame_diagnostics,
  }


def barbell_track_priors(tracking: dict[str, Any]) -> dict[int, dict[str, float]]:
  return {
    int(source_index): point
    for source_index, point in ((tracking.get("tracks") or {}).get("barbell") or {}).items()
    if float(point.get("confidence") or 0.0) >= MIN_TRACK_CONFIDENCE
  }
