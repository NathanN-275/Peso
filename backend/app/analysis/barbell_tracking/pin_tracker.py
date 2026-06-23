from __future__ import annotations

import math
import time
from typing import Any

from .constants import (
  BARBELL_TRACK_TARGET_FPS,
  MIN_TRACK_COVERAGE,
  MIN_TRACK_POINTS,
  TRACKING_SOURCE,
  TRACKING_TARGET,
)
from .postprocess import _smooth_points

PIN_ASSISTED_MIN_COVERAGE = max(MIN_TRACK_COVERAGE, 0.35)
PIN_ESTIMATE_MAX_GAP_FRAMES = 2
PIN_ESTIMATE_CONFIDENCE_CAP = 0.42
PIN_PERSISTENCE_CONFIDENCE = 0.24
PIN_PRIOR_MIN_CONFIDENCE = 0.42


def _timestamp_for_index(source_index: int, fps: float) -> float:
  return source_index / fps if fps > 0 else source_index / BARBELL_TRACK_TARGET_FPS


def _in_rep_windows(timestamp: float, rep_windows: list[dict[str, Any]]) -> bool:
  if not rep_windows:
    return True
  return any(float(window["start"]) <= timestamp <= float(window["end"]) for window in rep_windows)


def _point_from_prior(
  source_index: int,
  prior: dict[str, Any],
  *,
  fps: float,
) -> dict[str, Any] | None:
  confidence = float(prior.get("confidence") or 0.0)
  is_reference = prior.get("tracking_state") == "reference"
  if confidence < PIN_PRIOR_MIN_CONFIDENCE and not is_reference:
    return None
  x = prior.get("x")
  y = prior.get("y")
  if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
    return None
  if not math.isfinite(float(x)) or not math.isfinite(float(y)):
    return None
  if not (0.0 <= float(x) <= 1.0 and 0.0 <= float(y) <= 1.0):
    return None

  tracking_state = "reference" if is_reference else "guided"
  return {
    "time": _timestamp_for_index(source_index, fps),
    "x": float(x),
    "y": float(y),
    "confidence": max(confidence, PIN_PERSISTENCE_CONFIDENCE) if is_reference else confidence,
    "trackingState": tracking_state,
    "manual_assisted": True,
  }


def _expected_source_indices(
  pose_source_indices: list[int],
  manual_priors: dict[int, dict[str, Any]],
  *,
  tracking_frame_step: int,
  fps: float,
  rep_windows: list[dict[str, Any]],
) -> list[int]:
  step = max(tracking_frame_step, 1)
  indices = [
    index
    for index in pose_source_indices
    if index % step == 0 and _in_rep_windows(_timestamp_for_index(index, fps), rep_windows)
  ]
  if indices:
    return indices

  return [
    index
    for index in sorted(manual_priors)
    if _in_rep_windows(_timestamp_for_index(index, fps), rep_windows)
  ]


def _append_source_count(counts: dict[str, int], source: str) -> None:
  counts[source] = counts.get(source, 0) + 1


def _empty_source_counts() -> dict[str, int]:
  return {
    "reference": 0,
    "pin_roi": 0,
    "pin_estimated": 0,
    "visual_reacquired": 0,
    "automatic_fallback": 0,
    "gap": 0,
  }


def _clamp_point_coordinate(value: float) -> float:
  return min(max(float(value), 0.0), 1.0)


def _neighbor_sample(
  samples: list[dict[str, Any] | None],
  start: int,
  step: int,
) -> tuple[int, dict[str, Any]] | None:
  index = start
  while 0 <= index < len(samples):
    point = samples[index]
    if point is not None:
      return index, point
    index += step
  return None


def _pin_estimated_sample(
  samples: list[dict[str, Any] | None],
  expected_indices: list[int],
  sample_index: int,
  *,
  fps: float,
) -> tuple[dict[str, Any] | None, str]:
  previous = _neighbor_sample(samples, sample_index - 1, -1)
  following = _neighbor_sample(samples, sample_index + 1, 1)
  timestamp = _timestamp_for_index(expected_indices[sample_index], fps)

  if previous is not None and following is not None:
    previous_position, previous_point = previous
    following_position, following_point = following
    span = max(following_position - previous_position, 1)
    progress = (sample_index - previous_position) / span
    confidence = min(
      float(previous_point.get("confidence") or 0.0),
      float(following_point.get("confidence") or 0.0),
      PIN_ESTIMATE_CONFIDENCE_CAP,
    ) * 0.82
    return {
      "time": timestamp,
      "x": _clamp_point_coordinate(
        float(previous_point["x"])
        + ((float(following_point["x"]) - float(previous_point["x"])) * progress)
      ),
      "y": _clamp_point_coordinate(
        float(previous_point["y"])
        + ((float(following_point["y"]) - float(previous_point["y"])) * progress)
      ),
      "confidence": max(confidence, PIN_PERSISTENCE_CONFIDENCE),
      "trackingState": "estimated",
      "manual_assisted": True,
    }, "interpolated_between_pin_samples"

  if previous is not None:
    previous_position, previous_point = previous
    earlier = _neighbor_sample(samples, previous_position - 1, -1)
    if earlier is not None:
      earlier_position, earlier_point = earlier
      previous_index = expected_indices[previous_position]
      earlier_index = expected_indices[earlier_position]
      frame_delta = max(previous_index - earlier_index, 1)
      horizon = expected_indices[sample_index] - previous_index
      velocity_x = (float(previous_point["x"]) - float(earlier_point["x"])) / frame_delta
      velocity_y = (float(previous_point["y"]) - float(earlier_point["y"])) / frame_delta
      x = float(previous_point["x"]) + (velocity_x * horizon)
      y = float(previous_point["y"]) + (velocity_y * horizon)
      reason = "predicted_from_pin_velocity"
    else:
      x = float(previous_point["x"])
      y = float(previous_point["y"])
      reason = "held_last_pin_sample"
    gap_frames = max(sample_index - previous_position, 1)
    confidence = min(
      float(previous_point.get("confidence") or 0.0) * (0.78 ** gap_frames),
      PIN_ESTIMATE_CONFIDENCE_CAP,
    )
    return {
      "time": timestamp,
      "x": _clamp_point_coordinate(x),
      "y": _clamp_point_coordinate(y),
      "confidence": max(confidence, PIN_PERSISTENCE_CONFIDENCE),
      "trackingState": "estimated",
      "manual_assisted": True,
    }, reason

  if following is not None:
    following_position, following_point = following
    gap_frames = max(following_position - sample_index, 1)
    confidence = min(
      float(following_point.get("confidence") or 0.0) * (0.78 ** gap_frames),
      PIN_ESTIMATE_CONFIDENCE_CAP,
    )
    return {
      "time": timestamp,
      "x": _clamp_point_coordinate(float(following_point["x"])),
      "y": _clamp_point_coordinate(float(following_point["y"])),
      "confidence": max(confidence, PIN_PERSISTENCE_CONFIDENCE),
      "trackingState": "estimated",
      "manual_assisted": True,
    }, "held_next_pin_sample"

  return None, "missing_pin_neighbors"


def build_pin_assisted_barbell_result(
  *,
  manual_priors: dict[int, dict[str, Any]],
  pose_source_indices: list[int],
  fps: float,
  width: int,
  height: int,
  tracking_frame_step: int,
  rep_windows: list[dict[str, Any]],
  selected_side: str | None,
  coordinate_space: dict[str, int | str],
  started_at: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
  reference_indices = [
    index
    for index, prior in manual_priors.items()
    if prior.get("tracking_state") == "reference"
  ]
  diagnostics: dict[str, Any] = {
    "pin_assisted_requested": bool(manual_priors),
    "pin_assisted_primary": False,
    "pin_assisted_fallback_reason": None,
    "pin_source_counts": _empty_source_counts(),
    "pin_source_switch_count": 0,
    "pin_frames": [],
  }
  if not manual_priors:
    diagnostics["pin_assisted_fallback_reason"] = "missing_manual_barbell_priors"
    return None, diagnostics
  if not reference_indices:
    diagnostics["pin_assisted_fallback_reason"] = "missing_reference_pin_prior"
    return None, diagnostics

  normalized_priors = {
    int(index): prior
    for index, prior in manual_priors.items()
  }
  expected_indices = _expected_source_indices(
    pose_source_indices,
    normalized_priors,
    tracking_frame_step=tracking_frame_step,
    fps=fps,
    rep_windows=rep_windows,
  )
  if not expected_indices:
    diagnostics["pin_assisted_fallback_reason"] = "no_pin_tracking_samples"
    return None, diagnostics

  samples: list[dict[str, Any] | None] = []
  frame_diagnostics: list[dict[str, Any]] = []
  source_counts = _empty_source_counts()
  real_point_count = 0
  for source_index in expected_indices:
    prior = normalized_priors.get(source_index)
    point = _point_from_prior(source_index, prior, fps=fps) if prior else None
    if point is not None:
      source = "reference" if point["trackingState"] == "reference" else "pin_roi"
      real_point_count += 1
      _append_source_count(source_counts, source)
      samples.append(point)
      frame_diagnostics.append({
        "source_index": source_index,
        "time": round(float(point["time"]), 4),
        "source": source,
        "raw_pin_x": round(float(point["x"]) * width, 2),
        "raw_pin_y": round(float(point["y"]) * height, 2),
        "confidence": round(float(point["confidence"]), 3),
        "template_score": prior.get("template_score") if prior else None,
        "klt_inlier_count": prior.get("affine_inliers") or prior.get("tracked_features") if prior else None,
        "rejection_reason": None,
      })
      continue

    _append_source_count(source_counts, "gap")
    samples.append(None)
    frame_diagnostics.append({
      "source_index": source_index,
      "time": round(_timestamp_for_index(source_index, fps), 4),
      "source": "gap",
      "raw_pin_x": None,
      "raw_pin_y": None,
      "confidence": 0.0,
      "template_score": None,
      "klt_inlier_count": None,
      "rejection_reason": "pin_roi_missing",
    })

  estimated_count = 0
  detected_samples = list(samples)
  for sample_index, sample in enumerate(detected_samples):
    if sample is not None:
      continue
    estimated_point, estimate_reason = _pin_estimated_sample(
      detected_samples,
      expected_indices,
      sample_index,
      fps=fps,
    )
    if estimated_point is None:
      frame_diagnostics[sample_index]["rejection_reason"] = estimate_reason
      continue

    samples[sample_index] = estimated_point
    estimated_count += 1
    source_counts["gap"] = max(source_counts["gap"] - 1, 0)
    _append_source_count(source_counts, "pin_estimated")
    frame_diagnostics[sample_index].update({
      "source": "pin_estimated",
      "predicted_x": round(float(estimated_point["x"]) * width, 2),
      "predicted_y": round(float(estimated_point["y"]) * height, 2),
      "confidence": round(float(estimated_point["confidence"]), 3),
      "rejection_reason": None,
      "fallback_reason": estimate_reason,
    })

  points = [point for point in samples if point is not None]
  sampled_count = len(expected_indices)
  coverage = len(points) / max(sampled_count, 1)
  if len(points) < MIN_TRACK_POINTS or coverage < PIN_ASSISTED_MIN_COVERAGE:
    diagnostics.update({
      "pin_assisted_fallback_reason": "low_pin_assisted_coverage",
      "pin_source_counts": source_counts,
      "pin_frames": frame_diagnostics[:120],
      "sampled_frame_count": sampled_count,
      "detected_point_count": real_point_count,
      "interpolated_point_count": estimated_count,
      "coverage": round(coverage, 3),
    })
    return None, diagnostics

  smoothed_points = _smooth_points(points)
  point_times = [float(point["time"]) for point in smoothed_points]
  source_switch_count = 0
  previous_source: str | None = None
  for frame in frame_diagnostics:
    source = str(frame.get("source") or "gap")
    if previous_source is not None and source != previous_source:
      source_switch_count += 1
    previous_source = source

  per_rep_coverage: list[dict[str, Any]] = []
  for window in rep_windows:
    rep_index = int(window["rep_index"])
    start = float(window["start"])
    end = float(window["end"])
    rep_expected = [
      index
      for index in expected_indices
      if start <= _timestamp_for_index(index, fps) <= end
    ]
    rep_times = [time for time in point_times if start <= time <= end]
    gap_boundaries = [start, *rep_times, end]
    max_gap = max(
      (next_time - previous_time for previous_time, next_time in zip(gap_boundaries, gap_boundaries[1:])),
      default=max(end - start, 0.0),
    )
    per_rep_coverage.append({
      "rep_index": rep_index,
      "start": round(start, 4),
      "bottom": round(float(window["bottom"]), 4),
      "end": round(end, 4),
      "sampled_frame_count": len(rep_expected),
      "detected_point_count": len(rep_times),
      "coverage": round(len(rep_times) / max(len(rep_expected), 1), 3),
      "max_point_gap_seconds": round(max_gap, 4),
    })

  max_point_gap_seconds = (
    max(next_time - previous_time for previous_time, next_time in zip(point_times, point_times[1:]))
    if len(point_times) >= 2
    else 0.0
  )
  effective_tracking_fps = (
    (len(point_times) - 1) / (point_times[-1] - point_times[0])
    if len(point_times) >= 2 and point_times[-1] > point_times[0]
    else 0.0
  )
  bar_vertical_range_px = (
    (max(float(point["y"]) for point in smoothed_points) - min(float(point["y"]) for point in smoothed_points)) * height
    if smoothed_points
    else 0.0
  )
  diagnostics.update({
    "available": True,
    "pin_assisted_primary": True,
    "pin_assisted_fallback_reason": None,
    "pin_source_counts": source_counts,
    "pin_source_switch_count": source_switch_count,
    "pin_frames": frame_diagnostics[:120],
  })

  processing_duration_ms = int((time.perf_counter() - started_at) * 1000)
  return {
    "barbellPath": {
      "available": True,
      "target": TRACKING_TARGET,
      "source": TRACKING_SOURCE,
      "coverage": round(coverage, 3),
      "points": smoothed_points,
    },
    "diagnostics": {
      "available": True,
      "target": TRACKING_TARGET,
      "source": TRACKING_SOURCE,
      "coverage": round(coverage, 3),
      "sampled_frame_count": sampled_count,
      "detected_point_count": real_point_count,
      "manual_point_count": len(points),
      "automatic_point_count": 0,
      "manual_accepted_count": len(points),
      "manual_blended_count": estimated_count,
      "manual_rejected_count": source_counts.get("gap", 0),
      "manual_fallback_count": 0,
      "manual_rejection_reason_counts": {},
      "interpolated_point_count": estimated_count,
      "rejected_frame_count": source_counts.get("gap", 0),
      "rejected_candidate_count": 0,
      "rejection_reason_counts": (
        {"pin_roi_missing": source_counts.get("gap", 0)}
        if source_counts.get("gap", 0)
        else {}
      ),
      "skipped_no_pose_frame_count": 0,
      "reused_nearest_pose_frame_count": 0,
      "failure_reason": None,
      "processing_duration_ms": processing_duration_ms,
      "target_fps": BARBELL_TRACK_TARGET_FPS,
      "tracking_frame_step": tracking_frame_step,
      "tracking_mode": "pin_assisted_roi",
      "local_tracker_type": "manual_pin_roi",
      "initialization_confirmed": True,
      "initialization_frame_count": 1,
      "hough_detection_count": 0,
      "optical_flow_point_count": 0,
      "optical_flow_inlier_count": 0,
      "template_match_score": None,
      "local_tracking_confidence": 0.0,
      "accepted_local_tracking_count": len(points),
      "fresh_hough_correction_count": 0,
      "stationary_hardware_rejection_count": 0,
      "reacquisition_count": 0,
      "local_tracking_failure_count": source_counts.get("gap", 0),
      "outlier_removed_count": 0,
      "bar_vertical_range_px": round(bar_vertical_range_px, 2),
      "shoulder_vertical_range_px": None,
      "crop_width": None,
      "crop_height": None,
      "average_crop_width": None,
      "average_crop_height": None,
      "selected_candidate_type": "manual_pin_roi",
      "plate_center_x": None,
      "plate_center_y": None,
      "plate_radius": None,
      "final_bar_point_x": round(float(smoothed_points[-1]["x"]) * width, 2) if smoothed_points else None,
      "final_bar_point_y": round(float(smoothed_points[-1]["y"]) * height, 2) if smoothed_points else None,
      "final_bar_confidence": round(float(smoothed_points[-1]["confidence"]), 3) if smoothed_points else 0.0,
      "final_bar_reason": None,
      "final_bar_reason_counts": {},
      "real_hub_detection_count": 0,
      "hub_rejected_count": 0,
      "path_prior_rejection_count": 0,
      "path_prior_last_residual_px": None,
      "path_prior_max_residual_px": None,
      "path_prior_mean_residual_px": None,
      "selected_side": selected_side,
      "coordinate_space": coordinate_space,
      "collar_candidate_count": 0,
      "collar_descriptor_score": None,
      "tracklet_confirmation_count": len(points),
      "bad_candidate_rejection_counts": {},
      "path_reset_count": 0,
      "stale_prior_expiration_count": 0,
      "reacquisition_success_count": 0,
      "per_rep_coverage": per_rep_coverage,
      "source_switch_count": source_switch_count,
      "source_state_counts": {
        "reference": source_counts.get("reference", 0),
        "guided": source_counts.get("pin_roi", 0),
        "estimated": source_counts.get("pin_estimated", 0),
      },
      "max_point_gap_seconds": round(max_point_gap_seconds, 4),
      "effective_tracking_fps": round(effective_tracking_fps, 3),
      **diagnostics,
    },
  }, diagnostics
