from __future__ import annotations

import math
from typing import Any

from .constants import MAX_OUTLIER_VELOCITY

MAX_SMOOTHING_TIME_GAP_SECONDS = 0.5
MAX_SMOOTHING_DISPLACEMENT = 0.015
MAX_MANUAL_SMOOTHING_DISPLACEMENT = 0.006


def _interpolate_missing(
  samples: list[dict[str, Any] | None],
  *,
  blocked_gap_indices: set[int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
  points: list[dict[str, Any]] = []
  interpolated_count = 0
  sample_index = 0
  blocked_gap_indices = blocked_gap_indices or set()

  while sample_index < len(samples):
    point = samples[sample_index]
    if point is not None:
      points.append(point)
      sample_index += 1
      continue

    gap_start = sample_index
    while sample_index < len(samples) and samples[sample_index] is None:
      sample_index += 1
    gap_length = sample_index - gap_start
    previous = points[-1] if points else None
    following = samples[sample_index] if sample_index < len(samples) else None
    gap_is_blocked = any(
      index in blocked_gap_indices
      for index in range(gap_start, sample_index)
    )
    if previous is None or following is None or gap_length > 2 or gap_is_blocked:
      continue

    confidence = min(
      float(previous.get("confidence") or 0.0),
      float(following.get("confidence") or 0.0),
    ) * 0.6
    for gap_offset in range(1, gap_length + 1):
      progress = gap_offset / (gap_length + 1)
      points.append({
        "time": float(previous["time"])
        + ((float(following["time"]) - float(previous["time"])) * progress),
        "x": float(previous["x"])
        + ((float(following["x"]) - float(previous["x"])) * progress),
        "y": float(previous["y"])
        + ((float(following["y"]) - float(previous["y"])) * progress),
        "confidence": min(confidence, 0.45),
        "trackingState": "estimated",
      })
      interpolated_count += 1

  return points, interpolated_count


def _remove_motion_outliers(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
  if len(points) < 3:
    return points, 0

  centered_filtered: list[dict[str, Any]] = [points[0]]
  removed_count = 0

  for index in range(1, len(points) - 1):
    previous = points[index - 1]
    point = points[index]
    following = points[index + 1]
    previous_gap = float(point["time"]) - float(previous["time"])
    following_gap = float(following["time"]) - float(point["time"])
    if (
      previous_gap <= 0
      or following_gap <= 0
      or previous_gap > MAX_SMOOTHING_TIME_GAP_SECONDS
      or following_gap > MAX_SMOOTHING_TIME_GAP_SECONDS
    ):
      centered_filtered.append(point)
      continue

    span = previous_gap + following_gap
    progress = previous_gap / span
    expected_x = float(previous["x"]) + ((float(following["x"]) - float(previous["x"])) * progress)
    expected_y = float(previous["y"]) + ((float(following["y"]) - float(previous["y"])) * progress)
    residual = math.hypot(float(point["x"]) - expected_x, float(point["y"]) - expected_y)
    neighbor_motion = math.hypot(
      float(following["x"]) - float(previous["x"]),
      float(following["y"]) - float(previous["y"]),
    )
    centered_limit = max(0.035, neighbor_motion * 1.75)
    if residual > centered_limit:
      removed_count += 1
      continue
    centered_filtered.append(point)

  centered_filtered.append(points[-1])
  filtered: list[dict[str, Any]] = [centered_filtered[0]]

  for point in centered_filtered[1:]:
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
    if point.get("trackingState") == "reference":
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
      for item in points[max(index - 2, 0):min(index + 3, len(points))]
      if abs(float(item["time"]) - point_time) <= MAX_SMOOTHING_TIME_GAP_SECONDS
    ]
    confidence_sum = sum(max(float(item["confidence"]), 0.01) for item in window)
    target_x = (
      sum(float(item["x"]) * max(float(item["confidence"]), 0.01) for item in window)
      / confidence_sum
    )
    target_y = (
      sum(float(item["y"]) * max(float(item["confidence"]), 0.01) for item in window)
      / confidence_sum
    )
    raw_x = float(point["x"])
    raw_y = float(point["y"])
    displacement = math.hypot(target_x - raw_x, target_y - raw_y)
    displacement_limit = (
      MAX_MANUAL_SMOOTHING_DISPLACEMENT
      if point.get("manual_assisted")
      else MAX_SMOOTHING_DISPLACEMENT
    )
    if displacement > displacement_limit:
      scale = displacement_limit / displacement
      target_x = raw_x + ((target_x - raw_x) * scale)
      target_y = raw_y + ((target_y - raw_y) * scale)
    smoothed.append(
      {
        **point,
        "time": round(float(point["time"]), 4),
        "x": round(target_x, 4),
        "y": round(target_y, 4),
        "confidence": round(float(point["confidence"]), 3),
      }
    )

  return smoothed
