from __future__ import annotations

import math
from typing import Any

from .candidate import Candidate
from .constants import (
  COLLAR_GEOMETRIC_FALLBACK_CONFIDENCE_PENALTY,
  COLLAR_OFFSET_RATIO,
  COLLAR_REFINEMENT_AXIS_DEGREES,
  COLLAR_REFINEMENT_DISTANCE_CAP_RATIO,
  DEFAULT_SLEEVE_DIRECTION,
  MAX_COLLAR_OFFSET_RATIO,
  MIN_COLLAR_OFFSET_RATIO,
)

MIN_HUB_CONFIDENCE = 0.80
HUB_CENTRAL_REGION_RATIO = 0.58


def _estimate_collar_from_plate(
  plate: Candidate,
  *,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
  previous: dict[str, float] | None = None,
) -> tuple[tuple[float, float], tuple[float, float]]:
  direction_x, direction_y = DEFAULT_SLEEVE_DIRECTION
  if shoulder and plate.x < shoulder[0]:
    direction_x, direction_y = -DEFAULT_SLEEVE_DIRECTION[0], -DEFAULT_SLEEVE_DIRECTION[1]

  if previous and abs(previous.get("collar_direction_x", 0.0)) > 0.01:
    previous_direction_x = previous["collar_direction_x"]
    previous_direction_y = previous.get("collar_direction_y", DEFAULT_SLEEVE_DIRECTION[1])
    previous_magnitude = max(math.hypot(previous_direction_x, previous_direction_y), 0.01)
    previous_direction = (
      previous_direction_x / previous_magnitude,
      previous_direction_y / previous_magnitude,
    )
    current_magnitude = max(math.hypot(direction_x, direction_y), 0.01)
    current_direction = (direction_x / current_magnitude, direction_y / current_magnitude)
    if (previous_direction[0] * current_direction[0]) + (previous_direction[1] * current_direction[1]) >= 0.5:
      direction_x, direction_y = previous_direction

  magnitude = max(math.hypot(direction_x, direction_y), 0.01)
  direction_x /= magnitude
  direction_y /= magnitude
  offset = min(
    max(plate.radius * COLLAR_OFFSET_RATIO, plate.radius * MIN_COLLAR_OFFSET_RATIO),
    plate.radius * MAX_COLLAR_OFFSET_RATIO,
  )
  collar = (
    min(max(plate.x + direction_x * offset, 0.0), float(width)),
    min(max(plate.y + direction_y * offset, 0.0), float(height)),
  )
  return collar, (direction_x, direction_y)


def _validate_collar_geometry(
  collar: tuple[float, float],
  *,
  plate: Candidate,
  sleeve_direction: tuple[float, float],
  previous: dict[str, float] | None = None,
) -> str | None:
  vector_x = collar[0] - plate.x
  vector_y = collar[1] - plate.y
  distance = math.hypot(vector_x, vector_y)
  min_distance = plate.radius * MIN_COLLAR_OFFSET_RATIO
  max_distance = plate.radius * MAX_COLLAR_OFFSET_RATIO

  if distance < min_distance or distance > max_distance:
    return "collar_too_far_from_plate"

  sleeve_projection = (vector_x * sleeve_direction[0]) + (vector_y * sleeve_direction[1])
  if sleeve_projection < plate.radius * 0.04:
    return "collar_behind_plate"

  magnitude = max(distance, 0.01)
  direction_x = vector_x / magnitude
  direction_y = vector_y / magnitude
  if (direction_x * sleeve_direction[0]) + (direction_y * sleeve_direction[1]) < 0.74:
    return "collar_direction_flip"

  if previous and "collar_dx" in previous and "collar_dy" in previous:
    previous_dx = previous["collar_dx"]
    previous_dy = previous["collar_dy"]
    if math.hypot(vector_x - previous_dx, vector_y - previous_dy) > plate.radius * 0.16:
      return "collar_plate_relative_jump"

  return None


def _score_collar_patch(
  cv2: Any,
  frame: Any,
  *,
  collar: tuple[float, float],
  plate: Candidate,
  sleeve_direction: tuple[float, float],
) -> float:
  height, width = frame.shape[:2]
  radius = max(int(round(plate.radius * 0.16)), 8)
  x0 = max(int(round(collar[0])) - radius, 0)
  y0 = max(int(round(collar[1])) - radius, 0)
  x1 = min(int(round(collar[0])) + radius + 1, width)
  y1 = min(int(round(collar[1])) + radius + 1, height)
  if x1 <= x0 or y1 <= y0:
    return 0.0

  crop = frame[y0:y1, x0:x1]
  gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
  gray = cv2.GaussianBlur(gray, (3, 3), 0)
  edges = cv2.Canny(gray, 55, 145)
  edge_density = float(cv2.countNonZero(edges)) / max(edges.shape[0] * edges.shape[1], 1)
  edge_score = min(edge_density / 0.12, 1.0)

  lines = cv2.HoughLinesP(
    edges,
    1,
    math.pi / 180,
    threshold=max(6, int(radius * 0.55)),
    minLineLength=max(5, int(radius * 0.55)),
    maxLineGap=max(2, int(radius * 0.25)),
  )
  axis_score = 0.0
  if lines is not None:
    sleeve_magnitude = max(math.hypot(sleeve_direction[0], sleeve_direction[1]), 0.01)
    sleeve_axis = (
      sleeve_direction[0] / sleeve_magnitude,
      sleeve_direction[1] / sleeve_magnitude,
    )
    for line in lines[:, 0]:
      dx = float(line[2] - line[0])
      dy = float(line[3] - line[1])
      magnitude = max(math.hypot(dx, dy), 0.01)
      axis_dot = abs(((dx / magnitude) * sleeve_axis[0]) + ((dy / magnitude) * sleeve_axis[1]))
      axis_score = max(axis_score, axis_dot)

  local_contrast = float(gray.max() - gray.min()) / 255.0
  return round(min((edge_score * 0.45) + (axis_score * 0.35) + (local_contrast * 0.2), 1.0), 3)


def _point_inside_plate(
  point: tuple[float, float],
  *,
  plate: Candidate,
  max_radius_ratio: float = 0.72,
) -> bool:
  return math.hypot(point[0] - plate.x, point[1] - plate.y) <= plate.radius * max_radius_ratio


def _detect_hub_point(
  cv2: Any,
  frame: Any,
  *,
  plate: Candidate,
  previous: dict[str, float] | None = None,
) -> dict[str, Any]:
  height, width = frame.shape[:2]
  crop_radius = max(int(round(plate.radius * 0.52)), 12)
  center_x = int(round(plate.x))
  center_y = int(round(plate.y))
  x0 = max(center_x - crop_radius, 0)
  y0 = max(center_y - crop_radius, 0)
  x1 = min(center_x + crop_radius + 1, width)
  y1 = min(center_y + crop_radius + 1, height)
  if x1 <= x0 or y1 <= y0:
    return {
      "point": None,
      "confidence": 0.0,
      "reason": "hub_crop_empty",
      "source": "no_hub",
      "candidates": [],
      "rejected_candidates": [],
    }

  crop = frame[y0:y1, x0:x1]
  gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
  gray = cv2.GaussianBlur(gray, (5, 5), 0)
  local_center = (plate.x - x0, plate.y - y0)
  mask = gray.copy()
  mask[:] = 0
  cv2.circle(
    mask,
    (int(round(local_center[0])), int(round(local_center[1]))),
    max(int(round(plate.radius * 0.42)), 5),
    255,
    -1,
  )

  min_radius = max(3, int(round(plate.radius * 0.04)))
  max_radius = max(min_radius + 1, int(round(plate.radius * 0.24)))
  circles = cv2.HoughCircles(
    gray,
    cv2.HOUGH_GRADIENT,
    dp=1.15,
    minDist=max(6, int(round(plate.radius * 0.18))),
    param1=70,
    param2=10,
    minRadius=min_radius,
    maxRadius=max_radius,
  )
  candidates: list[dict[str, Any]] = []
  rejected_candidates: list[dict[str, Any]] = []
  if circles is not None:
    for circle in circles[0]:
      hub = (float(circle[0]) + x0, float(circle[1]) + y0)
      if not _point_inside_plate(hub, plate=plate, max_radius_ratio=HUB_CENTRAL_REGION_RATIO):
        rejected_candidates.append(
          {
            "point": hub,
            "radius": float(circle[2]),
            "confidence": 0.0,
            "reason": "hub_outside_plate_region",
          }
        )
        continue
      center_distance = math.hypot(hub[0] - plate.x, hub[1] - plate.y)
      radius_ratio = float(circle[2]) / max(plate.radius, 1.0)
      score = 0.68
      score += max(0.0, 0.12 * (1.0 - center_distance / max(plate.radius * 0.42, 1.0)))
      score += max(0.0, 0.22 * (1.0 - abs(radius_ratio - 0.11) / 0.12))
      if previous and "final_bar_x" in previous and "final_bar_y" in previous:
        previous_distance = math.hypot(hub[0] - previous["final_bar_x"], hub[1] - previous["final_bar_y"])
        score += max(0.0, 0.08 * (1.0 - previous_distance / max(plate.radius * 0.45, 1.0)))
      score = min(score, 1.0)
      candidate = {
        "point": hub,
        "radius": float(circle[2]),
        "confidence": score,
        "reason": None,
      }
      if score < MIN_HUB_CONFIDENCE:
        rejected_candidates.append({**candidate, "reason": "low_confidence_hub"})
      else:
        candidates.append(candidate)

  if candidates:
    selected = max(candidates, key=lambda item: item["confidence"])
    return {
      "point": selected["point"],
      "confidence": float(selected["confidence"]),
      "reason": None,
      "source": "hough_hub",
      "candidates": candidates,
      "rejected_candidates": rejected_candidates,
    }

  edges = cv2.Canny(gray, 55, 140)
  edges = cv2.bitwise_and(edges, edges, mask=mask)
  moments = cv2.moments(edges)
  if moments["m00"] > 0:
    hub = (
      x0 + (moments["m10"] / moments["m00"]),
      y0 + (moments["m01"] / moments["m00"]),
    )
    if _point_inside_plate(hub, plate=plate, max_radius_ratio=0.44):
      center_distance = math.hypot(hub[0] - plate.x, hub[1] - plate.y)
      confidence = max(0.52, 0.68 * (1.0 - center_distance / max(plate.radius * 0.58, 1.0)))
      rejected_candidates.append(
        {
          "point": hub,
          "radius": 0.0,
          "confidence": min(confidence, 0.72),
          "reason": "moments_fallback_uncertain",
        }
      )
      return {
        "point": None,
        "confidence": min(confidence, 0.72),
        "reason": "moments_fallback_uncertain",
        "source": "no_hub",
        "candidates": [],
        "rejected_candidates": rejected_candidates,
      }

  return {
    "point": None,
    "confidence": 0.0,
    "reason": "no_hub_candidates",
    "source": "no_hub",
    "candidates": [],
    "rejected_candidates": rejected_candidates,
  }


def _refine_collar_point(
  cv2: Any,
  frame: Any,
  *,
  predicted: tuple[float, float],
  plate: Candidate,
  sleeve_direction: tuple[float, float],
  previous: dict[str, float] | None = None,
) -> tuple[tuple[float, float], float, str | None]:
  height, width = frame.shape[:2]
  radius = max(int(round(plate.radius * 0.12)), 6)
  x0 = max(int(round(predicted[0])) - radius, 0)
  y0 = max(int(round(predicted[1])) - radius, 0)
  x1 = min(int(round(predicted[0])) + radius + 1, width)
  y1 = min(int(round(predicted[1])) + radius + 1, height)

  if x1 <= x0 or y1 <= y0:
    return predicted, 0.0, None

  crop = frame[y0:y1, x0:x1]
  gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
  gray = cv2.GaussianBlur(gray, (5, 5), 0)
  edges = cv2.Canny(gray, 60, 150)
  moments = cv2.moments(edges)
  if moments["m00"] <= 0:
    return predicted, 0.0, None

  refined = (
    x0 + (moments["m10"] / moments["m00"]),
    y0 + (moments["m01"] / moments["m00"]),
  )
  if math.hypot(refined[0] - predicted[0], refined[1] - predicted[1]) > plate.radius * COLLAR_REFINEMENT_DISTANCE_CAP_RATIO:
    return (
      predicted,
      COLLAR_GEOMETRIC_FALLBACK_CONFIDENCE_PENALTY,
      "collar_refinement_too_far_from_geometric_estimate",
    )

  sleeve_magnitude = max(math.hypot(sleeve_direction[0], sleeve_direction[1]), 0.01)
  sleeve_axis = (
    sleeve_direction[0] / sleeve_magnitude,
    sleeve_direction[1] / sleeve_magnitude,
  )
  plate_vector_x = refined[0] - plate.x
  plate_vector_y = refined[1] - plate.y
  plate_vector_magnitude = max(math.hypot(plate_vector_x, plate_vector_y), 0.01)
  plate_axis = (
    plate_vector_x / plate_vector_magnitude,
    plate_vector_y / plate_vector_magnitude,
  )
  min_axis_dot = math.cos(math.radians(COLLAR_REFINEMENT_AXIS_DEGREES))
  if (plate_axis[0] * sleeve_axis[0]) + (plate_axis[1] * sleeve_axis[1]) < min_axis_dot:
    return (
      predicted,
      COLLAR_GEOMETRIC_FALLBACK_CONFIDENCE_PENALTY,
      "collar_refinement_outside_sleeve_axis",
    )

  if _validate_collar_geometry(refined, plate=plate, sleeve_direction=sleeve_direction, previous=previous):
    return predicted, COLLAR_GEOMETRIC_FALLBACK_CONFIDENCE_PENALTY, "collar_refinement_invalid_geometry"

  return refined, 0.0, None
