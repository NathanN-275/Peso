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


def _estimate_collar_from_plate(
  plate: Candidate,
  *,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
  previous: dict[str, float] | None = None,
) -> tuple[tuple[float, float], tuple[float, float]]:
  direction_x, direction_y = DEFAULT_SLEEVE_DIRECTION
  if previous and previous.get("collar_direction_x", 0.0) > 0:
    previous_direction_x = previous["collar_direction_x"]
    previous_direction_y = previous.get("collar_direction_y", DEFAULT_SLEEVE_DIRECTION[1])
    previous_magnitude = max(math.hypot(previous_direction_x, previous_direction_y), 0.01)
    previous_direction = (
      previous_direction_x / previous_magnitude,
      previous_direction_y / previous_magnitude,
    )
    default_magnitude = max(math.hypot(*DEFAULT_SLEEVE_DIRECTION), 0.01)
    default_direction = (
      DEFAULT_SLEEVE_DIRECTION[0] / default_magnitude,
      DEFAULT_SLEEVE_DIRECTION[1] / default_magnitude,
    )
    if (previous_direction[0] * default_direction[0]) + (previous_direction[1] * default_direction[1]) >= 0.5:
      direction_x, direction_y = previous_direction

  magnitude = max(math.hypot(direction_x, direction_y), 0.01)
  direction_x /= magnitude
  direction_y /= magnitude
  if direction_x < 0.82:
    direction_x, direction_y = DEFAULT_SLEEVE_DIRECTION
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

  if vector_x < plate.radius * 0.04:
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
