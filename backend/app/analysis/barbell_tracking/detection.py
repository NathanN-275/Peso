from __future__ import annotations

import math
from typing import Any

from .candidate import Candidate
from .constants import MAX_CANDIDATES_PER_FRAME, MAX_DETECTION_CROP_WIDTH

WRIST_REJECTION_RADIUS_PX = 40.0
VISIBLE_LANDMARK_THRESHOLD = 0.35


def _candidate_in_bounds(candidate: Candidate, bounds: tuple[float, float, float, float]) -> bool:
  min_x, min_y, max_x, max_y = bounds
  return min_x <= candidate.x <= max_x and min_y <= candidate.y <= max_y


def _detect_circle_candidates(
  cv2: Any,
  frame: Any,
  *,
  offset_x: float = 0.0,
  offset_y: float = 0.0,
  radius_reference: int | None = None,
) -> list[Candidate]:
  height, width = frame.shape[:2]
  min_dimension = max(radius_reference or min(width, height), 1)
  gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
  gray = cv2.GaussianBlur(gray, (9, 9), 1.6)
  circles = cv2.HoughCircles(
    gray,
    cv2.HOUGH_GRADIENT,
    dp=1.2,
    minDist=max(20, int(min_dimension * 0.14)),
    param1=80,
    param2=18,
    minRadius=max(8, int(min_dimension * 0.025)),
    maxRadius=max(12, int(min_dimension * 0.34)),
  )

  if circles is None:
    return []

  return [
    Candidate(
      x=float(circle[0]) + offset_x,
      y=float(circle[1]) + offset_y,
      radius=float(circle[2]),
      confidence=0.62,
    )
    for circle in circles[0]
  ]


def _visible_landmark_point(
  landmarks: dict[str, dict[str, float]] | None,
  name: str,
  *,
  width: int,
  height: int,
) -> tuple[float, float] | None:
  point = (landmarks or {}).get(name)
  if not point or float(point.get("visibility", 0.0) or 0.0) < VISIBLE_LANDMARK_THRESHOLD:
    return None

  return float(point.get("x", 0.0)) * width, float(point.get("y", 0.0)) * height


def _mean_landmark_point(
  landmarks: dict[str, dict[str, float]] | None,
  names: tuple[str, ...],
  *,
  width: int,
  height: int,
) -> tuple[float, float] | None:
  points = [
    point
    for name in names
    if (point := _visible_landmark_point(landmarks, name, width=width, height=height)) is not None
  ]
  if not points:
    return None

  return (
    sum(point[0] for point in points) / len(points),
    sum(point[1] for point in points) / len(points),
  )


def _wrist_points_from_landmarks(
  landmarks: dict[str, dict[str, float]] | None,
  *,
  width: int,
  height: int,
) -> list[tuple[float, float]]:
  return [
    point
    for name in ("left_wrist", "right_wrist")
    if (point := _visible_landmark_point(landmarks, name, width=width, height=height)) is not None
  ]


def _crop_bounds_from_landmarks(
  landmarks: dict[str, dict[str, float]] | None,
  *,
  width: int,
  height: int,
  fallback_bounds: tuple[float, float, float, float],
) -> dict[str, Any]:
  shoulder = _mean_landmark_point(landmarks, ("left_shoulder", "right_shoulder"), width=width, height=height)
  return _crop_bounds_from_anchor(width=width, height=height, bounds=fallback_bounds, shoulder=shoulder)


def _crop_bounds_from_anchor(
  *,
  width: int,
  height: int,
  bounds: tuple[float, float, float, float],
  shoulder: tuple[float, float] | None,
) -> dict[str, Any]:
  min_x, min_y, max_x, max_y = bounds
  anchor_label = "shoulder" if shoulder else "pose_bounds"
  if shoulder:
    shoulder_x, shoulder_y = shoulder
    x_margin = width * 0.34
    y_margin_above = height * 0.24
    y_margin_below = height * 0.2
    crop_min_x = shoulder_x - x_margin
    crop_max_x = shoulder_x + x_margin
    crop_min_y = shoulder_y - y_margin_above
    crop_max_y = shoulder_y + y_margin_below
  else:
    crop_min_x = min_x
    crop_min_y = min_y
    crop_max_x = max_x
    crop_max_y = max_y

  x0 = max(int(math.floor(crop_min_x)), 0)
  y0 = max(int(math.floor(crop_min_y)), 0)
  x1 = min(int(math.ceil(crop_max_x)), width)
  y1 = min(int(math.ceil(crop_max_y)), height)
  if x1 <= x0 or y1 <= y0:
    x0, y0, x1, y1 = 0, 0, width, height

  return {
    "anchor_landmark": anchor_label,
    "anchor_point": shoulder,
    "crop_bounds": (float(x0), float(y0), float(x1), float(y1)),
  }


def _detection_crop(
  cv2: Any,
  frame: Any,
  bounds: tuple[float, float, float, float],
  *,
  shoulder: tuple[float, float] | None = None,
) -> tuple[Any, float, float, float, float, tuple[float, float, float, float], str]:
  height, width = frame.shape[:2]
  crop_info = _crop_bounds_from_anchor(width=width, height=height, bounds=bounds, shoulder=shoulder)
  crop_bounds = crop_info["crop_bounds"]
  anchor_label = crop_info["anchor_landmark"]
  x0, y0, x1, y1 = (int(value) for value in crop_bounds)

  if x1 <= x0 or y1 <= y0:
    return frame, 0.0, 0.0, float(width), float(height), (0.0, 0.0, float(width), float(height)), anchor_label

  crop = frame[y0:y1, x0:x1]
  crop_width = crop.shape[1]
  crop_height = crop.shape[0]
  if crop_width > MAX_DETECTION_CROP_WIDTH:
    scale = MAX_DETECTION_CROP_WIDTH / crop_width
    resized_width = MAX_DETECTION_CROP_WIDTH
    resized_height = max(int(round(crop_height * scale)), 1)
    crop = cv2.resize(crop, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    return crop, float(x0), float(y0), 1 / scale, 1 / scale, crop_bounds, anchor_label

  return crop, float(x0), float(y0), 1.0, 1.0, crop_bounds, anchor_label


def _near_wrist(candidate: Candidate, wrist_points: list[tuple[float, float]]) -> bool:
  return any(
    math.hypot(candidate.x - wrist_x, candidate.y - wrist_y) <= WRIST_REJECTION_RADIUS_PX
    for wrist_x, wrist_y in wrist_points
  )


def _filter_wrist_candidates(
  candidates: list[Candidate],
  landmarks: dict[str, dict[str, float]] | None,
  *,
  width: int,
  height: int,
) -> tuple[list[Candidate], int]:
  wrist_points = _wrist_points_from_landmarks(landmarks, width=width, height=height)
  wrist_rejected_count = 0
  filtered: list[Candidate] = []
  for candidate in candidates:
    if _near_wrist(candidate, wrist_points):
      wrist_rejected_count += 1
    else:
      filtered.append(candidate)
  return filtered, wrist_rejected_count


def _detect_crop_candidates(
  cv2: Any,
  frame: Any,
  bounds: tuple[float, float, float, float],
  *,
  landmarks: dict[str, dict[str, float]] | None = None,
  shoulder: tuple[float, float] | None = None,
  wrist_points: list[tuple[float, float]] | None = None,
) -> tuple[list[Candidate], int, int, dict[str, Any]]:
  height, width = frame.shape[:2]
  if landmarks is not None:
    crop_info = _crop_bounds_from_landmarks(landmarks, width=width, height=height, fallback_bounds=bounds)
    shoulder = crop_info["anchor_point"]

  crop, offset_x, offset_y, scale_x, scale_y, crop_bounds, anchor_label = _detection_crop(
    cv2,
    frame,
    bounds,
    shoulder=shoulder,
  )
  radius_reference = int(round(min(frame.shape[:2]) / ((scale_x + scale_y) / 2)))
  candidates = _detect_circle_candidates(cv2, crop, radius_reference=radius_reference)
  crop_height, crop_width = crop.shape[:2]
  mapped = [
    Candidate(
      x=(candidate.x * scale_x) + offset_x,
      y=(candidate.y * scale_y) + offset_y,
      radius=candidate.radius * ((scale_x + scale_y) / 2),
      confidence=candidate.confidence,
    )
    for candidate in candidates
  ]
  if landmarks is not None:
    mapped, wrist_rejected_count = _filter_wrist_candidates(mapped, landmarks, width=width, height=height)
  else:
    wrist_points = wrist_points or []
    wrist_rejected_count = 0
    filtered: list[Candidate] = []
    for candidate in mapped:
      if _near_wrist(candidate, wrist_points):
        wrist_rejected_count += 1
      else:
        filtered.append(candidate)
    mapped = filtered
  mapped.sort(key=lambda candidate: candidate.radius, reverse=True)
  return (
    mapped[:MAX_CANDIDATES_PER_FRAME],
    crop_width,
    crop_height,
    {
      "anchor_landmark": anchor_label,
      "crop_bounds": crop_bounds,
      "wrist_rejected_count": wrist_rejected_count,
    },
  )
