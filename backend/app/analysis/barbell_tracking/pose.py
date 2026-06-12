from __future__ import annotations

from typing import Any


def _visible_landmarks(frame: dict[str, Any] | None) -> dict[str, dict[str, float]]:
  if not frame:
    return {}

  landmarks = frame.get("landmarks") or {}
  return {
    name: point
    for name, point in landmarks.items()
    if float(point.get("visibility", 0.0) or 0.0) >= 0.35
  }


def _mean_point(
  landmarks: dict[str, dict[str, float]],
  names: tuple[str, ...],
  *,
  width: int,
  height: int,
) -> tuple[float, float] | None:
  points = [landmarks[name] for name in names if name in landmarks]
  if not points:
    return None

  return (
    sum(float(point.get("x", 0.0)) for point in points) / len(points) * width,
    sum(float(point.get("y", 0.0)) for point in points) / len(points) * height,
  )


def _point_for_landmark(
  landmarks: dict[str, dict[str, float]],
  name: str,
  *,
  width: int,
  height: int,
) -> tuple[float, float] | None:
  point = landmarks.get(name)
  if not point:
    return None

  return (
    float(point.get("x", 0.0)) * width,
    float(point.get("y", 0.0)) * height,
  )


def _side_point(
  landmarks: dict[str, dict[str, float]],
  selected_side: str | None,
  joint: str,
  *,
  width: int,
  height: int,
) -> tuple[float, float] | None:
  if selected_side not in {"left", "right"}:
    return None

  return _point_for_landmark(landmarks, f"{selected_side}_{joint}", width=width, height=height)


def _side_wrist_points(
  pose_frame: dict[str, Any] | None,
  *,
  selected_side: str | None,
  width: int,
  height: int,
) -> list[tuple[float, float]]:
  landmarks = _visible_landmarks(pose_frame)
  point = _side_point(landmarks, selected_side, "wrist", width=width, height=height)
  if point:
    return [point]

  points: list[tuple[float, float]] = []
  for name in ("left_wrist", "right_wrist"):
    point = _point_for_landmark(landmarks, name, width=width, height=height)
    if point is not None:
      points.append(point)
  return points


def _pose_bounds(
  pose_frame: dict[str, Any] | None,
  *,
  width: int,
  height: int,
  selected_side: str | None = None,
) -> tuple[float, float, float, float, tuple[float, float] | None]:
  landmarks = _visible_landmarks(pose_frame)
  if not landmarks:
    return 0.0, 0.0, float(width), float(height), None

  shoulder = (
    _side_point(landmarks, selected_side, "shoulder", width=width, height=height)
    or _mean_point(landmarks, ("left_shoulder", "right_shoulder"), width=width, height=height)
  )
  hip = (
    _side_point(landmarks, selected_side, "hip", width=width, height=height)
    or _mean_point(landmarks, ("left_hip", "right_hip"), width=width, height=height)
  )
  if selected_side in {"left", "right"}:
    upper_names = (
      f"{selected_side}_shoulder",
      f"{selected_side}_elbow",
      f"{selected_side}_wrist",
      f"{selected_side}_hip",
    )
  else:
    upper_names = (
      "left_shoulder",
      "right_shoulder",
      "left_elbow",
      "right_elbow",
      "left_wrist",
      "right_wrist",
      "left_hip",
      "right_hip",
    )
  upper_points = [landmarks[name] for name in upper_names if name in landmarks]

  if not upper_points:
    return 0.0, 0.0, float(width), float(height), shoulder

  xs = [float(point.get("x", 0.0)) * width for point in upper_points]
  ys = [float(point.get("y", 0.0)) * height for point in upper_points]
  torso_height = abs((hip[1] if hip else max(ys)) - (shoulder[1] if shoulder else min(ys)))
  torso_height = max(torso_height, height * 0.16)

  if shoulder:
    x_margin = max(torso_height * 0.9, width * 0.25)
    y_min = shoulder[1] - max(torso_height * 0.72, height * 0.16)
    y_max = shoulder[1] + max(torso_height * 0.42, height * 0.11)
    min_x = shoulder[0] - x_margin
    max_x = shoulder[0] + x_margin
  else:
    x_margin = max((max(xs) - min(xs)) * 1.1, width * 0.18)
    y_min = min(ys) - height * 0.12
    y_max = max(ys) + height * 0.12
    min_x = min(xs) - x_margin
    max_x = max(xs) + x_margin

  return (
    max(min_x, 0.0),
    max(y_min, 0.0),
    min(max_x, float(width)),
    min(y_max, float(height)),
    shoulder,
  )
