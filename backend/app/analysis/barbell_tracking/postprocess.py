from __future__ import annotations

import math
from typing import Any

from .constants import MAX_OUTLIER_VELOCITY

MAX_SMOOTHING_TIME_GAP_SECONDS = 0.5


def _interpolate_missing(samples: list[dict[str, Any] | None]) -> tuple[list[dict[str, Any]], int]:
  # Strict hub tracking treats missing samples as uncertainty. Do not create
  # synthetic points between frames that failed fresh hub validation.
  return [point for point in samples if point is not None], 0


def _remove_motion_outliers(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
  if len(points) < 3:
    return points, 0

  filtered: list[dict[str, Any]] = [points[0]]
  removed_count = 0

  for point in points[1:]:
    previous = filtered[-1]
    if float(point["time"]) - float(previous["time"]) > MAX_SMOOTHING_TIME_GAP_SECONDS:
      filtered.append(point)
      continue

    distance = math.hypot(float(point["x"]) - float(previous["x"]), float(point["y"]) - float(previous["y"]))
    if distance > MAX_OUTLIER_VELOCITY:
      removed_count += 1
      continue

    filtered.append(point)

  return filtered, removed_count


def _smooth_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
  smoothed: list[dict[str, Any]] = []

  for index, point in enumerate(points):
    if point.get("manual_assisted"):
      smoothed.append(
        {
          **point,
          "time": round(float(point["time"]), 4),
          "x": round(float(point["x"]), 4),
          "y": round(float(point["y"]), 4),
          "confidence": round(float(point["confidence"]), 3),
          "manual_assisted": True,
        }
      )
      continue
    point_time = float(point["time"])
    window = [
      item
      for item in points[max(index - 1, 0):min(index + 2, len(points))]
      if abs(float(item["time"]) - point_time) <= MAX_SMOOTHING_TIME_GAP_SECONDS
    ]
    confidence_sum = sum(max(float(item["confidence"]), 0.01) for item in window)
    smoothed.append(
      {
        **point,
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
