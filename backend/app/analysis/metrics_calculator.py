from __future__ import annotations

import math
from typing import Any


Point = dict[str, float]


def clamp(value: float, minimum: float, maximum: float) -> float:
  # Keep derived scores inside a predictable range.
  return max(minimum, min(maximum, value))


def average_visibility(frame: dict[str, Any], side: str) -> float:
  # Average the major joints on one side of the body.
  landmark_names = (
    f"{side}_shoulder",
    f"{side}_hip",
    f"{side}_knee",
    f"{side}_ankle",
  )
  visibilities = [frame["landmarks"][name]["visibility"] for name in landmark_names]
  return sum(visibilities) / len(visibilities)


def average_clip_visibility(frames: list[dict[str, Any]], side: str) -> float:
  # Aggregate visibility across the whole clip.
  if not frames:
    return 0.0

  return sum(average_visibility(frame, side) for frame in frames) / len(frames)


def select_tracking_side_for_clip(frames: list[dict[str, Any]]) -> tuple[str, float]:
  # Choose whichever body side is tracked more reliably.
  left_visibility = average_clip_visibility(frames, "left")
  right_visibility = average_clip_visibility(frames, "right")
  selected_side = "left" if left_visibility >= right_visibility else "right"
  stronger_visibility = max(left_visibility, right_visibility)
  weaker_visibility = min(left_visibility, right_visibility)
  confidence = (stronger_visibility - weaker_visibility) / max(stronger_visibility, 1e-6)
  return selected_side, round(clamp(confidence, 0.0, 1.0), 3)


def select_tracking_side(frame: dict[str, Any]) -> str:
  # Pick the stronger side for a single frame.
  left_visibility = average_visibility(frame, "left")
  right_visibility = average_visibility(frame, "right")
  return "left" if left_visibility >= right_visibility else "right"


def point_for_side(frame: dict[str, Any], side: str, joint: str) -> Point:
  # Read one joint for the selected side.
  return frame["landmarks"][f"{side}_{joint}"]


def blended_point(frame: dict[str, Any], joint: str) -> Point:
  # Blend left and right landmarks when both are usable.
  left = frame["landmarks"][f"left_{joint}"]
  right = frame["landmarks"][f"right_{joint}"]
  left_weight = max(left["visibility"], 0.0)
  right_weight = max(right["visibility"], 0.0)
  total_weight = left_weight + right_weight

  if total_weight <= 1e-6:
    return left

  return {
    "x": ((left["x"] * left_weight) + (right["x"] * right_weight)) / total_weight,
    "y": ((left["y"] * left_weight) + (right["y"] * right_weight)) / total_weight,
    "z": ((left["z"] * left_weight) + (right["z"] * right_weight)) / total_weight,
    "visibility": max(left_weight, right_weight),
  }


def torso_angle_from_vertical(shoulder: Point, hip: Point) -> float:
  # Measure how far the torso tilts from upright.
  dx = shoulder["x"] - hip["x"]
  dy = shoulder["y"] - hip["y"]
  return abs(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))


def joint_angle(a: Point, b: Point, c: Point) -> float:
  # Compute the angle at the middle joint.
  ab_x = a["x"] - b["x"]
  ab_y = a["y"] - b["y"]
  cb_x = c["x"] - b["x"]
  cb_y = c["y"] - b["y"]
  dot = (ab_x * cb_x) + (ab_y * cb_y)
  ab_length = math.hypot(ab_x, ab_y)
  cb_length = math.hypot(cb_x, cb_y)

  if ab_length <= 1e-6 or cb_length <= 1e-6:
    return 180.0

  cosine = clamp(dot / (ab_length * cb_length), -1.0, 1.0)
  return abs(math.degrees(math.acos(cosine)))


def knee_flexion_score(hip: Point, knee: Point, ankle: Point) -> float:
  # Convert knee angle into a squat-friendly score.
  angle = joint_angle(hip, knee, ankle)
  return clamp((175.0 - angle) / 95.0, 0.0, 1.0)


def hip_flexion_score(shoulder: Point, hip: Point, knee: Point) -> float:
  # Convert hip angle into a normalized flexion score.
  angle = joint_angle(shoulder, hip, knee)
  return clamp((180.0 - angle) / 95.0, 0.0, 1.0)


def hip_depth_ratio(shoulder: Point, hip: Point, ankle: Point) -> float:
  # Estimate squat depth from hip position relative to the ankle.
  denominator = max(abs(ankle["y"] - shoulder["y"]), 1e-6)
  return (hip["y"] - shoulder["y"]) / denominator


def squat_depth_score(hip: Point, knee: Point, ankle: Point) -> float:
  # Score how deep the squat bottom position is.
  shin_length = max(abs(ankle["y"] - knee["y"]), 1e-6)
  depth_ratio = (hip["y"] - knee["y"]) / shin_length
  return round(clamp(0.55 + (depth_ratio * 0.9), 0.0, 1.0), 3)


def torso_angle_change(start_angle: float, bottom_angle: float) -> float:
  # Compare torso lean at the start and bottom of the rep.
  return round(bottom_angle - start_angle, 2)
