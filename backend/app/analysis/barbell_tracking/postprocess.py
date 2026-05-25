from __future__ import annotations

import math
from typing import Any

from .constants import MAX_INTERPOLATION_GAP_FRAMES, MAX_OUTLIER_VELOCITY


def _interpolate_missing(samples: list[dict[str, Any] | None]) -> tuple[list[dict[str, Any]], int]:
  filled: list[dict[str, Any] | None] = samples[:]
  interpolated_count = 0
  index = 0

  while index < len(filled):
    if filled[index] is not None:
      index += 1
      continue

    gap_start = index
    while index < len(filled) and filled[index] is None:
      index += 1
    gap_end = index - 1
    previous_index = gap_start - 1
    next_index = index

    if (
      previous_index < 0
      or next_index >= len(filled)
      or filled[previous_index] is None
      or filled[next_index] is None
      or (gap_end - gap_start + 1) > MAX_INTERPOLATION_GAP_FRAMES
    ):
      continue

    previous = filled[previous_index]
    next_point = filled[next_index]
    if previous is None or next_point is None:
      continue

    total_steps = next_index - previous_index
    for missing_index in range(gap_start, gap_end + 1):
      progress = (missing_index - previous_index) / total_steps
      filled[missing_index] = {
        "time": samples[missing_index]["time"] if samples[missing_index] else (
          previous["time"] + ((next_point["time"] - previous["time"]) * progress)
        ),
        "x": previous["x"] + ((next_point["x"] - previous["x"]) * progress),
        "y": previous["y"] + ((next_point["y"] - previous["y"]) * progress),
        "confidence": min(previous["confidence"], next_point["confidence"]) * 0.72,
        "interpolated": True,
      }
      interpolated_count += 1

  return [point for point in filled if point is not None], interpolated_count


def _remove_motion_outliers(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
  if len(points) < 3:
    return points, 0

  filtered: list[dict[str, Any]] = [points[0]]
  removed_count = 0

  for point in points[1:]:
    previous = filtered[-1]
    distance = math.hypot(float(point["x"]) - float(previous["x"]), float(point["y"]) - float(previous["y"]))
    if distance > MAX_OUTLIER_VELOCITY:
      removed_count += 1
      continue

    filtered.append(point)

  return filtered, removed_count


def _smooth_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
  smoothed: list[dict[str, Any]] = []

  for index, point in enumerate(points):
    window = points[max(index - 1, 0):min(index + 2, len(points))]
    confidence_sum = sum(max(float(item["confidence"]), 0.01) for item in window)
    smoothed.append(
      {
        "time": round(float(point["time"]), 4),
        "x": round(
          sum(float(item["x"]) * max(float(item["confidence"]), 0.01) for item in window)
          / confidence_sum,
          4,
        ),
        "y": round(
          sum(float(item["y"]) * max(float(item["confidence"]), 0.01) for item in window)
          / confidence_sum,
          4,
        ),
        "confidence": round(float(point["confidence"]), 3),
      }
    )

  return smoothed
