from __future__ import annotations

import math
from typing import Any

from .candidate import Candidate
from .constants import (
  MAX_CANDIDATES_PER_FRAME,
  MAX_DETECTION_CROP_WIDTH,
  MIN_SLEEVE_END_DESCRIPTOR_SCORE,
)

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
  candidates = [
    Candidate(
      x=float(circle[0]) + offset_x,
      y=float(circle[1]) + offset_y,
      radius=float(circle[2]),
      confidence=0.62,
    )
    for circle in (circles[0] if circles is not None else [])
  ]

  hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
  kernel_size = max(5, int(round(min_dimension * 0.025)))
  if kernel_size % 2 == 0:
    kernel_size += 1
  kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
  hue_bands = ((0, 18), (18, 36), (36, 100), (100, 138), (138, 179))
  for hue_min, hue_max in hue_bands:
    color_mask = cv2.inRange(hsv, (hue_min, 22, 20), (hue_max, 255, 240))
    color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel)
    contours = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
    for contour in contours:
      area = float(cv2.contourArea(contour))
      perimeter = float(cv2.arcLength(contour, True))
      if area <= 0.0 or perimeter <= 0.0:
        continue
      (center_x, center_y), radius = cv2.minEnclosingCircle(contour)
      if radius < min_dimension * 0.055 or radius > min_dimension * 0.34:
        continue
      _, _, box_width, box_height = cv2.boundingRect(contour)
      aspect_ratio = box_width / max(box_height, 1)
      circularity = (4.0 * math.pi * area) / max(perimeter * perimeter, 1.0)
      fill_ratio = area / max(math.pi * radius * radius, 1.0)
      if not 0.55 <= aspect_ratio <= 1.55 or circularity < 0.34 or fill_ratio < 0.28:
        continue
      confidence = min(0.58 + (circularity * 0.2) + (fill_ratio * 0.18), 0.92)
      contour_candidate = Candidate(
        x=float(center_x) + offset_x,
        y=float(center_y) + offset_y,
        radius=float(radius),
        confidence=confidence,
      )
      duplicate_index = next(
        (
          index
          for index, candidate in enumerate(candidates)
          if math.hypot(candidate.x - contour_candidate.x, candidate.y - contour_candidate.y)
          <= max(min(candidate.radius, contour_candidate.radius) * 0.24, 6.0)
        ),
        None,
      )
      if duplicate_index is None:
        candidates.append(contour_candidate)
      elif contour_candidate.confidence > candidates[duplicate_index].confidence:
        candidates[duplicate_index] = contour_candidate

  return candidates


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
  anchor_label = "upper_back_proxy" if shoulder else "pose_bounds"
  if shoulder:
    shoulder_x, shoulder_y = shoulder
    x_margin = width * 0.46
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
  rejection_radius = min(
    WRIST_REJECTION_RADIUS_PX,
    max(12.0, candidate.radius * 0.28),
  )
  return any(
    math.hypot(candidate.x - wrist_x, candidate.y - wrist_y) <= rejection_radius
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


def _point_to_axis_distance(
  point: tuple[float, float],
  origin: tuple[float, float],
  direction: tuple[float, float],
) -> tuple[float, float]:
  offset_x = point[0] - origin[0]
  offset_y = point[1] - origin[1]
  projection = (offset_x * direction[0]) + (offset_y * direction[1])
  perpendicular = abs((offset_x * -direction[1]) + (offset_y * direction[0]))
  return perpendicular, projection


def _detect_sleeve_end_candidates(
  cv2: Any,
  frame: Any,
  *,
  shoulder: tuple[float, float] | None,
  wrist_points: list[tuple[float, float]],
) -> list[Candidate]:
  """Detect the exposed free end of an unloaded sleeve.

  A valid end cap must terminate a long edge that runs back toward the selected
  shoulder and passes near the selected wrist. This deliberately excludes
  generic rack holes and other small circles.
  """
  if shoulder is None or not wrist_points:
    return []

  height, width = frame.shape[:2]
  max_dimension = max(width, height)
  min_dimension = min(width, height)
  x0 = max(int(round(shoulder[0] - (width * 0.45))), 0)
  x1 = min(int(round(shoulder[0] + (width * 0.45))), width)
  y0 = max(int(round(shoulder[1] - (height * 0.52))), 0)
  y1 = min(int(round(shoulder[1] + (height * 0.1))), height)
  if x1 <= x0 or y1 <= y0:
    return []

  crop = frame[y0:y1, x0:x1]
  local_shoulder = (shoulder[0] - x0, shoulder[1] - y0)
  local_wrists = [(wrist[0] - x0, wrist[1] - y0) for wrist in wrist_points]
  gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
  blurred = cv2.GaussianBlur(gray, (5, 5), 1.2)
  edges = cv2.Canny(blurred, 45, 130)
  lines = cv2.HoughLinesP(
    edges,
    1,
    math.pi / 180,
    threshold=max(16, int(min_dimension * 0.04)),
    minLineLength=max(22, int(min_dimension * 0.065)),
    maxLineGap=max(6, int(min_dimension * 0.02)),
  )
  if lines is None:
    return []

  proposals: list[dict[str, Any]] = []
  for raw_line in lines[:, 0]:
    line_x1, line_y1, line_x2, line_y2 = (float(value) for value in raw_line)
    line_length = math.hypot(line_x2 - line_x1, line_y2 - line_y1)
    if line_length <= 0:
      continue
    endpoint_1 = (line_x1, line_y1)
    endpoint_2 = (line_x2, line_y2)
    distance_1 = math.hypot(local_shoulder[0] - line_x1, local_shoulder[1] - line_y1)
    distance_2 = math.hypot(local_shoulder[0] - line_x2, local_shoulder[1] - line_y2)
    outer_endpoint, inner_endpoint = (
      (endpoint_1, endpoint_2)
      if distance_1 >= distance_2
      else (endpoint_2, endpoint_1)
    )
    direction = (
      (inner_endpoint[0] - outer_endpoint[0]) / line_length,
      (inner_endpoint[1] - outer_endpoint[1]) / line_length,
    )
    outer_shoulder_distance = math.hypot(
      local_shoulder[0] - outer_endpoint[0],
      local_shoulder[1] - outer_endpoint[1],
    )
    if outer_shoulder_distance < max_dimension * 0.1 or outer_shoulder_distance > max_dimension * 0.52:
      continue
    shoulder_direction = (
      (local_shoulder[0] - outer_endpoint[0]) / outer_shoulder_distance,
      (local_shoulder[1] - outer_endpoint[1]) / outer_shoulder_distance,
    )
    alignment = (direction[0] * shoulder_direction[0]) + (direction[1] * shoulder_direction[1])
    if alignment < 0.9:
      continue
    wrist_measurements = [
      _point_to_axis_distance(wrist, outer_endpoint, direction)
      for wrist in local_wrists
    ]
    wrist_axis_distance, wrist_projection = min(wrist_measurements, key=lambda item: item[0])
    if wrist_axis_distance > max(30.0, min_dimension * 0.08):
      continue
    if wrist_projection < line_length * 0.45 or wrist_projection > outer_shoulder_distance + 35.0:
      continue
    proposals.append(
      {
        "outer": outer_endpoint,
        "direction": direction,
        "length": line_length,
        "score": (
          (alignment * 0.5)
          + (min(line_length / max(min_dimension * 0.24, 1.0), 1.0) * 0.3)
          + (max(0.0, 1.0 - (wrist_axis_distance / max(30.0, min_dimension * 0.08))) * 0.2)
        ),
      }
    )

  output: list[Candidate] = []
  cluster_distance = max(24.0, min_dimension * 0.07)
  for proposal in proposals:
    group = [
      other
      for other in proposals
      if math.hypot(
        proposal["outer"][0] - other["outer"][0],
        proposal["outer"][1] - other["outer"][1],
      ) <= cluster_distance
      and abs(
        (proposal["direction"][0] * other["direction"][0])
        + (proposal["direction"][1] * other["direction"][1])
      ) >= 0.94
    ]
    if len(group) < 2:
      continue
    weight_sum = sum(max(float(item["score"]), 0.01) for item in group)
    outer_x = sum(item["outer"][0] * item["score"] for item in group) / weight_sum
    outer_y = sum(item["outer"][1] * item["score"] for item in group) / weight_sum
    direction_x = sum(item["direction"][0] * item["score"] for item in group) / weight_sum
    direction_y = sum(item["direction"][1] * item["score"] for item in group) / weight_sum
    direction_length = max(math.hypot(direction_x, direction_y), 1e-6)
    direction_x /= direction_length
    direction_y /= direction_length
    refinement_distance = min(max(sum(item["length"] for item in group) / len(group) * 0.25, 12.0), 28.0)
    confidence = min(
      0.45
      + (min(len(group), 4) * 0.08)
      + ((sum(item["score"] for item in group) / len(group)) * 0.18),
      1.0,
    )
    if confidence < MIN_SLEEVE_END_DESCRIPTOR_SCORE:
      continue
    target_x = outer_x - (direction_x * refinement_distance)
    target_y = outer_y - (direction_y * refinement_distance)
    patch_x0 = max(int(round(target_x)) - 6, 0)
    patch_y0 = max(int(round(target_y)) - 6, 0)
    patch_x1 = min(int(round(target_x)) + 7, gray.shape[1])
    patch_y1 = min(int(round(target_y)) + 7, gray.shape[0])
    target_patch = gray[patch_y0:patch_y1, patch_x0:patch_x1]
    if target_patch.size == 0 or float(cv2.mean(target_patch)[0]) < 110.0:
      continue
    output.append(
      Candidate(
        x=target_x + x0,
        y=target_y + y0,
        radius=28.0,
        confidence=confidence,
      )
    )

  output.sort(key=lambda candidate: candidate.confidence, reverse=True)
  deduplicated: list[Candidate] = []
  for candidate in output:
    if any(math.hypot(candidate.x - kept.x, candidate.y - kept.y) < 20.0 for kept in deduplicated):
      continue
    deduplicated.append(candidate)
  return deduplicated[:4]
