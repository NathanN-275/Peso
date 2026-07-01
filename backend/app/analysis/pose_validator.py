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


def is_body_point_occluded_by_plate(
  point_px: tuple[float, float],
  plate_center_px: tuple[float, float],
  plate_radius_px: float,
  margin_px: float = 0.0,
) -> bool:
  return math.hypot(point_px[0] - plate_center_px[0], point_px[1] - plate_center_px[1]) <= (
    float(plate_radius_px) + float(margin_px)
  )


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


def _median_ankle_relative_offsets(
  frames: list[dict[str, Any]],
  side: str,
) -> dict[str, dict[str, float]]:
  offsets: dict[str, dict[str, list[float]]] = {
    joint: {"x": [], "y": []}
    for joint in ("shoulder", "hip", "knee")
  }

  for frame in frames:
    ankle = point_for_side(frame, side, "ankle")
    if ankle.get("visibility", 0.0) < 0.35:
      continue
    for joint in offsets:
      point = point_for_side(frame, side, joint)
      if point.get("visibility", 0.0) < 0.35:
        continue
      offsets[joint]["x"].append(point["x"] - ankle["x"])
      offsets[joint]["y"].append(point["y"] - ankle["y"])

  return {
    joint: {
      "x": median(values["x"]) if values["x"] else 0.0,
      "y": median(values["y"]) if values["y"] else 0.0,
    }
    for joint, values in offsets.items()
  }


def _median_joint_vector(
  frames: list[dict[str, Any]],
  side: str,
  *,
  from_joint: str,
  to_joint: str,
) -> dict[str, float] | None:
  x_values: list[float] = []
  y_values: list[float] = []
  for frame in frames:
    first = point_for_side(frame, side, from_joint)
    second = point_for_side(frame, side, to_joint)
    if min(first.get("visibility", 0.0), second.get("visibility", 0.0)) < 0.35:
      continue
    x_values.append(second["x"] - first["x"])
    y_values.append(second["y"] - first["y"])
  if not x_values or not y_values:
    return None
  return {
    "x": median(x_values),
    "y": median(y_values),
  }


def _mark_invalid(
  invalid: dict[tuple[int, str], set[str]],
  frame_index: int,
  joint: str,
  reason: str,
) -> None:
  invalid.setdefault((frame_index, joint), set()).add(reason)


def _frame_dimensions(frame: dict[str, Any]) -> tuple[float, float]:
  width = frame.get("processed_frame_width") or frame.get("frame_width") or 1.0
  height = frame.get("processed_frame_height") or frame.get("frame_height") or 1.0
  try:
    width = float(width)
    height = float(height)
  except (TypeError, ValueError):
    return 1.0, 1.0
  return max(width, 1.0), max(height, 1.0)


def _point_to_px(point: dict[str, float], *, width: float, height: float) -> tuple[float, float]:
  return float(point["x"]) * width, float(point["y"]) * height


def _occluder_for_frame(
  barbell_occluders_by_frame: dict[int, dict[str, float]] | None,
  *,
  frame: dict[str, Any],
  frame_index: int,
) -> dict[str, float] | None:
  if not barbell_occluders_by_frame:
    return None
  source_index = frame.get("source_frame_index")
  keys = []
  if isinstance(source_index, (int, float)):
    keys.append(int(source_index))
  keys.append(frame_index)
  for key in keys:
    occluder = barbell_occluders_by_frame.get(key)
    if isinstance(occluder, dict):
      return occluder
  return None


def _occluder_px(
  occluder: dict[str, float],
  *,
  width: float,
  height: float,
) -> tuple[tuple[float, float], float] | None:
  x = occluder.get("x")
  y = occluder.get("y")
  radius = occluder.get("radius")
  if not all(isinstance(value, (int, float)) for value in (x, y, radius)):
    return None
  if not all(math.isfinite(float(value)) for value in (x, y, radius)):
    return None
  center_x = float(x)
  center_y = float(y)
  radius_px = float(radius)
  if 0.0 <= center_x <= 1.0 and 0.0 <= center_y <= 1.0:
    center_x *= width
    center_y *= height
  if 0.0 <= radius_px <= 1.0:
    radius_px *= max(width, height)
  if radius_px <= 0:
    return None
  return (center_x, center_y), radius_px


def _find_invalid_landmarks(
  frames: list[dict[str, Any]],
  *,
  side: str,
  subject_height: float,
  barbell_occluders_by_frame: dict[int, dict[str, float]] | None = None,
) -> dict[tuple[int, str], set[str]]:
  invalid: dict[tuple[int, str], set[str]] = {}
  median_lengths = _median_segment_lengths(frames, side)
  reference_offsets = _median_ankle_relative_offsets(frames, side)
  isolated_chain_threshold = max(0.055, subject_height * 0.16)
  stable_chain_threshold = max(0.025, subject_height * 0.065)
  direct_side_offset_threshold = max(0.075, subject_height * 0.13)

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

    occluder = _occluder_for_frame(
      barbell_occluders_by_frame,
      frame=frame,
      frame_index=frame_index,
    )
    if occluder:
      width, height = _frame_dimensions(frame)
      occluder_geometry = _occluder_px(occluder, width=width, height=height)
      if occluder_geometry is not None:
        plate_center_px, plate_radius_px = occluder_geometry
        margin_px = max(4.0, max(width, height) * 0.008)
        for joint in ("shoulder", "hip", "knee"):
          point = point_for_side(frame, side, joint)
          if point.get("visibility", 0.0) < 0.35:
            continue
          if is_body_point_occluded_by_plate(
            _point_to_px(point, width=width, height=height),
            plate_center_px,
            plate_radius_px,
            margin_px,
          ):
            _mark_invalid(invalid, frame_index, joint, "barbell_plate_occlusion")

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

    reference_displacements: list[tuple[str, float, float]] = []
    if ankle.get("visibility", 0.0) >= 0.35:
      for joint in ("shoulder", "hip", "knee"):
        point = point_for_side(frame, side, joint)
        reference_offset = reference_offsets.get(joint) or {}
        if (
          point.get("visibility", 0.0) < 0.35
          or not reference_offset
        ):
          continue
        dx = (point["x"] - ankle["x"]) - reference_offset["x"]
        dy = (point["y"] - ankle["y"]) - reference_offset["y"]
        displacement = math.hypot(dx, dy)
        if (
          displacement > direct_side_offset_threshold
          and abs(dx) > direct_side_offset_threshold * 0.75
        ):
          reference_displacements.append((joint, dx, displacement))

    if len(reference_displacements) >= 2:
      positive = sum(1 for _, dx, _ in reference_displacements if dx > 0)
      negative = sum(1 for _, dx, _ in reference_displacements if dx < 0)
      if max(positive, negative) >= 2:
        displacement_by_joint = {
          joint: displacement
          for joint, _dx, displacement in reference_displacements
        }
        if (
          "shoulder" in displacement_by_joint
          and "hip" in displacement_by_joint
          and abs(displacement_by_joint["shoulder"] - displacement_by_joint["hip"]) < direct_side_offset_threshold * 1.25
        ) or (
          "hip" in displacement_by_joint
          and "knee" in displacement_by_joint
          and abs(displacement_by_joint["hip"] - displacement_by_joint["knee"]) < direct_side_offset_threshold * 1.25
        ):
          for joint, _, _ in reference_displacements:
            _mark_invalid(invalid, frame_index, joint, "direct_side_chain_jumble")

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

      previous_ankle = point_for_side(previous_frame, side, "ankle")
      following_ankle = point_for_side(following_frame, side, "ankle")
      current_ankle = point_for_side(frame, side, "ankle")
      ankle_midpoint = {
        "x": (previous_ankle["x"] + following_ankle["x"]) / 2,
        "y": (previous_ankle["y"] + following_ankle["y"]) / 2,
      }
      chain_jumble_threshold = max(0.06, subject_height * 0.14)
      ankle_is_stable = (
        min(
          current_ankle.get("visibility", 0.0),
          previous_ankle.get("visibility", 0.0),
          following_ankle.get("visibility", 0.0),
        ) >= 0.35
        and _distance(current_ankle, ankle_midpoint) < max(0.045, subject_height * 0.10)
        and _distance(previous_ankle, following_ankle) < max(0.055, subject_height * 0.12)
      )
      coherent_offsets: list[tuple[str, float, float]] = []
      for joint in ("shoulder", "hip", "knee"):
        point = point_for_side(frame, side, joint)
        previous_point = point_for_side(previous_frame, side, joint)
        following_point = point_for_side(following_frame, side, joint)
        if min(
          point.get("visibility", 0.0),
          previous_point.get("visibility", 0.0),
          following_point.get("visibility", 0.0),
        ) < 0.35:
          continue
        midpoint = {
          "x": (previous_point["x"] + following_point["x"]) / 2,
          "y": (previous_point["y"] + following_point["y"]) / 2,
        }
        dx = point["x"] - midpoint["x"]
        jump_distance = _distance(point, midpoint)
        if (
          jump_distance > chain_jumble_threshold
          and abs(dx) > chain_jumble_threshold * 0.60
          and _distance(previous_point, following_point) < max(0.055, subject_height * 0.12)
        ):
          coherent_offsets.append((joint, dx, jump_distance))

      if ankle_is_stable and len(coherent_offsets) >= 2:
        positive = sum(1 for _, dx, _ in coherent_offsets if dx > 0)
        negative = sum(1 for _, dx, _ in coherent_offsets if dx < 0)
        if max(positive, negative) >= 2:
          for joint, _, _ in coherent_offsets:
            _mark_invalid(invalid, frame_index, joint, "chain_jumble")

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


def _trusted_current_point(
  frames: list[dict[str, Any]],
  invalid_keys: set[tuple[int, str]],
  *,
  frame_index: int,
  side: str,
  joint: str,
) -> dict[str, float] | None:
  if (frame_index, joint) in invalid_keys:
    return None
  point = point_for_side(frames[frame_index], side, joint)
  if point.get("visibility", 0.0) < 0.35:
    return None
  return point


def _kinematic_recovery_point(
  frames: list[dict[str, Any]],
  invalid_keys: set[tuple[int, str]],
  *,
  frame_index: int,
  side: str,
  joint: str,
  median_lengths: dict[str, float],
  torso_vector: dict[str, float] | None,
  reference_offsets: dict[str, dict[str, float]],
) -> dict[str, float] | None:
  hip = _trusted_current_point(frames, invalid_keys, frame_index=frame_index, side=side, joint="hip")
  shoulder = _trusted_current_point(frames, invalid_keys, frame_index=frame_index, side=side, joint="shoulder")
  knee = _trusted_current_point(frames, invalid_keys, frame_index=frame_index, side=side, joint="knee")
  ankle = _trusted_current_point(frames, invalid_keys, frame_index=frame_index, side=side, joint="ankle")

  def accepted(point: dict[str, float]) -> dict[str, float] | None:
    if not (0.0 <= point["x"] <= 1.0 and 0.0 <= point["y"] <= 1.0):
      return None
    return {
      "x": point["x"],
      "y": point["y"],
      "z": point.get("z", 0.0),
      "visibility": min(max(point.get("visibility", INTERPOLATED_CONFIDENCE), LOW_RELIABILITY_CONFIDENCE), INTERPOLATED_CONFIDENCE),
    }

  if joint == "shoulder" and hip is not None and torso_vector is not None:
    return accepted({
      "x": hip["x"] + torso_vector["x"],
      "y": hip["y"] + torso_vector["y"],
      "z": hip.get("z", 0.0),
      "visibility": INTERPOLATED_CONFIDENCE,
    })

  if joint == "hip" and shoulder is not None and torso_vector is not None:
    candidate = {
      "x": shoulder["x"] - torso_vector["x"],
      "y": shoulder["y"] - torso_vector["y"],
      "z": shoulder.get("z", 0.0),
      "visibility": INTERPOLATED_CONFIDENCE,
    }
    if knee is None:
      return accepted(candidate)
    thigh_length = median_lengths.get("thigh") or 0.0
    if thigh_length <= 0 or 0.45 <= (_distance(candidate, knee) / max(thigh_length, 1e-6)) <= 1.8:
      return accepted(candidate)
    return None

  if joint != "knee" or hip is None or ankle is None:
    return None

  thigh_length = median_lengths.get("thigh") or 0.0
  shin_length = median_lengths.get("shin") or 0.0
  if thigh_length <= 1e-6 or shin_length <= 1e-6:
    return None
  dx = ankle["x"] - hip["x"]
  dy = ankle["y"] - hip["y"]
  distance = math.hypot(dx, dy)
  if distance <= 1e-6 or distance > (thigh_length + shin_length) * 1.20:
    return None
  unit_x = dx / distance
  unit_y = dy / distance
  projected = ((thigh_length * thigh_length) - (shin_length * shin_length) + (distance * distance)) / (2 * distance)
  projected = max(min(projected, thigh_length), 0.0)
  bend_height = math.sqrt(max((thigh_length * thigh_length) - (projected * projected), 0.0))
  base = {
    "x": hip["x"] + (unit_x * projected),
    "y": hip["y"] + (unit_y * projected),
  }
  perpendicular = (-unit_y, unit_x)
  candidates = [
    {
      "x": base["x"] + (perpendicular[0] * bend_height),
      "y": base["y"] + (perpendicular[1] * bend_height),
      "z": hip.get("z", 0.0),
      "visibility": INTERPOLATED_CONFIDENCE,
    },
    {
      "x": base["x"] - (perpendicular[0] * bend_height),
      "y": base["y"] - (perpendicular[1] * bend_height),
      "z": hip.get("z", 0.0),
      "visibility": INTERPOLATED_CONFIDENCE,
    },
  ]
  hip_offset = reference_offsets.get("hip") or {}
  knee_offset = reference_offsets.get("knee") or {}
  reference_cross = 0.0
  if hip_offset and knee_offset:
    ankle_to_hip = (hip_offset["x"], hip_offset["y"])
    hip_to_knee = (knee_offset["x"] - hip_offset["x"], knee_offset["y"] - hip_offset["y"])
    reference_cross = ((-ankle_to_hip[0]) * hip_to_knee[1]) - ((-ankle_to_hip[1]) * hip_to_knee[0])

  def candidate_score(candidate: dict[str, float]) -> float:
    cross = (dx * (candidate["y"] - hip["y"])) - (dy * (candidate["x"] - hip["x"]))
    bend_penalty = 0.0 if reference_cross == 0 or cross == 0 or (cross > 0) == (reference_cross > 0) else 0.2
    current = point_for_side(frames[frame_index], side, "knee")
    current_penalty = _distance(candidate, current) if current.get("visibility", 0.0) >= 0.20 else 0.0
    vertical_penalty = 0.1 if candidate["y"] < min(hip["y"], ankle["y"]) - 0.08 else 0.0
    return bend_penalty + current_penalty + vertical_penalty

  return accepted(min(candidates, key=candidate_score))


def _mark_visual_only(
  target: dict[str, Any],
  reasons: list[str],
) -> None:
  primary_reason = "barbell_plate_occlusion" if "barbell_plate_occlusion" in reasons else reasons[0]
  target["accepted_source"] = "gap"
  target["chain_valid"] = False
  target["visual_only"] = True
  target["chain_failure_reason"] = primary_reason
  if "occlusion" in primary_reason or "plate" in primary_reason:
    target["occlusion_reason"] = primary_reason


def _mark_connected_estimate(
  target: dict[str, Any],
  *,
  accepted_source: str,
) -> None:
  target["accepted_source"] = accepted_source
  target["chain_valid"] = True
  target["visual_only"] = False
  target.pop("chain_failure_reason", None)


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
  barbell_occluders_by_frame: dict[int, dict[str, float]] | None = None,
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
      "barbell_plate_occlusion_count": 0,
      "kinematic_estimated_landmark_count": 0,
      "visual_only_landmark_count": 0,
      "interpolated_landmark_count": 0,
      "rejected_landmark_count": 0,
      "unreliable_landmarks": [],
    }

  automatic_side, tracking_confidence = select_tracking_side_for_clip(frames)
  selected_side = selected_side_override if selected_side_override in {"left", "right"} else automatic_side
  subject_height = _subject_height(frames, selected_side)
  median_lengths = _median_segment_lengths(frames, selected_side)
  reference_offsets = _median_ankle_relative_offsets(frames, selected_side)
  torso_vector = _median_joint_vector(frames, selected_side, from_joint="hip", to_joint="shoulder")
  invalid = _find_invalid_landmarks(
    frames,
    side=selected_side,
    subject_height=subject_height,
    barbell_occluders_by_frame=barbell_occluders_by_frame,
  )
  invalid_keys = set(invalid)
  validated_frames = copy.deepcopy(frames)
  unreliable_landmarks: list[dict[str, Any]] = []
  corrected_count = 0
  interpolated_count = 0
  rejected_count = 0
  occluded_count = 0
  barbell_plate_occlusion_count = 0
  kinematic_estimated_count = 0
  visual_only_count = 0

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
    if "barbell_plate_occlusion" in reasons:
      occluded_count += 1
      barbell_plate_occlusion_count += 1

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
      _mark_connected_estimate(target, accepted_source="interpolated")
      status = "interpolated"
    else:
      recovery = _kinematic_recovery_point(
        frames,
        invalid_keys,
        frame_index=frame_index,
        side=selected_side,
        joint=joint,
        median_lengths=median_lengths,
        torso_vector=torso_vector,
        reference_offsets=reference_offsets,
      )
      if recovery is not None:
        target["x"] = recovery["x"]
        target["y"] = recovery["y"]
        target["z"] = recovery.get("z", target.get("z", 0.0))
        target["visibility"] = min(
          max(recovery.get("visibility", INTERPOLATED_CONFIDENCE), INTERPOLATED_CONFIDENCE),
          INTERPOLATED_CONFIDENCE,
        )
        target["tracking_state"] = "estimated"
        _mark_connected_estimate(target, accepted_source="kinematic_estimate")
        corrected_count += 1
        kinematic_estimated_count += 1
        status = "kinematic_estimate"
      else:
        target["visibility"] = min(target.get("visibility", 0.0), LOW_RELIABILITY_CONFIDENCE)
        target["tracking_state"] = "estimated"
        _mark_visual_only(target, reasons)
        rejected_count += 1
        visual_only_count += 1
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
    "barbell_plate_occlusion_count": barbell_plate_occlusion_count,
    "kinematic_estimated_landmark_count": kinematic_estimated_count,
    "visual_only_landmark_count": visual_only_count,
    "interpolated_landmark_count": interpolated_count,
    "rejected_landmark_count": rejected_count,
    "unreliable_landmarks": unreliable_landmarks,
    "quality_score_penalty": round(
      clamp((corrected_count + rejected_count) / max(len(frames) * len(SQUAT_VALIDATION_JOINTS), 1), 0.0, 1.0),
      3,
    ),
  }
