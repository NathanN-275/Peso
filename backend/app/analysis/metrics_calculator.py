from __future__ import annotations

import math
from typing import Any


Point = dict[str, float]


def clamp(value: float, minimum: float, maximum: float) -> float:
  return max(minimum, min(maximum, value))


def average_visibility(frame: dict[str, Any], side: str) -> float:
  landmark_names = (
    f"{side}_shoulder",
    f"{side}_hip",
    f"{side}_knee",
    f"{side}_ankle",
  )
  visibilities = [frame["landmarks"][name]["visibility"] for name in landmark_names]
  return sum(visibilities) / len(visibilities)


def select_tracking_side(frame: dict[str, Any]) -> str:
  left_visibility = average_visibility(frame, "left")
  right_visibility = average_visibility(frame, "right")
  return "left" if left_visibility >= right_visibility else "right"


def point_for_side(frame: dict[str, Any], side: str, joint: str) -> Point:
  return frame["landmarks"][f"{side}_{joint}"]


def torso_angle_from_vertical(shoulder: Point, hip: Point) -> float:
  dx = shoulder["x"] - hip["x"]
  dy = shoulder["y"] - hip["y"]
  return abs(math.degrees(math.atan2(dx, abs(dy) + 1e-6)))


def hip_depth_ratio(shoulder: Point, hip: Point, ankle: Point) -> float:
  denominator = max(abs(ankle["y"] - shoulder["y"]), 1e-6)
  return (hip["y"] - shoulder["y"]) / denominator


def squat_depth_score(hip: Point, knee: Point, ankle: Point) -> float:
  shin_length = max(abs(ankle["y"] - knee["y"]), 1e-6)
  depth_ratio = (hip["y"] - knee["y"]) / shin_length
  return round(clamp(0.55 + (depth_ratio * 0.9), 0.0, 1.0), 3)


def torso_angle_change(start_angle: float, bottom_angle: float) -> float:
  return round(bottom_angle - start_angle, 2)
