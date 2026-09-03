from __future__ import annotations

import math
from typing import Any


LONG_CLIP_THRESHOLD_SECONDS = 60.0
MAX_COARSE_SAMPLES = 600
MAX_REFINEMENT_SAMPLES = 360
REFINEMENT_TARGET_FPS = 12.0


def timestamp_sample_indices(
  *,
  frame_count: int,
  source_fps: float,
  target_fps: float,
  windows: list[tuple[float, float]] | None = None,
  max_samples: int | None = None,
) -> list[int]:
  """Schedule by media time so high-FPS sources never overshoot target FPS."""
  if frame_count <= 0 or source_fps <= 0 or target_fps <= 0:
    return []

  normalized_windows = [
    (max(float(start), 0.0), max(float(end), float(start)))
    for start, end in (windows or [(0.0, frame_count / source_fps)])
    if math.isfinite(float(start)) and math.isfinite(float(end)) and float(end) >= 0
  ]
  if not normalized_windows:
    return []

  scheduled: list[int] = []
  seen: set[int] = set()
  interval_seconds = 1.0 / target_fps
  for start, end in normalized_windows:
    sample_time = start
    while sample_time <= end + 1e-9:
      frame_index = min(max(int(math.ceil((sample_time * source_fps) - 1e-9)), 0), frame_count - 1)
      if frame_index not in seen:
        seen.add(frame_index)
        scheduled.append(frame_index)
        if max_samples is not None and len(scheduled) >= max_samples:
          return sorted(scheduled)
      sample_time += interval_seconds
  return sorted(scheduled)


def coarse_target_fps(duration_seconds: float, requested_fps: float) -> float:
  if duration_seconds <= LONG_CLIP_THRESHOLD_SECONDS:
    return requested_fps
  return min(requested_fps, MAX_COARSE_SAMPLES / max(duration_seconds, 1.0))


def active_motion_windows(
  frames: list[dict[str, Any]],
  *,
  padding_seconds: float = 0.8,
) -> list[tuple[float, float]]:
  """Find coarse lower-body motion spans for long-clip refinement."""
  observations: list[tuple[float, float]] = []
  for frame in frames:
    landmarks = frame.get("landmarks") or {}
    hips = [
      landmarks.get(name)
      for name in ("left_hip", "right_hip")
      if float((landmarks.get(name) or {}).get("visibility") or 0.0) >= 0.35
    ]
    if not hips:
      continue
    observations.append((
      float(frame.get("timestamp_ms") or 0.0) / 1000.0,
      sum(float(point["y"]) for point in hips) / len(hips),
    ))

  moving_spans: list[tuple[float, float]] = []
  for previous, current in zip(observations, observations[1:]):
    elapsed = current[0] - previous[0]
    if elapsed <= 0:
      continue
    velocity = abs(current[1] - previous[1]) / elapsed
    if velocity >= 0.012:
      moving_spans.append((
        max(previous[0] - padding_seconds, 0.0),
        current[0] + padding_seconds,
      ))

  merged: list[tuple[float, float]] = []
  for start, end in moving_spans:
    if merged and start <= merged[-1][1] + 0.35:
      merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    else:
      merged.append((start, end))
  return merged


def merge_pose_frames(
  coarse_frames: list[dict[str, Any]],
  refined_frames: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  refined_indices = {int(frame["source_frame_index"]) for frame in refined_frames}
  merged = [
    frame for frame in coarse_frames
    if int(frame.get("source_frame_index", -1)) not in refined_indices
  ] + list(refined_frames)
  merged.sort(key=lambda frame: int(frame.get("source_frame_index", -1)))
  for index, frame in enumerate(merged):
    frame["frame_index"] = index
  return merged
