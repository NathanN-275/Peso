from __future__ import annotations

from typing import Any


def smooth_series(values: list[float], window_size: int = 5) -> list[float]:
  if len(values) <= 2:
    return values

  smoothed: list[float] = []
  half_window = window_size // 2

  for index in range(len(values)):
    start = max(0, index - half_window)
    end = min(len(values), index + half_window + 1)
    segment = values[start:end]
    smoothed.append(sum(segment) / len(segment))

  return smoothed


def detect_reps(depth_values: list[float], frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
  if len(depth_values) < 5:
    return []

  smoothed = smooth_series(depth_values)
  minimum = min(smoothed)
  maximum = max(smoothed)
  amplitude = maximum - minimum

  if amplitude < 0.12:
    return []

  upper_threshold = minimum + (amplitude * 0.65)
  lower_threshold = minimum + (amplitude * 0.35)

  reps: list[dict[str, Any]] = []
  state = "top"
  start_index = 0
  bottom_index = 0

  for index, value in enumerate(smoothed):
    if state == "top":
      if value <= lower_threshold:
        start_index = index

      if value >= upper_threshold:
        state = "descending"
        bottom_index = index
      continue

    if value > smoothed[bottom_index]:
      bottom_index = index

    if value <= lower_threshold and (bottom_index - start_index) >= 2:
      start_frame = frames[start_index]
      bottom_frame = frames[bottom_index]
      end_frame = frames[index]
      reps.append(
        {
          "start_index": start_index,
          "bottom_index": bottom_index,
          "end_index": index,
          "start_timestamp_ms": start_frame["timestamp_ms"],
          "bottom_timestamp_ms": bottom_frame["timestamp_ms"],
          "end_timestamp_ms": end_frame["timestamp_ms"],
        }
      )
      state = "top"
      start_index = index

  return reps
