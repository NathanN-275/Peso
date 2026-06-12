from __future__ import annotations

import math
from bisect import bisect_left
from pathlib import Path
from typing import Any

from .candidate import Candidate
from .constants import (
  BARBELL_TRACK_TARGET_FPS,
  INIT_CONFIRMATION_FRAMES,
  MAX_INTERPOLATION_GAP_FRAMES,
  SLEEVE_END_TRACKING_TARGET,
  STALE_PATH_RESET_SECONDS,
  TRACKING_SOURCE,
)
from .detection import _detect_sleeve_end_candidates
from .local_tracker import _make_tracking_lock, _track_local_patch
from .pose import _pose_bounds, _side_wrist_points
from .postprocess import _remove_motion_outliers, _smooth_points


def _relative_point(
  candidate: Any,
  shoulder: tuple[float, float],
) -> tuple[float, float]:
  return candidate.x - shoulder[0], candidate.y - shoulder[1]


def _relative_distance(
  candidate: Any,
  shoulder: tuple[float, float],
  reference: tuple[float, float],
) -> float:
  relative = _relative_point(candidate, shoulder)
  return math.hypot(relative[0] - reference[0], relative[1] - reference[1])


def _choose_candidate(
  candidates: list[Any],
  *,
  shoulder: tuple[float, float],
  height: int,
  reference: tuple[float, float] | None,
  max_distance: float,
  required_side: int | None = None,
) -> Any | None:
  plausible = [
    candidate
    for candidate in candidates
    if candidate.y <= shoulder[1] + (height * 0.06)
    and (
      required_side is None
      or (candidate.x - shoulder[0]) * required_side >= -8.0
    )
  ]
  if not plausible:
    return None

  if reference is not None:
    matched = [
      candidate
      for candidate in plausible
      if _relative_distance(candidate, shoulder, reference) <= max_distance
    ]
    if not matched:
      return None
    return min(
      matched,
      key=lambda candidate: (
        _relative_distance(candidate, shoulder, reference)
        - (candidate.confidence * 5.0)
      ),
    )

  return max(
    plausible,
    key=lambda candidate: (
      math.hypot(candidate.x - shoulder[0], candidate.y - shoulder[1])
      + (candidate.confidence * 25.0)
    ),
  )


def _correlation(values_a: list[float], values_b: list[float]) -> float:
  if len(values_a) < 3 or len(values_a) != len(values_b):
    return 0.0
  mean_a = sum(values_a) / len(values_a)
  mean_b = sum(values_b) / len(values_b)
  centered_a = [value - mean_a for value in values_a]
  centered_b = [value - mean_b for value in values_b]
  variance_a = sum(value * value for value in centered_a)
  variance_b = sum(value * value for value in centered_b)
  if variance_a <= 1e-6 or variance_b <= 1e-6:
    return 0.0
  covariance = sum(a * b for a, b in zip(centered_a, centered_b))
  return covariance / math.sqrt(variance_a * variance_b)


def _median(values: list[float]) -> float:
  ordered = sorted(values)
  middle = len(ordered) // 2
  if len(ordered) % 2:
    return ordered[middle]
  return (ordered[middle - 1] + ordered[middle]) / 2


def _reference_anchor(reference_history: list[tuple[float, float]]) -> tuple[float, float] | None:
  if not reference_history:
    return None
  recent = reference_history[-12:]
  return _median([point[0] for point in recent]), _median([point[1] for point in recent])


def _path_residual(
  point: tuple[float, float],
  accepted_points: list[tuple[float, float]],
) -> float | None:
  recent = accepted_points[-12:]
  if len(recent) < 4:
    return None
  mean_x = sum(item[0] for item in recent) / len(recent)
  mean_y = sum(item[1] for item in recent) / len(recent)
  variance_x = sum((item[0] - mean_x) ** 2 for item in recent)
  variance_y = sum((item[1] - mean_y) ** 2 for item in recent)
  covariance = sum((item[0] - mean_x) * (item[1] - mean_y) for item in recent)
  angle = 0.5 * math.atan2(2.0 * covariance, variance_x - variance_y)
  normal_x = -math.sin(angle)
  normal_y = math.cos(angle)
  return abs(((point[0] - mean_x) * normal_x) + ((point[1] - mean_y) * normal_y))


def _interpolate_short_gaps(samples: list[dict[str, float] | None]) -> tuple[list[dict[str, float]], int]:
  output: list[dict[str, float]] = []
  interpolated_count = 0
  index = 0
  while index < len(samples):
    point = samples[index]
    if point is not None:
      output.append(point)
      index += 1
      continue

    gap_start = index
    while index < len(samples) and samples[index] is None:
      index += 1
    previous = output[-1] if output else None
    next_point = samples[index] if index < len(samples) else None
    gap_length = index - gap_start
    if (
      previous is None
      or next_point is None
      or gap_length > MAX_INTERPOLATION_GAP_FRAMES
      or float(next_point["time"]) - float(previous["time"]) > STALE_PATH_RESET_SECONDS
    ):
      continue

    for offset in range(1, gap_length + 1):
      progress = offset / (gap_length + 1)
      output.append(
        {
          "time": previous["time"] + ((next_point["time"] - previous["time"]) * progress),
          "x": previous["x"] + ((next_point["x"] - previous["x"]) * progress),
          "y": previous["y"] + ((next_point["y"] - previous["y"]) * progress),
          "confidence": min(previous["confidence"], next_point["confidence"]) * 0.9,
        }
      )
      interpolated_count += 1
  output.sort(key=lambda item: item["time"])
  return output, interpolated_count


def track_unloaded_sleeve_end(
  file_path: str,
  *,
  pose_frames: list[dict[str, Any]],
  frame_step: int,
  processed_width: int,
  processed_height: int,
  selected_side: str | None,
  rep_windows: list[dict[str, Any]] | None,
  include_rejected_diagnostics: bool = False,
) -> dict[str, Any] | None:
  import cv2

  if selected_side not in {"left", "right"} or not Path(file_path).is_file():
    return None

  capture = cv2.VideoCapture(file_path)
  if not capture.isOpened():
    return None
  if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
    capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

  fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
  pose_frame_step = max(int(frame_step or 1), 1)
  target_frame_step = max(int(round(fps / BARBELL_TRACK_TARGET_FPS)), 1) if fps > 0 else pose_frame_step
  tracking_frame_step = pose_frame_step * max(int(round(target_frame_step / pose_frame_step)), 1)
  pose_by_source_index = {
    int(frame.get("source_frame_index", -1)): frame
    for frame in pose_frames
    if frame.get("source_frame_index") is not None
  }
  pose_source_indices = sorted(pose_by_source_index)
  if not pose_by_source_index:
    capture.release()
    return None

  width = int(processed_width)
  height = int(processed_height)
  max_dimension = max(width, height)
  samples: list[dict[str, float] | None] = []
  sample_shoulders: list[float | None] = []
  pending_tracklets: list[list[tuple[int, Any, tuple[float, float]]]] = []
  confirmed_reference: tuple[float, float] | None = None
  historical_reference: tuple[float, float] | None = None
  reference_history: list[tuple[float, float]] = []
  accepted_points_px: list[tuple[float, float]] = []
  tracking_lock: dict[str, Any] | None = None
  previous_gray: Any | None = None
  consecutive_local_failures = 0
  consecutive_fresh_misses = 0
  last_accepted_time: float | None = None
  candidate_count = 0
  tracklet_confirmation_count = 0
  path_reset_count = 0
  stale_prior_expiration_count = 0
  reacquisition_success_count = 0
  active_rep_index: int | None = None
  rep_target_side: int | None = None
  path_drift_rejection_count = 0
  anchor_drift_rejection_count = 0
  descriptor_bridge_count = 0
  reused_nearest_pose_frame_count = 0
  normalized_windows = sorted(rep_windows or [], key=lambda window: float(window.get("start", 0.0)))
  frame_index = 0

  try:
    while capture.isOpened():
      success, frame = capture.read()
      if not success:
        break
      if frame_index % tracking_frame_step != 0:
        frame_index += 1
        continue

      timestamp = frame_index / fps if fps > 0 else len(samples) / BARBELL_TRACK_TARGET_FPS
      current_rep = next(
        (
          window
          for window in normalized_windows
          if float(window["start"]) <= timestamp <= float(window["end"])
        ),
        None,
      )
      tracking_rep = current_rep or next(
        (
          window
          for window in normalized_windows
          if float(window["start"]) - 0.4 <= timestamp < float(window["start"])
        ),
        None,
      )
      tracking_rep_index = int(tracking_rep.get("rep_index", 0)) if tracking_rep else None
      if tracking_rep_index != active_rep_index:
        pending_tracklets = []
        confirmed_reference = None
        reference_history = []
        accepted_points_px = []
        tracking_lock = None
        previous_gray = None
        consecutive_local_failures = 0
        consecutive_fresh_misses = 0
        rep_target_side = None
        active_rep_index = tracking_rep_index

      if normalized_windows and tracking_rep is None:
        samples.append(None)
        sample_shoulders.append(None)
        frame_index += 1
        continue

      pose_frame = pose_by_source_index.get(frame_index)
      if pose_frame is None:
        insertion_index = bisect_left(pose_source_indices, frame_index)
        nearby_pose_indices = pose_source_indices[
          max(insertion_index - 1, 0):min(insertion_index + 1, len(pose_source_indices))
        ]
        nearest_pose_index = (
          min(nearby_pose_indices, key=lambda index: abs(index - frame_index))
          if nearby_pose_indices
          else None
        )
        max_pose_distance_frames = max(int(round(fps * 0.75)), tracking_frame_step * 2)
        if (
          nearest_pose_index is not None
          and abs(nearest_pose_index - frame_index) <= max_pose_distance_frames
        ):
          pose_frame = pose_by_source_index[nearest_pose_index]
          reused_nearest_pose_frame_count += 1
        else:
          samples.append(None)
          sample_shoulders.append(None)
          frame_index += 1
          continue

      if frame.shape[1] != width or frame.shape[0] != height:
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
      gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
      bounds = _pose_bounds(pose_frame, width=width, height=height, selected_side=selected_side)
      shoulder = bounds[4]
      wrist_points = _side_wrist_points(
        pose_frame,
        selected_side=selected_side,
        width=width,
        height=height,
      )
      if shoulder is None or not wrist_points:
        samples.append(None)
        sample_shoulders.append(None)
        frame_index += 1
        continue

      candidates = _detect_sleeve_end_candidates(
        cv2,
        frame,
        shoulder=shoulder,
        wrist_points=wrist_points,
      )
      candidate_count += len(candidates)
      sample_shoulders.append(shoulder[1])

      if last_accepted_time is not None and timestamp - last_accepted_time > STALE_PATH_RESET_SECONDS:
        confirmed_reference = None
        pending_tracklets = []
        reference_history = []
        accepted_points_px = []
        tracking_lock = None
        previous_gray = gray
        consecutive_local_failures = 0
        consecutive_fresh_misses = 0
        last_accepted_time = None
        path_reset_count += 1
        stale_prior_expiration_count += 1

      if tracking_lock is not None and previous_gray is not None:
        local_shoulder = shoulder
        previous_shoulder_x = tracking_lock.get("shoulder_x")
        previous_shoulder_y = tracking_lock.get("shoulder_y")
        if (
          previous_shoulder_x is not None
          and previous_shoulder_y is not None
          and math.hypot(
            shoulder[0] - previous_shoulder_x,
            shoulder[1] - previous_shoulder_y,
          )
          > max(34.0, max_dimension * 0.055)
        ):
          local_shoulder = (float(previous_shoulder_x), float(previous_shoulder_y))
        next_lock, local_stats = _track_local_patch(
          cv2,
          previous_gray,
          gray,
          tracking_lock,
          shoulder=local_shoulder,
          width=width,
          height=height,
        )
        if next_lock is not None:
          local_point = next_lock["final_bar_point"]
          local_reference = (
            local_point[0] - local_shoulder[0],
            local_point[1] - local_shoulder[1],
          )
          fresh_candidate = _choose_candidate(
            candidates,
            shoulder=local_shoulder,
            height=height,
            reference=local_reference,
            max_distance=max(28.0, max_dimension * 0.05),
            required_side=rep_target_side,
          )
          if fresh_candidate is not None:
            fresh_reference = _relative_point(fresh_candidate, local_shoulder)
            anchor = _reference_anchor(reference_history)
            if (
              anchor is not None
              and math.hypot(fresh_reference[0] - anchor[0], fresh_reference[1] - anchor[1])
              > max(34.0, max_dimension * 0.055)
            ):
              fresh_candidate = None
              anchor_drift_rejection_count += 1
            residual = (
              _path_residual((fresh_candidate.x, fresh_candidate.y), accepted_points_px)
              if fresh_candidate is not None
              else None
            )
            if residual is not None and residual > 14.0:
              fresh_candidate = None
              path_drift_rejection_count += 1
          if fresh_candidate is not None:
            direction_distance = max(
              math.hypot(local_shoulder[0] - fresh_candidate.x, local_shoulder[1] - fresh_candidate.y),
              1.0,
            )
            sleeve_direction = (
              (local_shoulder[0] - fresh_candidate.x) / direction_distance,
              (local_shoulder[1] - fresh_candidate.y) / direction_distance,
            )
            next_lock = _make_tracking_lock(
              cv2,
              gray,
              plate=fresh_candidate,
              collar=(fresh_candidate.x, fresh_candidate.y),
              sleeve_direction=sleeve_direction,
              shoulder=local_shoulder,
              final_bar_point=(fresh_candidate.x, fresh_candidate.y),
              final_bar_confidence=fresh_candidate.confidence,
              target_kind=SLEEVE_END_TRACKING_TARGET,
            )
            next_lock["predicted_collar"] = (fresh_candidate.x, fresh_candidate.y)
            next_lock["refined_collar"] = (fresh_candidate.x, fresh_candidate.y)
            consecutive_fresh_misses = 0
          else:
            bridge_point = next_lock["final_bar_point"]
            bridge_reference = (
              bridge_point[0] - local_shoulder[0],
              bridge_point[1] - local_shoulder[1],
            )
            bridge_anchor = _reference_anchor(reference_history)
            bridge_residual = _path_residual(bridge_point, accepted_points_px)
            bridge_side_valid = (
              rep_target_side is None
              or (bridge_point[0] - local_shoulder[0]) * rep_target_side >= -8.0
            )
            bridge_anchor_valid = (
              bridge_anchor is None
              or math.hypot(
                bridge_reference[0] - bridge_anchor[0],
                bridge_reference[1] - bridge_anchor[1],
              )
              <= max(28.0, max_dimension * 0.045)
            )
            bridge_path_valid = bridge_residual is None or bridge_residual <= 12.0
            bridge_confident = (
              float(local_stats.get("local_tracking_confidence") or 0.0) >= 0.58
              and (
                int(local_stats.get("optical_flow_inlier_count") or 0) >= 6
                or float(local_stats.get("template_match_score") or 0.0) >= 0.72
              )
            )
            if (
              consecutive_fresh_misses < 6
              and bridge_side_valid
              and bridge_anchor_valid
              and bridge_path_valid
              and bridge_confident
            ):
              consecutive_fresh_misses += 1
              descriptor_bridge_count += 1
            else:
              next_lock = None

        if next_lock is not None:
          tracked_point = next_lock["final_bar_point"]
          if (
            tracked_point[0] < 0
            or tracked_point[0] >= width
            or tracked_point[1] < 0
            or tracked_point[1] >= height
            or tracked_point[1] > shoulder[1] + (height * 0.08)
          ):
            next_lock = None

        if next_lock is not None:
          tracking_lock = next_lock
          relative = (
            tracked_point[0] - local_shoulder[0],
            tracked_point[1] - local_shoulder[1],
          )
          confirmed_reference = relative
          historical_reference = relative
          reference_history.append(relative)
          accepted_points_px.append(tracked_point)
          samples.append(
            {
              "time": timestamp,
              "x": tracked_point[0] / width,
              "y": tracked_point[1] / height,
              "confidence": float(next_lock.get("final_bar_confidence", 0.65)),
            }
          )
          last_accepted_time = timestamp
          consecutive_local_failures = 0
          previous_gray = gray
          frame_index += 1
          continue

        consecutive_local_failures += 1
        if consecutive_local_failures <= 2:
          samples.append(None)
          frame_index += 1
          continue
        tracking_lock = None
        confirmed_reference = None
        pending_tracklets = []
        consecutive_local_failures = 0
        consecutive_fresh_misses = 0
        previous_gray = gray

      if confirmed_reference is not None and tracking_lock is None:
        candidate = _choose_candidate(
          candidates,
          shoulder=shoulder,
          height=height,
          reference=confirmed_reference,
          max_distance=max(34.0, max_dimension * 0.06),
          required_side=rep_target_side,
        )
        if candidate is not None:
          relative = _relative_point(candidate, shoulder)
          anchor = _reference_anchor(reference_history)
          if (
            anchor is not None
            and math.hypot(relative[0] - anchor[0], relative[1] - anchor[1])
            > max(34.0, max_dimension * 0.055)
          ):
            candidate = None
            anchor_drift_rejection_count += 1
          residual = (
            _path_residual((candidate.x, candidate.y), accepted_points_px)
            if candidate is not None
            else None
          )
          if residual is not None and residual > 14.0:
            candidate = None
            path_drift_rejection_count += 1
        if candidate is not None:
          relative = _relative_point(candidate, shoulder)
          confirmed_reference = (
            (confirmed_reference[0] * 0.72) + (relative[0] * 0.28),
            (confirmed_reference[1] * 0.72) + (relative[1] * 0.28),
          )
          historical_reference = confirmed_reference
          reference_history.append(relative)
          accepted_points_px.append((candidate.x, candidate.y))
          point = {
            "time": timestamp,
            "x": candidate.x / width,
            "y": candidate.y / height,
            "confidence": candidate.confidence,
          }
          samples.append(point)
          last_accepted_time = timestamp
          previous_gray = gray
        else:
          samples.append(None)
        frame_index += 1
        continue

      plausible_candidates = [
        candidate
        for candidate in candidates
        if candidate.y <= shoulder[1] + (height * 0.06)
        and (
          rep_target_side is None
          or (candidate.x - shoulder[0]) * rep_target_side >= -8.0
        )
      ]
      match_distance = max(44.0, max_dimension * 0.085)
      next_tracklets: list[list[tuple[int, Any, tuple[float, float]]]] = []
      for tracklet in pending_tracklets:
        previous_candidate = tracklet[-1][1]
        previous_shoulder = tracklet[-1][2]
        reference = _relative_point(previous_candidate, previous_shoulder)
        matches = sorted(
          (
            candidate
            for candidate in plausible_candidates
            if _relative_distance(candidate, shoulder, reference) <= match_distance
          ),
          key=lambda candidate: _relative_distance(candidate, shoulder, reference),
        )
        for candidate in matches[:2]:
          next_tracklets.append([*tracklet, (len(samples), candidate, shoulder)])
      next_tracklets.extend(
        [(len(samples), candidate, shoulder)]
        for candidate in plausible_candidates
      )
      pending_tracklets = sorted(
        next_tracklets,
        key=lambda tracklet: (
          len(tracklet),
          sum(item[1].confidence for item in tracklet) / len(tracklet),
          -(
            _relative_distance(tracklet[-1][1], tracklet[-1][2], historical_reference)
            if historical_reference is not None
            else 0.0
          ),
        ),
        reverse=True,
      )[:16]
      samples.append(None)
      confirmed_tracklet = next(
        (
          tracklet
          for tracklet in pending_tracklets
          if len(tracklet) >= INIT_CONFIRMATION_FRAMES
        ),
        None,
      )
      if confirmed_tracklet is not None:
        if historical_reference is not None:
          reacquisition_success_count += 1
        recent = confirmed_tracklet[-INIT_CONFIRMATION_FRAMES:]
        relative_points = [_relative_point(item[1], item[2]) for item in recent]
        confirmed_reference = (
          sum(point[0] for point in relative_points) / len(relative_points),
          sum(point[1] for point in relative_points) / len(relative_points),
        )
        historical_reference = confirmed_reference
        for sample_index, confirmed_candidate, confirmed_shoulder in recent:
          sample_time = sample_index * tracking_frame_step / fps if fps > 0 else sample_index / BARBELL_TRACK_TARGET_FPS
          samples[sample_index] = {
            "time": sample_time,
            "x": confirmed_candidate.x / width,
            "y": confirmed_candidate.y / height,
            "confidence": confirmed_candidate.confidence,
          }
          accepted_points_px.append((confirmed_candidate.x, confirmed_candidate.y))
          reference_history.append(_relative_point(confirmed_candidate, confirmed_shoulder))
        last_accepted_time = timestamp
        tracklet_confirmation_count = max(tracklet_confirmation_count, len(recent))
        confirmed_candidate = recent[-1][1]
        if rep_target_side is None:
          rep_target_side = -1 if confirmed_candidate.x < shoulder[0] else 1
        direction_distance = max(
          math.hypot(shoulder[0] - confirmed_candidate.x, shoulder[1] - confirmed_candidate.y),
          1.0,
        )
        sleeve_direction = (
          (shoulder[0] - confirmed_candidate.x) / direction_distance,
          (shoulder[1] - confirmed_candidate.y) / direction_distance,
        )
        tracking_lock = _make_tracking_lock(
          cv2,
          gray,
          plate=Candidate(
            x=confirmed_candidate.x,
            y=confirmed_candidate.y,
            radius=confirmed_candidate.radius,
            confidence=confirmed_candidate.confidence,
          ),
          collar=(confirmed_candidate.x, confirmed_candidate.y),
          sleeve_direction=sleeve_direction,
          shoulder=shoulder,
          final_bar_point=(confirmed_candidate.x, confirmed_candidate.y),
          final_bar_confidence=confirmed_candidate.confidence,
          target_kind=SLEEVE_END_TRACKING_TARGET,
        )
        tracking_lock["predicted_collar"] = (confirmed_candidate.x, confirmed_candidate.y)
        tracking_lock["refined_collar"] = (confirmed_candidate.x, confirmed_candidate.y)
        previous_gray = gray
        pending_tracklets = []
      elif tracking_lock is None:
        previous_gray = gray
      frame_index += 1
  finally:
    capture.release()

  points, interpolated_count = _interpolate_short_gaps(samples)
  points, outlier_removed_count = _remove_motion_outliers(points)
  if normalized_windows:
    points = [
      point
      for point in points
      if any(
        float(window["start"]) <= float(point["time"]) <= float(window["end"])
        for window in normalized_windows
      )
    ]
  points = [
    point
    for point in points
    if 10.0 <= float(point["x"]) * width <= width - 10.0
    and 10.0 <= float(point["y"]) * height <= height - 10.0
  ]
  if len(points) < 8 or len(points) / max(len(samples), 1) < 0.06:
    if include_rejected_diagnostics:
      return {
        "barbellPath": {"available": False, "target": SLEEVE_END_TRACKING_TARGET, "points": []},
        "diagnostics": {
          "failure_reason": "low_sleeve_tracking_coverage",
          "sampled_frame_count": len(samples),
          "detected_point_count": len(points),
          "interpolated_point_count": interpolated_count,
          "sleeve_candidate_count": candidate_count,
          "tracklet_confirmation_count": tracklet_confirmation_count,
          "coverage": round(len(points) / max(len(samples), 1), 3),
          "debug_points": points,
        },
      }
    return None

  accepted_shoulders: list[float] = []
  point_y_values: list[float] = []
  for point in points:
    sample_index = int(round(float(point["time"]) * fps / tracking_frame_step)) if fps > 0 else -1
    shoulder_y = sample_shoulders[sample_index] if 0 <= sample_index < len(sample_shoulders) else None
    if shoulder_y is None:
      continue
    accepted_shoulders.append(float(shoulder_y))
    point_y_values.append(float(point["y"]) * height)

  point_vertical_range = max(point_y_values) - min(point_y_values) if point_y_values else 0.0
  shoulder_vertical_range = max(accepted_shoulders) - min(accepted_shoulders) if accepted_shoulders else 0.0
  motion_correlation = _correlation(point_y_values, accepted_shoulders)
  coverage = len(points) / max(len(samples), 1)
  per_rep_coverage = []
  for window in normalized_windows:
    rep_index = int(window.get("rep_index", len(per_rep_coverage) + 1))
    start = float(window["start"])
    bottom = float(window["bottom"])
    end = float(window["end"])
    sampled_frame_count = sum(
      1
      for sample_index in range(len(samples))
      if start <= (sample_index * tracking_frame_step / fps if fps > 0 else sample_index / BARBELL_TRACK_TARGET_FPS) <= end
    )
    detected_point_count = sum(1 for point in points if start <= float(point["time"]) <= end)
    per_rep_coverage.append(
      {
        "rep_index": rep_index,
        "start": round(start, 4),
        "bottom": round(bottom, 4),
        "end": round(end, 4),
        "sampled_frame_count": sampled_frame_count,
        "detected_point_count": detected_point_count,
        "coverage": round(detected_point_count / max(sampled_frame_count, 1), 3),
      }
    )
  if (
    motion_correlation < 0.72
    or point_vertical_range < max(14.0, shoulder_vertical_range * 0.38)
    or coverage < 0.08
  ):
    if include_rejected_diagnostics:
      return {
        "barbellPath": {"available": False, "target": SLEEVE_END_TRACKING_TARGET, "points": []},
        "diagnostics": {
          "failure_reason": "implausible_sleeve_motion",
          "sampled_frame_count": len(samples),
          "detected_point_count": len(points),
          "interpolated_point_count": interpolated_count,
          "sleeve_candidate_count": candidate_count,
          "tracklet_confirmation_count": tracklet_confirmation_count,
          "coverage": round(coverage, 3),
          "motion_correlation": round(motion_correlation, 3),
          "bar_vertical_range_px": round(point_vertical_range, 2),
          "shoulder_vertical_range_px": round(shoulder_vertical_range, 2),
          "debug_points": points,
        },
      }
    return None

  smoothed_points = _smooth_points(points)
  point_times = [float(point["time"]) for point in smoothed_points]
  if normalized_windows:
    rep_gap_by_index: dict[int, float] = {}
    for window in normalized_windows:
      rep_index = int(window.get("rep_index", 0))
      start = float(window["start"])
      end = float(window["end"])
      rep_times = [time for time in point_times if start <= time <= end]
      gap_boundaries = [start, *rep_times, end]
      rep_gap_by_index[rep_index] = max(
        (
          next_time - previous_time
          for previous_time, next_time in zip(gap_boundaries, gap_boundaries[1:])
        ),
        default=max(end - start, 0.0),
      )
    max_point_gap_seconds = max(rep_gap_by_index.values(), default=0.0)
    per_rep_coverage = [
      {
        **item,
        "max_point_gap_seconds": round(
          rep_gap_by_index.get(int(item["rep_index"]), 0.0),
          4,
        ),
      }
      for item in per_rep_coverage
    ]
  else:
    max_point_gap_seconds = max(
      (
        float(current["time"]) - float(previous["time"])
        for previous, current in zip(smoothed_points, smoothed_points[1:])
      ),
      default=0.0,
    )
  return {
    "barbellPath": {
      "available": True,
      "target": SLEEVE_END_TRACKING_TARGET,
      "source": TRACKING_SOURCE,
      "coverage": round(coverage, 3),
      "points": smoothed_points,
    },
    "diagnostics": {
      "available": True,
      "target": SLEEVE_END_TRACKING_TARGET,
      "source": TRACKING_SOURCE,
      "coverage": round(coverage, 3),
      "sampled_frame_count": len(samples),
      "detected_point_count": len(points) - interpolated_count,
      "interpolated_point_count": interpolated_count,
      "outlier_removed_count": outlier_removed_count,
      "sleeve_candidate_count": candidate_count,
      "tracklet_confirmation_count": tracklet_confirmation_count,
      "path_reset_count": path_reset_count,
      "stale_prior_expiration_count": stale_prior_expiration_count,
      "reacquisition_success_count": reacquisition_success_count,
      "reused_nearest_pose_frame_count": reused_nearest_pose_frame_count,
      "path_drift_rejection_count": path_drift_rejection_count,
      "anchor_drift_rejection_count": anchor_drift_rejection_count,
      "descriptor_bridge_count": descriptor_bridge_count,
      "max_point_gap_seconds": round(max_point_gap_seconds, 4),
      "per_rep_coverage": per_rep_coverage,
      "motion_correlation": round(motion_correlation, 3),
      "bar_vertical_range_px": round(point_vertical_range, 2),
      "shoulder_vertical_range_px": round(shoulder_vertical_range, 2),
      "selected_side": selected_side,
      "coordinate_space": {
        "width": width,
        "height": height,
        "source": "processed_frame",
      },
      "failure_reason": None,
    },
  }
