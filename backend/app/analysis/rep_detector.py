from __future__ import annotations

from typing import Any


def smooth_series(values: list[float], window_size: int = 5) -> list[float]:
  # Smooth noisy pose measurements before rep detection.
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


def normalize_series(values: list[float]) -> list[float]:
  # Scale signals into a common 0-1 range.
  if not values:
    return []

  minimum = min(values)
  maximum = max(values)
  amplitude = maximum - minimum

  if amplitude <= 1e-6:
    return [0.0 for _ in values]

  return [(value - minimum) / amplitude for value in values]


def build_motion_signal(
  *,
  hip_depths: list[float],
  knee_flexions: list[float],
  hip_flexions: list[float],
) -> list[float]:
  # Blend depth and joint flexion into one squat signal.
  normalized_depths = normalize_series(hip_depths)
  smoothed_knees = smooth_series(knee_flexions)
  smoothed_hips = smooth_series(hip_flexions)

  return [
    (depth * 0.5) + (knee * 0.35) + (hip * 0.15)
    for depth, knee, hip in zip(normalized_depths, smoothed_knees, smoothed_hips)
  ]


def _frame_gap_for_min_duration(frames: list[dict[str, Any]], minimum_ms: int) -> int:
  # Convert a duration target into a frame gap.
  if len(frames) < 2:
    return 2

  duration_ms = max(frames[-1]["timestamp_ms"] - frames[0]["timestamp_ms"], 1)
  average_frame_ms = duration_ms / max(len(frames) - 1, 1)
  return max(round(minimum_ms / average_frame_ms), 2)


def _series_amplitude(values: list[float]) -> float:
  # Measure how much motion a signal contains.
  if not values:
    return 0.0

  return max(values) - min(values)


def _select_primary_signal(
  *,
  hip_depths: list[float],
  knee_flexions: list[float],
  hip_flexions: list[float],
) -> tuple[list[float], str]:
  # Prefer knee flexion when it has enough movement.
  knee_signal = smooth_series(knee_flexions, window_size=7)

  if _series_amplitude(knee_signal) >= 0.16:
    return knee_signal, "knee_flexion"

  return smooth_series(
    build_motion_signal(
      hip_depths=hip_depths,
      knee_flexions=knee_flexions,
      hip_flexions=hip_flexions,
    ),
    window_size=7,
  ), "fused_motion"


def _find_boundary(
  signal: list[float],
  peak_index: int,
  threshold: float,
  direction: int,
  max_gap: int,
) -> int:
  # Walk outward from the peak until the signal drops.
  index = peak_index
  best_index = peak_index
  best_value = signal[peak_index]
  steps = 0

  while 0 <= index < len(signal) and steps <= max_gap:
    value = signal[index]

    if value < best_value:
      best_value = value
      best_index = index

    if value <= threshold:
      return index

    index += direction
    steps += 1

  return best_index


def _find_peak_candidates(
  signal: list[float],
  *,
  high_threshold: float,
  min_spacing_frames: int,
) -> list[int]:
  # Pick local peaks that are tall enough and spaced apart.
  local_peaks: list[int] = []

  for index, value in enumerate(signal):
    previous_value = signal[index - 1] if index > 0 else value
    next_value = signal[index + 1] if index < len(signal) - 1 else value

    if value >= high_threshold and value >= previous_value and value >= next_value:
      local_peaks.append(index)

  selected_peaks: list[int] = []

  for peak_index in sorted(local_peaks, key=lambda index: signal[index], reverse=True):
    if all(abs(peak_index - selected_index) >= min_spacing_frames for selected_index in selected_peaks):
      selected_peaks.append(peak_index)

  return sorted(selected_peaks)


def detect_reps(
  *,
  hip_depths: list[float],
  knee_flexions: list[float],
  hip_flexions: list[float],
  frames: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  # Rep detection turns the motion signal into rep boundaries.
  if len(hip_depths) < 5:
    return [], {
      "motion_amplitude": 0.0,
      "low_threshold": None,
      "high_threshold": None,
      "reason": "not_enough_pose_frames",
    }

  motion_signal, primary_signal = _select_primary_signal(
    hip_depths=hip_depths,
    knee_flexions=knee_flexions,
    hip_flexions=hip_flexions,
  )

  minimum = min(motion_signal)
  maximum = max(motion_signal)
  amplitude = maximum - minimum

  diagnostics: dict[str, Any] = {
    "motion_amplitude": round(amplitude, 3),
    "minimum_signal": round(minimum, 3),
    "maximum_signal": round(maximum, 3),
    "primary_signal": primary_signal,
    "reason": None,
  }

  if amplitude < 0.08:
    diagnostics["reason"] = "low_squat_motion"
    return [], diagnostics

  upper_threshold = minimum + (amplitude * 0.58)
  lower_threshold = minimum + (amplitude * 0.30)
  minimum_frame_gap = _frame_gap_for_min_duration(frames, 450)
  peak_spacing_frames = _frame_gap_for_min_duration(frames, 2600)
  boundary_search_frames = _frame_gap_for_min_duration(frames, 3200)
  diagnostics["low_threshold"] = round(lower_threshold, 3)
  diagnostics["high_threshold"] = round(upper_threshold, 3)

  reps: list[dict[str, Any]] = []
  peak_candidates = _find_peak_candidates(
    motion_signal,
    high_threshold=upper_threshold,
    min_spacing_frames=peak_spacing_frames,
  )

  for peak_index in peak_candidates:
    start_index = _find_boundary(
      motion_signal,
      peak_index,
      lower_threshold,
      direction=-1,
      max_gap=boundary_search_frames,
    )
    end_index = _find_boundary(
      motion_signal,
      peak_index,
      lower_threshold,
      direction=1,
      max_gap=boundary_search_frames,
    )

    if (peak_index - start_index) < minimum_frame_gap and (end_index - peak_index) < minimum_frame_gap:
      continue

    if reps and start_index <= reps[-1]["end_index"]:
      previous_peak = reps[-1]["bottom_index"]

      if motion_signal[peak_index] > motion_signal[previous_peak]:
        reps[-1] = {
          **reps[-1],
          "bottom_index": peak_index,
          "bottom_timestamp_ms": frames[peak_index]["timestamp_ms"],
        }
      continue

    start_frame = frames[start_index]
    bottom_frame = frames[peak_index]
    end_frame = frames[end_index]
    reps.append(
      {
        "start_index": start_index,
        "bottom_index": peak_index,
        "end_index": end_index,
        "start_timestamp_ms": start_frame["timestamp_ms"],
        "bottom_timestamp_ms": bottom_frame["timestamp_ms"],
        "end_timestamp_ms": end_frame["timestamp_ms"],
      }
    )

  if not reps:
    diagnostics["reason"] = "no_complete_rep_cycle"

  diagnostics["rep_count"] = len(reps)
  return reps, diagnostics
