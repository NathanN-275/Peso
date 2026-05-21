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


def lower_body_visibility(frame: dict[str, Any], side: str) -> float:
  landmark_names = (
    f"{side}_hip",
    f"{side}_knee",
    f"{side}_ankle",
  )
  visibilities = [frame["landmarks"][name]["visibility"] for name in landmark_names]
  return sum(visibilities) / len(visibilities)


def select_depth_side(frame: dict[str, Any]) -> tuple[str, float, float, float]:
  # Pick the side whose hip, knee, and ankle are most trustworthy for depth.
  left_visibility = lower_body_visibility(frame, "left")
  right_visibility = lower_body_visibility(frame, "right")
  selected_side = "left" if left_visibility >= right_visibility else "right"
  stronger_visibility = max(left_visibility, right_visibility)
  weaker_visibility = min(left_visibility, right_visibility)
  clarity = (stronger_visibility - weaker_visibility) / max(stronger_visibility, 1e-6)
  return (
    selected_side,
    round(stronger_visibility, 3),
    round(weaker_visibility, 3),
    round(clamp(clarity, 0.0, 1.0), 3),
  )


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


def landmark_visibility_score(points: list[Point]) -> float:
  # Average landmark visibility for a metric's input joints.
  if not points:
    return 0.0

  return clamp(sum(point.get("visibility", 0.0) for point in points) / len(points), 0.0, 1.0)


def _frame_height_from_points(points: list[Point], fallback: float = 1.0) -> float:
  for point in points:
    height = point.get("frame_height") or point.get("frameHeight")
    if height and height > 0:
      return float(height)
  return fallback


def _depth_reason(
  *,
  depth_delta: float,
  tolerance: float,
  confidence: float,
  lower_body_confidence: float,
  min_lower_body_confidence: float,
  side_clarity: float | None,
) -> tuple[str, str]:
  if min_lower_body_confidence < 0.35 or lower_body_confidence < 0.45:
    return "uncertain_depth", "low_landmark_confidence"
  if confidence < 0.45:
    return "uncertain_depth", "low_depth_confidence"
  if side_clarity is not None and side_clarity < 0.08:
    return "uncertain_depth", "selected_side_unclear"
  if depth_delta >= -tolerance:
    return "hit_depth", "depth_met"
  if depth_delta > -(tolerance * 2.0):
    return "uncertain_depth", "borderline_depth"
  return "insufficient_depth", "hip_crease_above_knee_top"


def squat_depth_assessment(
  shoulder: Point,
  hip: Point,
  knee: Point,
  ankle: Point,
  *,
  frame_height_px: float | None = None,
  selected_side: str | None = None,
  selected_side_score: float | None = None,
  alternate_side_score: float | None = None,
  side_clarity: float | None = None,
) -> dict[str, Any]:
  # Score depth from 2D side-view geometry and joint flexion; MediaPipe z is not treated as real depth.
  shin_length = max(abs(ankle["y"] - knee["y"]), 1e-6)
  thigh_length = max(math.hypot(hip["x"] - knee["x"], hip["y"] - knee["y"]), 1e-6)
  limb_reference = max(shin_length, thigh_length, 1e-6)
  raw_hip_knee_delta = hip["y"] - knee["y"]
  knee_score = knee_flexion_score(hip, knee, ankle)
  hip_score = hip_flexion_score(shoulder, hip, knee)
  crease_offset = min(limb_reference * 0.10, 0.04)
  crease_offset *= clamp(knee_score / 0.55, 0.45, 1.0)
  knee_top_offset = min(limb_reference * 0.08, 0.032)
  hip_crease_y = hip["y"] + crease_offset
  knee_top_y = knee["y"] - knee_top_offset
  hip_knee_delta = hip_crease_y - knee_top_y
  hip_vs_knee_ratio = hip_knee_delta / limb_reference
  depth_tolerance = max(limb_reference * 0.08, 0.018)
  ratio_tolerance = depth_tolerance / limb_reference
  # Hip crease at or slightly above the knee top is treated as depth; nearby misses stay uncertain.
  ratio_parallel_score = clamp((hip_vs_knee_ratio + ratio_tolerance) / ratio_tolerance, 0.0, 1.0)
  absolute_parallel_score = clamp((hip_knee_delta + depth_tolerance) / depth_tolerance, 0.0, 1.0)
  parallel_score = max(ratio_parallel_score, absolute_parallel_score)
  below_parallel_score = clamp(hip_vs_knee_ratio / 0.24, 0.0, 1.0)
  hip_vs_knee_score = clamp((parallel_score * 0.80) + (below_parallel_score * 0.20), 0.0, 1.0)
  visibility_score = landmark_visibility_score([shoulder, hip, knee, ankle])
  lower_body_confidence = landmark_visibility_score([hip, knee, ankle])
  min_lower_body_confidence = min(
    hip.get("visibility", 0.0),
    knee.get("visibility", 0.0),
    ankle.get("visibility", 0.0),
  )

  geometry_score = (
    (hip_vs_knee_score * 0.76)
    + (knee_score * 0.16)
    + (hip_score * 0.08)
  )
  visibility_multiplier = clamp(visibility_score / 0.75, 0.35, 1.0)
  score = clamp(geometry_score * visibility_multiplier, 0.0, 1.0)
  consistency = 1.0 - min(
    (abs(hip_vs_knee_score - knee_score) + abs(knee_score - hip_score)) * 0.55,
    1.0,
  )
  geometry_confidence = 1.0 if abs(hip_vs_knee_ratio) >= 0.04 else 0.82
  confidence = clamp(
    (lower_body_confidence * 0.62)
    + (consistency * 0.22)
    + (visibility_score * 0.06)
    + (geometry_confidence * 0.10),
    0.0,
    1.0,
  )
  classification, reason = _depth_reason(
    depth_delta=hip_knee_delta,
    tolerance=depth_tolerance,
    confidence=confidence,
    lower_body_confidence=lower_body_confidence,
    min_lower_body_confidence=min_lower_body_confidence,
    side_clarity=side_clarity,
  )
  resolved_frame_height = frame_height_px or _frame_height_from_points([shoulder, hip, knee, ankle])

  return {
    "score": round(score, 3),
    "confidence": round(confidence, 3),
    "depth_classification": classification,
    "depth_reason": reason,
    "selected_side": selected_side,
    "selected_side_score": selected_side_score,
    "alternate_side_score": alternate_side_score,
    "side_clarity": side_clarity,
    "hip_vs_knee_score": round(hip_vs_knee_score, 3),
    "knee_flexion_score": round(knee_score, 3),
    "hip_flexion_score": round(hip_score, 3),
    "parallel_score": round(parallel_score, 3),
    "visibility_score": round(visibility_score, 3),
    "lower_body_confidence": round(lower_body_confidence, 3),
    "min_lower_body_confidence": round(min_lower_body_confidence, 3),
    "hip_knee_delta": round(hip_knee_delta, 3),
    "raw_hip_knee_delta": round(raw_hip_knee_delta, 3),
    "hip_crease_offset": round(crease_offset, 3),
    "knee_top_offset": round(knee_top_offset, 3),
    "estimated_hip_crease_y": round(hip_crease_y, 4),
    "estimated_knee_top_y": round(knee_top_y, 4),
    "depth_delta_px": round(hip_knee_delta * resolved_frame_height, 2),
    "depth_tolerance_px": round(depth_tolerance * resolved_frame_height, 2),
    "depth_delta_normalized": round(hip_knee_delta, 4),
    "depth_tolerance_normalized": round(depth_tolerance, 4),
    "hip_vs_knee_ratio": round(hip_vs_knee_ratio, 3),
    "ratio_parallel_score": round(ratio_parallel_score, 3),
    "absolute_parallel_score": round(absolute_parallel_score, 3),
  }


def squat_depth_score(
  hip: Point,
  knee: Point,
  ankle: Point,
  shoulder: Point | None = None,
) -> float:
  # Backward-compatible score helper. Pass shoulder when hip flexion should contribute.
  if shoulder is not None:
    return squat_depth_assessment(shoulder, hip, knee, ankle)["score"]

  shin_length = max(abs(ankle["y"] - knee["y"]), 1e-6)
  knee_score = knee_flexion_score(hip, knee, ankle)
  thigh_vertical = abs(knee["y"] - hip["y"])
  crease_offset = min(thigh_vertical * 0.28, shin_length * 0.14)
  crease_offset *= clamp(knee_score / 0.55, 0.0, 1.0)
  hip_vs_knee_ratio = ((hip["y"] + crease_offset) - knee["y"]) / shin_length
  hip_knee_delta = (hip["y"] + crease_offset) - knee["y"]
  parallel_score = max(
    clamp((hip_vs_knee_ratio + 0.10) / 0.10, 0.0, 1.0),
    clamp((hip_knee_delta + 0.03) / 0.03, 0.0, 1.0),
  )
  below_parallel_score = clamp(hip_vs_knee_ratio / 0.24, 0.0, 1.0)
  hip_vs_knee_score = clamp((parallel_score * 0.80) + (below_parallel_score * 0.20), 0.0, 1.0)
  visibility_score = landmark_visibility_score([hip, knee, ankle])
  visibility_multiplier = clamp(visibility_score / 0.75, 0.35, 1.0)
  return round(clamp(((hip_vs_knee_score * 0.78) + (knee_score * 0.22)) * visibility_multiplier, 0.0, 1.0), 3)


def torso_angle_change(start_angle: float, bottom_angle: float) -> float:
  # Compare torso lean at the start and bottom of the rep.
  return round(bottom_angle - start_angle, 2)
