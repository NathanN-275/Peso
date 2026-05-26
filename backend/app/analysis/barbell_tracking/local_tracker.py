from __future__ import annotations

import math
from typing import Any

from .candidate import Candidate
from .geometry import _estimate_collar_from_plate, _validate_collar_geometry
from .selection import _shoulder_relative_offset


def _tracking_patch_bounds(
  center: tuple[float, float],
  *,
  plate_radius: float,
  width: int,
  height: int,
  scale: float = 0.45,
) -> tuple[int, int, int, int]:
  radius = max(int(round(plate_radius * scale)), 14)
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
  x0, y0, x1, y1 = _tracking_patch_bounds(center, plate_radius=plate_radius, width=width, height=height, scale=0.55)
  if x1 <= x0 or y1 <= y0:
    return None

  mask = None
  patch = gray[y0:y1, x0:x1]
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


def _make_tracking_lock(
  cv2: Any,
  gray: Any,
  *,
  plate: Candidate,
  collar: tuple[float, float],
  sleeve_direction: tuple[float, float],
  shoulder: tuple[float, float] | None,
) -> dict[str, Any]:
  tracking_point = (plate.x, plate.y)
  template, template_bounds = _extract_template(gray, tracking_point, plate_radius=plate.radius)
  features = _feature_points(cv2, gray, tracking_point, plate_radius=plate.radius)
  relative_offset = _shoulder_relative_offset(plate, shoulder)
  return {
    "plate": plate,
    "collar": collar,
    "tracking_point": tracking_point,
    "x": plate.x,
    "y": plate.y,
    "collar_dx": collar[0] - plate.x,
    "collar_dy": collar[1] - plate.y,
    "dx": relative_offset[0] if relative_offset else 0.0,
    "dy": relative_offset[1] if relative_offset else 0.0,
    "radius": plate.radius,
    "shoulder_x": shoulder[0] if shoulder else plate.x,
    "shoulder_y": shoulder[1] if shoulder else plate.y,
    "collar_direction_x": sleeve_direction[0],
    "collar_direction_y": sleeve_direction[1],
    "template": template,
    "template_bounds": template_bounds,
    "features": features,
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
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
  stats: dict[str, Any] = {
    "local_tracker_type": None,
    "optical_flow_point_count": 0,
    "optical_flow_inlier_count": 0,
    "template_match_score": None,
    "fallback_used": False,
    "collar_rejection_reason": None,
  }
  old_collar = lock["collar"]
  old_plate = lock["plate"]
  old_tracking_point = lock.get("tracking_point", (old_plate.x, old_plate.y))
  flow_motion: tuple[float, float] | None = None
  points = lock.get("features")

  if previous_gray is not None and points is not None and len(points) >= 4:
    next_points, status, _ = cv2.calcOpticalFlowPyrLK(previous_gray, gray, points, None)
    if next_points is not None and status is not None:
      good_old = points[status.flatten() == 1]
      good_new = next_points[status.flatten() == 1]
      stats["optical_flow_point_count"] = int(len(points))
      stats["optical_flow_inlier_count"] = int(len(good_new))
      if len(good_new) >= 4:
        motions = good_new.reshape(-1, 2) - good_old.reshape(-1, 2)
        median_motion = motions[len(motions) // 2] if len(motions) == 1 else sorted(motions.tolist(), key=lambda item: item[0])[len(motions) // 2]
        flow_motion = (float(median_motion[0]), float(median_motion[1]))

  template_motion: tuple[float, float] | None = None
  template = lock.get("template")
  if template is not None and float(template.std()) >= 3.0:
    search_radius = max(int(round(old_plate.radius * 0.7)), 24)
    x0 = max(int(round(old_tracking_point[0])) - search_radius, 0)
    y0 = max(int(round(old_tracking_point[1])) - search_radius, 0)
    x1 = min(int(round(old_tracking_point[0])) + search_radius + 1, width)
    y1 = min(int(round(old_tracking_point[1])) + search_radius + 1, height)
    search = gray[y0:y1, x0:x1]
    if search.shape[0] >= template.shape[0] and search.shape[1] >= template.shape[1] and float(search.std()) >= 3.0:
      result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
      _, max_score, _, max_loc = cv2.minMaxLoc(result)
      stats["template_match_score"] = float(max_score)
      if max_score >= 0.48:
        template_center = (
          x0 + max_loc[0] + (template.shape[1] / 2),
          y0 + max_loc[1] + (template.shape[0] / 2),
        )
        template_motion = (
          template_center[0] - old_tracking_point[0],
          template_center[1] - old_tracking_point[1],
        )

  if flow_motion is not None and template_motion is not None:
    motion = (
      (flow_motion[0] * 0.65) + (template_motion[0] * 0.35),
      (flow_motion[1] * 0.65) + (template_motion[1] * 0.35),
    )
    stats["local_tracker_type"] = "klt_optical_flow"
  elif flow_motion is not None:
    motion = flow_motion
    stats["local_tracker_type"] = "klt_optical_flow"
  elif template_motion is not None:
    motion = template_motion
    stats["local_tracker_type"] = "template_matching"
  else:
    stats["collar_rejection_reason"] = "local_tracking_failed"
    return None, stats

  if math.hypot(motion[0], motion[1]) > max(width, height) * 0.12:
    stats["collar_rejection_reason"] = "absolute_jump"
    return None, stats

  tracked_plate = Candidate(
    x=old_plate.x + motion[0],
    y=old_plate.y + motion[1],
    radius=old_plate.radius,
    confidence=old_plate.confidence,
  )
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
      plate_motion = math.hypot(tracked_plate.x - old_plate.x, tracked_plate.y - old_plate.y)
      if shoulder_motion >= 4.0 and plate_motion <= max(1.5, shoulder_motion * 0.35):
        stats["collar_rejection_reason"] = "stationary_hardware_like"
        return None, stats

  new_lock = _make_tracking_lock(
    cv2,
    gray,
    plate=tracked_plate,
    collar=final_collar,
    sleeve_direction=sleeve_direction,
    shoulder=shoulder,
  )
  new_lock["predicted_collar"] = predicted_collar
  new_lock["refined_collar"] = final_collar
  new_lock["collar_geometry_valid"] = True
  new_lock["fallback_used"] = stats["fallback_used"]
  return new_lock, stats
