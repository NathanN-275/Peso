from __future__ import annotations

import copy
import math
from statistics import median
from typing import Any

from .metrics_calculator import clamp, point_for_side, select_tracking_side_for_clip


SQUAT_VALIDATION_JOINTS = ("shoulder", "hip", "knee", "ankle")
LOW_RELIABILITY_CONFIDENCE = 0.2
INTERPOLATED_CONFIDENCE = 0.48
SMOOTHED_CONFIDENCE_CAP = 0.72
SMOOTHING_WEIGHTS = {
  "shoulder": (0.32, 0.36, 0.32),
  "hip": (0.30, 0.40, 0.30),
  "knee": (0.15, 0.70, 0.15),
  "ankle": (0.10, 0.80, 0.10),
}
JOINT_JUMP_SCALE = {
  "shoulder": 0.22,
  "hip": 0.22,
  "knee": 0.30,
  "ankle": 0.36,
}
UPPER_BACK_RELATIVE_JUMP_SCALE = 0.16


def _distance(first: dict[str, float], second: dict[str, float]) -> float:
  return math.hypot(first["x"] - second["x"], first["y"] - second["y"])


def _median_point(points: list[dict[str, float]]) -> dict[str, float] | None:
  if not points:
    return None

  return {
    "x": median(point["x"] for point in points),
    "y": median(point["y"] for point in points),
    "z": median(point.get("z", 0.0) for point in points),
    "visibility": median(point.get("visibility", 0.0) for point in points),
  }


def _subject_height(frames: list[dict[str, Any]], side: str) -> float:
  heights: list[float] = []

  for frame in frames:
    points = [
      point_for_side(frame, side, joint)
      for joint in SQUAT_VALIDATION_JOINTS
      if point_for_side(frame, side, joint).get("visibility", 0.0) >= 0.35
    ]

    if len(points) >= 2:
      y_values = [point["y"] for point in points]
      heights.append(max(y_values) - min(y_values))

  return median(heights) if heights else 0.45


def _neighbor_median(
  frames: list[dict[str, Any]],
  *,
  frame_index: int,
  side: str,
  joint: str,
  radius: int = 2,
) -> dict[str, float] | None:
  points: list[dict[str, float]] = []

  start = max(0, frame_index - radius)
  end = min(len(frames), frame_index + radius + 1)

  for index in range(start, end):
    if index == frame_index:
      continue

    point = point_for_side(frames[index], side, joint)
    if point.get("visibility", 0.0) >= 0.35:
      points.append(point)

  return _median_point(points)


def _find_neighbor(
  frames: list[dict[str, Any]],
  invalid_keys: set[tuple[int, str]],
  *,
  frame_index: int,
  side: str,
  joint: str,
  direction: int,
  max_gap: int = 4,
) -> dict[str, float] | None:
  for offset in range(1, max_gap + 1):
    index = frame_index + (offset * direction)

    if index < 0 or index >= len(frames):
      return None
    if (index, joint) in invalid_keys:
      continue

    point = point_for_side(frames[index], side, joint)
    if point.get("visibility", 0.0) >= 0.35:
      return point

  return None


def _segment_lengths(frame: dict[str, Any], side: str) -> dict[str, float]:
  shoulder = point_for_side(frame, side, "shoulder")
  hip = point_for_side(frame, side, "hip")
  knee = point_for_side(frame, side, "knee")
  ankle = point_for_side(frame, side, "ankle")

  return {
    "torso": _distance(shoulder, hip),
    "thigh": _distance(hip, knee),
    "shin": _distance(knee, ankle),
  }


def _median_segment_lengths(frames: list[dict[str, Any]], side: str) -> dict[str, float]:
  segment_values: dict[str, list[float]] = {
    "torso": [],
    "thigh": [],
    "shin": [],
  }

  for frame in frames:
    points = [
      point_for_side(frame, side, joint)
      for joint in SQUAT_VALIDATION_JOINTS
    ]
    if min(point.get("visibility", 0.0) for point in points) < 0.35:
      continue

    for segment, length in _segment_lengths(frame, side).items():
      if length > 1e-6:
        segment_values[segment].append(length)

  return {
    segment: median(values) if values else 0.0
    for segment, values in segment_values.items()
  }


def _mark_invalid(
  invalid: dict[tuple[int, str], set[str]],
  frame_index: int,
  joint: str,
  reason: str,
) -> None:
  invalid.setdefault((frame_index, joint), set()).add(reason)


def _find_invalid_landmarks(
  frames: list[dict[str, Any]],
  *,
  side: str,
  subject_height: float,
) -> dict[tuple[int, str], set[str]]:
  invalid: dict[tuple[int, str], set[str]] = {}
  median_lengths = _median_segment_lengths(frames, side)
  isolated_chain_threshold = max(0.055, subject_height * 0.16)
  stable_chain_threshold = max(0.025, subject_height * 0.065)

  for frame_index, frame in enumerate(frames):
    for joint in SQUAT_VALIDATION_JOINTS:
      point = point_for_side(frame, side, joint)
      visibility = point.get("visibility", 0.0)

      if visibility < 0.35:
        _mark_invalid(invalid, frame_index, joint, "low_visibility")
        continue

      jump_threshold = max(0.07, subject_height * JOINT_JUMP_SCALE[joint])
      if 0 < frame_index < len(frames) - 1:
        previous_point = point_for_side(frames[frame_index - 1], side, joint)
        following_point = point_for_side(frames[frame_index + 1], side, joint)

        if min(
          previous_point.get("visibility", 0.0),
          following_point.get("visibility", 0.0),
        ) >= 0.35:
          midpoint = {
            "x": (previous_point["x"] + following_point["x"]) / 2,
            "y": (previous_point["y"] + following_point["y"]) / 2,
          }
          jump_distance = _distance(point, midpoint)
          horizontal_jump = abs(point["x"] - midpoint["x"])
          if (
            jump_distance > jump_threshold
            and (joint not in {"shoulder", "hip"} or horizontal_jump > jump_threshold * 0.70)
            and _distance(previous_point, following_point) < jump_threshold
          ):
            _mark_invalid(invalid, frame_index, joint, "temporal_jump")

    lengths = _segment_lengths(frame, side)
    shin_length = max(lengths["shin"], 1e-6)

    if lengths["thigh"] / shin_length > 2.1 or lengths["thigh"] / shin_length < 0.28:
      _mark_invalid(invalid, frame_index, "hip", "implausible_thigh_length")

    if lengths["torso"] / shin_length > 2.4 or lengths["torso"] / shin_length < 0.22:
      _mark_invalid(invalid, frame_index, "shoulder", "implausible_torso_length")

    if median_lengths["thigh"] > 0:
      thigh_ratio = lengths["thigh"] / median_lengths["thigh"]
      if thigh_ratio > 1.85 or thigh_ratio < 0.42:
        _mark_invalid(invalid, frame_index, "hip", "thigh_length_inconsistent")

    if median_lengths["torso"] > 0:
      torso_ratio = lengths["torso"] / median_lengths["torso"]
      if torso_ratio > 2.45 or torso_ratio < 0.32:
        _mark_invalid(invalid, frame_index, "shoulder", "torso_length_inconsistent")

    shoulder = point_for_side(frame, side, "shoulder")
    hip = point_for_side(frame, side, "hip")
    knee = point_for_side(frame, side, "knee")
    ankle = point_for_side(frame, side, "ankle")

    if hip["y"] < shoulder["y"] - 0.10:
      _mark_invalid(invalid, frame_index, "hip", "hip_above_shoulder")
    if ankle["y"] < knee["y"] + 0.03:
      _mark_invalid(invalid, frame_index, "ankle", "ankle_above_knee")

    if 0 < frame_index < len(frames) - 1:
      previous_frame = frames[frame_index - 1]
      following_frame = frames[frame_index + 1]
      previous_knee = point_for_side(previous_frame, side, "knee")
      following_knee = point_for_side(following_frame, side, "knee")
      previous_ankle = point_for_side(previous_frame, side, "ankle")
      following_ankle = point_for_side(following_frame, side, "ankle")
      chain_movement = (
        _distance(previous_knee, following_knee)
        + _distance(previous_ankle, following_ankle)
      ) / 2

      for joint in ("shoulder", "hip"):
        point = point_for_side(frame, side, joint)
        previous_point = point_for_side(previous_frame, side, joint)
        following_point = point_for_side(following_frame, side, joint)
        if min(
          point.get("visibility", 0.0),
          previous_point.get("visibility", 0.0),
          following_point.get("visibility", 0.0),
          knee.get("visibility", 0.0),
          ankle.get("visibility", 0.0),
          previous_knee.get("visibility", 0.0),
          previous_ankle.get("visibility", 0.0),
          following_knee.get("visibility", 0.0),
          following_ankle.get("visibility", 0.0),
        ) < 0.35:
          continue

        midpoint = {
          "x": (previous_point["x"] + following_point["x"]) / 2,
          "y": (previous_point["y"] + following_point["y"]) / 2,
        }
        if (
          _distance(point, midpoint) > isolated_chain_threshold
          and abs(point["x"] - midpoint["x"]) > isolated_chain_threshold * 0.70
          and _distance(previous_point, following_point) < isolated_chain_threshold
          and chain_movement < stable_chain_threshold
        ):
          _mark_invalid(invalid, frame_index, joint, "isolated_chain_jump")

      previous_shoulder = point_for_side(previous_frame, side, "shoulder")
      following_shoulder = point_for_side(following_frame, side, "shoulder")
      previous_hip = point_for_side(previous_frame, side, "hip")
      following_hip = point_for_side(following_frame, side, "hip")
      if min(
        shoulder.get("visibility", 0.0),
        hip.get("visibility", 0.0),
        previous_shoulder.get("visibility", 0.0),
        following_shoulder.get("visibility", 0.0),
        previous_hip.get("visibility", 0.0),
        following_hip.get("visibility", 0.0),
        previous_knee.get("visibility", 0.0),
        previous_ankle.get("visibility", 0.0),
        following_knee.get("visibility", 0.0),
        following_ankle.get("visibility", 0.0),
      ) >= 0.35:
        previous_relative = {
          "x": previous_shoulder["x"] - previous_hip["x"],
          "y": previous_shoulder["y"] - previous_hip["y"],
        }
        following_relative = {
          "x": following_shoulder["x"] - following_hip["x"],
          "y": following_shoulder["y"] - following_hip["y"],
        }
        current_relative = {
          "x": shoulder["x"] - hip["x"],
          "y": shoulder["y"] - hip["y"],
        }
        expected_relative = {
          "x": (previous_relative["x"] + following_relative["x"]) / 2,
          "y": (previous_relative["y"] + following_relative["y"]) / 2,
        }
        expected_hip = {
          "x": (previous_hip["x"] + following_hip["x"]) / 2,
          "y": (previous_hip["y"] + following_hip["y"]) / 2,
        }
        relative_jump_threshold = max(0.055, subject_height * UPPER_BACK_RELATIVE_JUMP_SCALE)
        hip_motion = _distance(previous_hip, following_hip)
        if (
          _distance(current_relative, expected_relative) > relative_jump_threshold
          and _distance(previous_relative, following_relative) < relative_jump_threshold
          and _distance(hip, expected_hip) < max(0.045, subject_height * 0.12)
          and hip_motion < max(0.055, subject_height * 0.16)
          and chain_movement < max(stable_chain_threshold * 1.4, subject_height * 0.10)
        ):
          _mark_invalid(invalid, frame_index, "shoulder", "upper_back_relative_jump")

  return invalid


def _valid_neighbor_points(
  frames: list[dict[str, Any]],
  invalid_keys: set[tuple[int, str]],
  *,
  frame_index: int,
  side: str,
  joint: str,
) -> tuple[dict[str, float] | None, dict[str, float] | None]:
  previous = None
  following = None

  if frame_index > 0 and (frame_index - 1, joint) not in invalid_keys:
    candidate = point_for_side(frames[frame_index - 1], side, joint)
    if candidate.get("visibility", 0.0) >= 0.35:
      previous = candidate

  if frame_index < len(frames) - 1 and (frame_index + 1, joint) not in invalid_keys:
    candidate = point_for_side(frames[frame_index + 1], side, joint)
    if candidate.get("visibility", 0.0) >= 0.35:
      following = candidate

  return previous, following


def _apply_smoothing(
  frames: list[dict[str, Any]],
  invalid_keys: set[tuple[int, str]],
  *,
  side: str,
  subject_height: float,
) -> tuple[int, int]:
  smoothed_count = 0
  hysteresis_count = 0
  smoothing_limit = max(0.08, subject_height * 0.18)
  source_frames = copy.deepcopy(frames)

  for frame_index in range(len(frames)):
    for joint in SQUAT_VALIDATION_JOINTS:
      if (frame_index, joint) in invalid_keys:
        continue

      current = point_for_side(source_frames[frame_index], side, joint)
      if current.get("visibility", 0.0) < 0.35:
        continue

      previous, following = _valid_neighbor_points(
        source_frames,
        invalid_keys,
        frame_index=frame_index,
        side=side,
        joint=joint,
      )
      if not previous or not following:
        continue

      is_vertical_extremum = (
        abs(current["y"] - previous["y"]) > 0.05
        and abs(current["y"] - following["y"]) > 0.05
        and (
          (current["y"] > previous["y"] and current["y"] > following["y"])
          or (current["y"] < previous["y"] and current["y"] < following["y"])
        )
      )

      if is_vertical_extremum:
        continue

      neighbor_midpoint = {
        "x": (previous["x"] + following["x"]) / 2,
        "y": (previous["y"] + following["y"]) / 2,
        "z": (previous.get("z", 0.0) + following.get("z", 0.0)) / 2,
        "visibility": min(previous.get("visibility", 0.0), following.get("visibility", 0.0)),
      }
      target = point_for_side(frames[frame_index], side, joint)

      if _distance(current, neighbor_midpoint) > smoothing_limit:
        hysteresis_count += 1
        target["x"] = neighbor_midpoint["x"]
        target["y"] = neighbor_midpoint["y"]
        target["z"] = neighbor_midpoint["z"]
        target["visibility"] = min(
          target.get("visibility", 0.0),
          neighbor_midpoint.get("visibility", 0.0),
          INTERPOLATED_CONFIDENCE,
        )
        target["tracking_state"] = "estimated"
        smoothed_count += 1
        continue

      previous_weight, current_weight, following_weight = SMOOTHING_WEIGHTS[joint]
      smoothed_x = (
        (previous["x"] * previous_weight)
        + (current["x"] * current_weight)
        + (following["x"] * following_weight)
      )
      smoothed_y = (
        (previous["y"] * previous_weight)
        + (current["y"] * current_weight)
        + (following["y"] * following_weight)
      )

      smoothed_point = {
        "x": smoothed_x,
        "y": smoothed_y,
      }

      if _distance(current, smoothed_point) <= 0.002:
        continue

      target["x"] = smoothed_x
      target["y"] = smoothed_y
      target["z"] = (
        (previous.get("z", 0.0) * previous_weight)
        + (current.get("z", 0.0) * current_weight)
        + (following.get("z", 0.0) * following_weight)
      )
      target["visibility"] = min(target.get("visibility", 0.0), SMOOTHED_CONFIDENCE_CAP)
      if target.get("tracking_state") != "reference":
        target["tracking_state"] = "estimated"
      smoothed_count += 1

  return smoothed_count, hysteresis_count


def validate_squat_pose_frames(
  frames: list[dict[str, Any]],
  *,
  selected_side_override: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  # Downgrade or interpolate squat-critical landmarks that are anatomically or temporally implausible.
  if not frames:
    return frames, {
      "selected_side": None,
      "upper_back_proxy_landmark": "shoulder",
      "corrected_landmark_count": 0,
      "smoothed_landmark_count": 0,
      "hysteresis_rejected_jump_count": 0,
      "occluded_landmark_count": 0,
      "interpolated_landmark_count": 0,
      "rejected_landmark_count": 0,
      "unreliable_landmarks": [],
    }

  automatic_side, tracking_confidence = select_tracking_side_for_clip(frames)
  selected_side = selected_side_override if selected_side_override in {"left", "right"} else automatic_side
  subject_height = _subject_height(frames, selected_side)
  invalid = _find_invalid_landmarks(
    frames,
    side=selected_side,
    subject_height=subject_height,
  )
  invalid_keys = set(invalid)
  validated_frames = copy.deepcopy(frames)
  unreliable_landmarks: list[dict[str, Any]] = []
  corrected_count = 0
  interpolated_count = 0
  rejected_count = 0
  occluded_count = 0

  for frame_index, joint in sorted(invalid_keys):
    target = point_for_side(validated_frames[frame_index], selected_side, joint)
    previous = _find_neighbor(
      frames,
      invalid_keys,
      frame_index=frame_index,
      side=selected_side,
      joint=joint,
      direction=-1,
    )
    following = _find_neighbor(
      frames,
      invalid_keys,
      frame_index=frame_index,
      side=selected_side,
      joint=joint,
      direction=1,
    )
    reasons = sorted(invalid[(frame_index, joint)])
    if "low_visibility" in reasons:
      occluded_count += 1

    if previous and following:
      target["x"] = (previous["x"] + following["x"]) / 2
      target["y"] = (previous["y"] + following["y"]) / 2
      target["z"] = (previous.get("z", 0.0) + following.get("z", 0.0)) / 2
      target["visibility"] = min(
        max(target.get("visibility", 0.0), INTERPOLATED_CONFIDENCE),
        INTERPOLATED_CONFIDENCE,
      )
      corrected_count += 1
      interpolated_count += 1
      target["tracking_state"] = "estimated"
      status = "interpolated"
    else:
      target["visibility"] = min(target.get("visibility", 0.0), LOW_RELIABILITY_CONFIDENCE)
      target["tracking_state"] = "estimated"
      rejected_count += 1
      status = "rejected"

    unreliable_landmarks.append(
      {
        "frame_index": frame_index,
        "timestamp_ms": frames[frame_index].get("timestamp_ms"),
        "side": selected_side,
        "joint": joint,
        "status": status,
        "reasons": reasons,
      }
    )

  smoothed_count, hysteresis_count = _apply_smoothing(
    validated_frames,
    invalid_keys,
    side=selected_side,
    subject_height=subject_height,
  )

  return validated_frames, {
    "selected_side": selected_side,
    "selected_side_overridden": selected_side != automatic_side,
    "upper_back_proxy_landmark": "shoulder",
    "upper_back_proxy_semantics": "displayed_as_upper_back",
    "tracking_side_confidence": tracking_confidence,
    "subject_height": round(subject_height, 3),
    "corrected_landmark_count": corrected_count,
    "smoothed_landmark_count": smoothed_count,
    "hysteresis_rejected_jump_count": hysteresis_count,
    "occluded_landmark_count": occluded_count,
    "interpolated_landmark_count": interpolated_count,
    "rejected_landmark_count": rejected_count,
    "unreliable_landmarks": unreliable_landmarks,
    "quality_score_penalty": round(
      clamp((corrected_count + rejected_count) / max(len(frames) * len(SQUAT_VALIDATION_JOINTS), 1), 0.0, 1.0),
      3,
    ),
  }
