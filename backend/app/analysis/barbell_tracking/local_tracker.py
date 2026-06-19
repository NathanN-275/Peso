from __future__ import annotations

import math
from typing import Any

from .candidate import Candidate
from .constants import (
  LOCAL_FLOW_TEMPLATE_MAX_DISAGREEMENT_RATIO,
  LOCAL_TEMPLATE_MIN_SCORE,
  MIN_LOCAL_FLOW_INLIERS,
  SLEEVE_END_TRACKING_TARGET,
  TRACKING_TARGET,
)
from .geometry import _estimate_collar_from_plate, _point_inside_plate, _validate_collar_geometry
from .selection import _shoulder_relative_offset


def _tracking_patch_bounds(
  center: tuple[float, float],
  *,
  plate_radius: float,
  width: int,
  height: int,
  scale: float = 0.26,
) -> tuple[int, int, int, int]:
  radius = max(int(round(plate_radius * scale)), 10)
  x0 = max(int(round(center[0])) - radius, 0)
  y0 = max(int(round(center[1])) - radius, 0)
  x1 = min(int(round(center[0])) + radius + 1, width)
  y1 = min(int(round(center[1])) + radius + 1, height)
  return x0, y0, x1, y1


def _extract_template(gray: Any, center: tuple[float, float], *, plate_radius: float) -> tuple[Any | None, tuple[int, int, int, int]]:
  height, width = gray.shape[:2]
  bounds = _tracking_patch_bounds(center, plate_radius=plate_radius, width=width, height=height)
  x0, y0, x1, y1 = bounds
  if x1 <= x0 or y1 <= y0:
    return None, bounds

  return gray[y0:y1, x0:x1].copy(), bounds


def _feature_points(cv2: Any, gray: Any, center: tuple[float, float], *, plate_radius: float) -> Any:
  height, width = gray.shape[:2]
  x0, y0, x1, y1 = _tracking_patch_bounds(center, plate_radius=plate_radius, width=width, height=height, scale=0.32)
  if x1 <= x0 or y1 <= y0:
    return None

  patch = gray[y0:y1, x0:x1]
  mask = patch.copy()
  mask[:] = 0
  cv2.circle(
    mask,
    (int(round(center[0] - x0)), int(round(center[1] - y0))),
    max(int(round(plate_radius * 0.26)), 6),
    255,
    -1,
  )
  points = cv2.goodFeaturesToTrack(
    patch,
    maxCorners=32,
    qualityLevel=0.01,
    minDistance=4,
    blockSize=5,
    mask=mask,
  )
  if points is None:
    return None

  points[:, 0, 0] += x0
  points[:, 0, 1] += y0
  return points


def _median_motion(motions: Any) -> tuple[float, float]:
  values = motions.reshape(-1, 2).tolist()
  x_values = sorted(float(item[0]) for item in values)
  y_values = sorted(float(item[1]) for item in values)
  middle = len(values) // 2

  if len(values) % 2 == 1:
    return x_values[middle], y_values[middle]

  return (
    (x_values[middle - 1] + x_values[middle]) / 2,
    (y_values[middle - 1] + y_values[middle]) / 2,
  )


def _make_tracking_lock(
  cv2: Any,
  gray: Any,
  *,
  plate: Candidate,
  collar: tuple[float, float],
  sleeve_direction: tuple[float, float],
  shoulder: tuple[float, float] | None,
  final_bar_point: tuple[float, float] | None = None,
  display_target_point: tuple[float, float] | None = None,
  final_bar_confidence: float = 0.65,
  final_bar_reason: str | None = None,
  target_kind: str = TRACKING_TARGET,
) -> dict[str, Any]:
  tracking_point = final_bar_point or (plate.x, plate.y)
  display_point = display_target_point or tracking_point
  template, template_bounds = _extract_template(gray, tracking_point, plate_radius=plate.radius)
  features = _feature_points(cv2, gray, tracking_point, plate_radius=plate.radius)
  plate_relative_offset = _shoulder_relative_offset(plate, shoulder)
  final_relative_offset = (
    (tracking_point[0] - shoulder[0], tracking_point[1] - shoulder[1])
    if shoulder
    else None
  )
  return {
    "plate": plate,
    "collar": collar,
    "final_bar_point": tracking_point,
    "final_bar_confidence": final_bar_confidence,
    "final_bar_reason": final_bar_reason,
    "tracking_point": tracking_point,
    "display_target_point": display_point,
    "x": plate.x,
    "y": plate.y,
    "collar_dx": collar[0] - plate.x,
    "collar_dy": collar[1] - plate.y,
    "dx": plate_relative_offset[0] if plate_relative_offset else 0.0,
    "dy": plate_relative_offset[1] if plate_relative_offset else 0.0,
    "final_bar_x": tracking_point[0],
    "final_bar_y": tracking_point[1],
    "final_bar_dx": final_relative_offset[0] if final_relative_offset else 0.0,
    "final_bar_dy": final_relative_offset[1] if final_relative_offset else 0.0,
    "radius": plate.radius,
    "shoulder_x": shoulder[0] if shoulder else plate.x,
    "shoulder_y": shoulder[1] if shoulder else plate.y,
    "collar_direction_x": sleeve_direction[0],
    "collar_direction_y": sleeve_direction[1],
    "template": template,
    "template_bounds": template_bounds,
    "features": features,
    "target_kind": target_kind,
  }


def _track_local_patch(
  cv2: Any,
  previous_gray: Any,
  gray: Any,
  lock: dict[str, Any],
  *,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
  predicted_point: tuple[float, float] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
  stats: dict[str, Any] = {
    "local_tracker_type": None,
    "optical_flow_point_count": 0,
    "optical_flow_inlier_count": 0,
    "template_match_score": None,
    "local_tracking_confidence": 0.0,
    "fallback_used": False,
    "collar_rejection_reason": None,
    "prediction_assisted": predicted_point is not None,
  }
  if predicted_point is not None:
    stats["predicted_point_x"] = float(predicted_point[0])
    stats["predicted_point_y"] = float(predicted_point[1])
  old_collar = lock["collar"]
  old_plate = lock["plate"]
  old_tracking_point = lock.get("final_bar_point") or lock.get("tracking_point", (old_plate.x, old_plate.y))
  old_display_point = lock.get("display_target_point", old_tracking_point)
  flow_motion: tuple[float, float] | None = None
  points = lock.get("features")

  if previous_gray is not None and points is not None and len(points) >= 4:
    next_points, status, _ = cv2.calcOpticalFlowPyrLK(previous_gray, gray, points, None)
    if next_points is not None and status is not None:
      good_old = points[status.flatten() == 1]
      good_new = next_points[status.flatten() == 1]
      stats["optical_flow_point_count"] = int(len(points))
      stats["optical_flow_inlier_count"] = int(len(good_new))
      if len(good_new) >= MIN_LOCAL_FLOW_INLIERS:
        motions = good_new.reshape(-1, 2) - good_old.reshape(-1, 2)
        flow_motion = _median_motion(motions)

  template_motion: tuple[float, float] | None = None
  template = lock.get("template")
  if template is not None and float(template.std()) >= 3.0:
    search_radius = max(int(round(old_plate.radius * 0.34)), 18)
    search_center = predicted_point or old_tracking_point
    if predicted_point is not None:
      search_radius = max(
        search_radius,
        int(round(math.hypot(
          predicted_point[0] - old_tracking_point[0],
          predicted_point[1] - old_tracking_point[1],
        ) + old_plate.radius * 0.22)),
      )
    x0 = max(int(round(search_center[0])) - search_radius, 0)
    y0 = max(int(round(search_center[1])) - search_radius, 0)
    x1 = min(int(round(search_center[0])) + search_radius + 1, width)
    y1 = min(int(round(search_center[1])) + search_radius + 1, height)
    search = gray[y0:y1, x0:x1]
    if search.shape[0] >= template.shape[0] and search.shape[1] >= template.shape[1] and float(search.std()) >= 3.0:
      result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
      _, max_score, _, max_loc = cv2.minMaxLoc(result)
      stats["template_match_score"] = float(max_score)
      if max_score >= LOCAL_TEMPLATE_MIN_SCORE:
        template_center = (
          x0 + max_loc[0] + (template.shape[1] / 2),
          y0 + max_loc[1] + (template.shape[0] / 2),
        )
        template_motion = (
          template_center[0] - old_tracking_point[0],
          template_center[1] - old_tracking_point[1],
        )

  if flow_motion is not None and template_motion is not None:
    disagreement = math.hypot(flow_motion[0] - template_motion[0], flow_motion[1] - template_motion[1])
    if predicted_point is not None:
      predicted_motion = (
        predicted_point[0] - old_tracking_point[0],
        predicted_point[1] - old_tracking_point[1],
      )
      flow_prediction_error = math.hypot(
        flow_motion[0] - predicted_motion[0],
        flow_motion[1] - predicted_motion[1],
      )
      template_prediction_error = math.hypot(
        template_motion[0] - predicted_motion[0],
        template_motion[1] - predicted_motion[1],
      )
      stats["flow_prediction_error_px"] = float(flow_prediction_error)
      stats["template_prediction_error_px"] = float(template_prediction_error)
      if (
        template_prediction_error + max(3.0, old_plate.radius * 0.18) < flow_prediction_error
        and float(stats["template_match_score"] or 0.0) >= LOCAL_TEMPLATE_MIN_SCORE
      ):
        motion = template_motion
        stats["local_tracker_type"] = "template_matching"
        stats["local_tracking_confidence"] = max(float(stats["template_match_score"] or 0.0), 0.0)
      else:
        if disagreement > max(3.0, old_plate.radius * LOCAL_FLOW_TEMPLATE_MAX_DISAGREEMENT_RATIO):
          stats["collar_rejection_reason"] = "local_motion_disagreement"
          return None, stats

        motion = (
          (flow_motion[0] * 0.65) + (template_motion[0] * 0.35),
          (flow_motion[1] * 0.65) + (template_motion[1] * 0.35),
        )
        stats["local_tracker_type"] = "klt_optical_flow"
        stats["local_tracking_confidence"] = min(
          1.0,
          (max(float(stats["optical_flow_inlier_count"]), 0.0) / 12.0 * 0.65)
          + (max(float(stats["template_match_score"] or 0.0), 0.0) * 0.35),
        )
    else:
      if disagreement > max(3.0, old_plate.radius * LOCAL_FLOW_TEMPLATE_MAX_DISAGREEMENT_RATIO):
        stats["collar_rejection_reason"] = "local_motion_disagreement"
        return None, stats

      motion = (
        (flow_motion[0] * 0.65) + (template_motion[0] * 0.35),
        (flow_motion[1] * 0.65) + (template_motion[1] * 0.35),
      )
      stats["local_tracker_type"] = "klt_optical_flow"
      stats["local_tracking_confidence"] = min(
        1.0,
        (max(float(stats["optical_flow_inlier_count"]), 0.0) / 12.0 * 0.65)
        + (max(float(stats["template_match_score"] or 0.0), 0.0) * 0.35),
      )
  elif flow_motion is not None:
    if predicted_point is not None:
      predicted_motion = (
        predicted_point[0] - old_tracking_point[0],
        predicted_point[1] - old_tracking_point[1],
      )
      stats["flow_prediction_error_px"] = float(
        math.hypot(flow_motion[0] - predicted_motion[0], flow_motion[1] - predicted_motion[1])
      )
    motion = flow_motion
    stats["local_tracker_type"] = "klt_optical_flow"
    stats["local_tracking_confidence"] = min(
      1.0,
      max(float(stats["optical_flow_inlier_count"]), 0.0) / 12.0,
    )
  elif template_motion is not None:
    if predicted_point is not None:
      predicted_motion = (
        predicted_point[0] - old_tracking_point[0],
        predicted_point[1] - old_tracking_point[1],
      )
      stats["template_prediction_error_px"] = float(
        math.hypot(template_motion[0] - predicted_motion[0], template_motion[1] - predicted_motion[1])
      )
    motion = template_motion
    stats["local_tracker_type"] = "template_matching"
    stats["local_tracking_confidence"] = max(float(stats["template_match_score"] or 0.0), 0.0)
  else:
    stats["collar_rejection_reason"] = "local_tracking_failed"
    return None, stats

  motion_limit = max(width, height) * 0.12
  if predicted_point is not None:
    predicted_motion_distance = math.hypot(
      predicted_point[0] - old_tracking_point[0],
      predicted_point[1] - old_tracking_point[1],
    )
    prediction_error = math.hypot(
      (old_tracking_point[0] + motion[0]) - predicted_point[0],
      (old_tracking_point[1] + motion[1]) - predicted_point[1],
    )
    stats["prediction_error_px"] = float(prediction_error)
    if prediction_error <= max(4.0, old_plate.radius * 0.22):
      motion_limit = max(motion_limit, predicted_motion_distance + old_plate.radius * 0.35)
  if math.hypot(motion[0], motion[1]) > motion_limit:
    stats["collar_rejection_reason"] = "absolute_jump"
    return None, stats

  tracked_plate = Candidate(
    x=old_plate.x + motion[0],
    y=old_plate.y + motion[1],
    radius=old_plate.radius,
    confidence=old_plate.confidence,
  )
  tracked_final_bar_point = (
    old_tracking_point[0] + motion[0],
    old_tracking_point[1] + motion[1],
  )
  tracked_display_point = (
    old_display_point[0] + motion[0],
    old_display_point[1] + motion[1],
  )
  target_kind = lock.get("target_kind", TRACKING_TARGET)
  if (
    target_kind != SLEEVE_END_TRACKING_TARGET
    and not _point_inside_plate(tracked_final_bar_point, plate=tracked_plate, max_radius_ratio=0.58)
  ):
    stats["collar_rejection_reason"] = "hub_left_plate_region"
    return None, stats

  if target_kind == SLEEVE_END_TRACKING_TARGET:
    sleeve_direction = (
      float(lock.get("collar_direction_x", 1.0)),
      float(lock.get("collar_direction_y", 0.0)),
    )
    tracked_collar = tracked_final_bar_point
    predicted_collar = tracked_final_bar_point
    final_collar = tracked_final_bar_point
    stats["fallback_used"] = False
  else:
    predicted_collar, sleeve_direction = _estimate_collar_from_plate(
      tracked_plate,
      shoulder=shoulder,
      width=width,
      height=height,
      previous=lock,
    )
    tracked_collar = (old_collar[0] + motion[0], old_collar[1] + motion[1])
    reason = _validate_collar_geometry(tracked_collar, plate=tracked_plate, sleeve_direction=sleeve_direction, previous=lock)
    stats["fallback_used"] = reason is not None
    final_collar = predicted_collar if reason else (
      (predicted_collar[0] * 0.7) + (tracked_collar[0] * 0.3),
      (predicted_collar[1] * 0.7) + (tracked_collar[1] * 0.3),
    )
    final_reason = _validate_collar_geometry(final_collar, plate=tracked_plate, sleeve_direction=sleeve_direction, previous=lock)
    if final_reason:
      stats["collar_rejection_reason"] = final_reason
      return None, stats

  if shoulder:
    previous_shoulder_x = lock.get("shoulder_x")
    previous_shoulder_y = lock.get("shoulder_y")
    if previous_shoulder_x is not None and previous_shoulder_y is not None:
      shoulder_motion = math.hypot(shoulder[0] - previous_shoulder_x, shoulder[1] - previous_shoulder_y)
      point_motion = math.hypot(
        tracked_final_bar_point[0] - old_tracking_point[0],
        tracked_final_bar_point[1] - old_tracking_point[1],
      )
      if shoulder_motion >= 6.0 and point_motion <= 1.0:
        stats["collar_rejection_reason"] = "stationary_hardware_like"
        return None, stats

  new_lock = _make_tracking_lock(
    cv2,
    gray,
    plate=tracked_plate,
    collar=final_collar,
    sleeve_direction=sleeve_direction,
    final_bar_point=tracked_final_bar_point,
    display_target_point=tracked_display_point,
    final_bar_confidence=float(lock.get("final_bar_confidence", 0.65)),
    final_bar_reason=lock.get("final_bar_reason"),
    shoulder=shoulder,
    target_kind=target_kind,
  )
  new_lock["predicted_collar"] = predicted_collar
  new_lock["refined_collar"] = final_collar
  new_lock["collar_geometry_valid"] = True
  new_lock["fallback_used"] = stats["fallback_used"]
  return new_lock, stats
