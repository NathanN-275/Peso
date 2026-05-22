from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

TRACKING_TARGET = "near_plate_collar_center"
TRACKING_SOURCE = "opencv_circle_tracker"
BARBELL_TRACK_TARGET_FPS = 6.0
MAX_DETECTION_CROP_WIDTH = 240
MAX_CANDIDATES_PER_FRAME = 12
MIN_TRACK_COVERAGE = 0.2
MIN_TRACK_POINTS = 4
MAX_INTERPOLATION_GAP_FRAMES = 2
COLLAR_OFFSET_RATIO = 0.34


@dataclass(frozen=True)
class Candidate:
  x: float
  y: float
  radius: float
  confidence: float


def _empty_result(
  reason: str,
  *,
  sampled_frame_count: int = 0,
  detected_point_count: int = 0,
  skipped_no_pose_frame_count: int = 0,
  processing_duration_ms: int = 0,
  target_fps: float = BARBELL_TRACK_TARGET_FPS,
  tracking_frame_step: int | None = None,
  rejected_candidate_count: int = 0,
  rejection_reason_counts: dict[str, int] | None = None,
  crop_width: float | None = None,
  crop_height: float | None = None,
  selected_plate: Candidate | None = None,
  predicted_collar: tuple[float, float] | None = None,
  refined_collar: tuple[float, float] | None = None,
) -> dict[str, Any]:
  return {
    "barbellPath": {
      "available": False,
      "target": TRACKING_TARGET,
      "source": TRACKING_SOURCE,
      "coverage": 0.0,
      "points": [],
    },
    "diagnostics": {
      "available": False,
      "target": TRACKING_TARGET,
      "source": TRACKING_SOURCE,
      "coverage": 0.0,
      "sampled_frame_count": sampled_frame_count,
      "detected_point_count": detected_point_count,
      "interpolated_point_count": 0,
      "rejected_frame_count": max(sampled_frame_count - detected_point_count, 0),
      "rejected_candidate_count": rejected_candidate_count,
      "rejection_reason_counts": rejection_reason_counts or {},
      "skipped_no_pose_frame_count": skipped_no_pose_frame_count,
      "failure_reason": reason,
      "processing_duration_ms": processing_duration_ms,
      "target_fps": target_fps,
      "tracking_frame_step": tracking_frame_step,
      "crop_width": crop_width,
      "crop_height": crop_height,
      "average_crop_width": crop_width,
      "average_crop_height": crop_height,
      "selected_candidate_type": "none",
      "plate_center_x": round(selected_plate.x, 2) if selected_plate else None,
      "plate_center_y": round(selected_plate.y, 2) if selected_plate else None,
      "plate_radius": round(selected_plate.radius, 2) if selected_plate else None,
      "predicted_collar_x": round(predicted_collar[0], 2) if predicted_collar else None,
      "predicted_collar_y": round(predicted_collar[1], 2) if predicted_collar else None,
      "refined_collar_x": round(refined_collar[0], 2) if refined_collar else None,
      "refined_collar_y": round(refined_collar[1], 2) if refined_collar else None,
    },
  }


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


def _pose_bounds(
  pose_frame: dict[str, Any] | None,
  *,
  width: int,
  height: int,
) -> tuple[float, float, float, float, tuple[float, float] | None]:
  landmarks = _visible_landmarks(pose_frame)
  if not landmarks:
    return 0.0, 0.0, float(width), float(height), None

  shoulder = _mean_point(landmarks, ("left_shoulder", "right_shoulder"), width=width, height=height)
  hip = _mean_point(landmarks, ("left_hip", "right_hip"), width=width, height=height)
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


def _candidate_in_bounds(candidate: Candidate, bounds: tuple[float, float, float, float]) -> bool:
  min_x, min_y, max_x, max_y = bounds
  return min_x <= candidate.x <= max_x and min_y <= candidate.y <= max_y


def _detect_circle_candidates(
  cv2: Any,
  frame: Any,
  *,
  offset_x: float = 0.0,
  offset_y: float = 0.0,
  radius_reference: int | None = None,
) -> list[Candidate]:
  height, width = frame.shape[:2]
  min_dimension = max(radius_reference or min(width, height), 1)
  gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
  gray = cv2.GaussianBlur(gray, (9, 9), 1.6)
  circles = cv2.HoughCircles(
    gray,
    cv2.HOUGH_GRADIENT,
    dp=1.2,
    minDist=max(20, int(min_dimension * 0.14)),
    param1=80,
    param2=18,
    minRadius=max(8, int(min_dimension * 0.025)),
    maxRadius=max(12, int(min_dimension * 0.34)),
  )

  if circles is None:
    return []

  return [
    Candidate(
      x=float(circle[0]) + offset_x,
      y=float(circle[1]) + offset_y,
      radius=float(circle[2]),
      confidence=0.62,
    )
    for circle in circles[0]
  ]


def _detection_crop(
  cv2: Any,
  frame: Any,
  bounds: tuple[float, float, float, float],
) -> tuple[Any, float, float, float, float]:
  height, width = frame.shape[:2]
  min_x, min_y, max_x, max_y = bounds
  x0 = max(int(math.floor(min_x)), 0)
  y0 = max(int(math.floor(min_y)), 0)
  x1 = min(int(math.ceil(max_x)), width)
  y1 = min(int(math.ceil(max_y)), height)

  if x1 <= x0 or y1 <= y0:
    return frame, 0.0, 0.0, float(width), float(height)

  crop = frame[y0:y1, x0:x1]
  crop_width = crop.shape[1]
  crop_height = crop.shape[0]
  if crop_width > MAX_DETECTION_CROP_WIDTH:
    scale = MAX_DETECTION_CROP_WIDTH / crop_width
    resized_width = MAX_DETECTION_CROP_WIDTH
    resized_height = max(int(round(crop_height * scale)), 1)
    crop = cv2.resize(crop, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    return crop, float(x0), float(y0), 1 / scale, 1 / scale

  return crop, float(x0), float(y0), 1.0, 1.0


def _detect_crop_candidates(
  cv2: Any,
  frame: Any,
  bounds: tuple[float, float, float, float],
) -> tuple[list[Candidate], int, int]:
  crop, offset_x, offset_y, scale_x, scale_y = _detection_crop(cv2, frame, bounds)
  radius_reference = int(round(min(frame.shape[:2]) / ((scale_x + scale_y) / 2)))
  candidates = _detect_circle_candidates(cv2, crop, radius_reference=radius_reference)
  crop_height, crop_width = crop.shape[:2]
  mapped = [
    Candidate(
      x=(candidate.x * scale_x) + offset_x,
      y=(candidate.y * scale_y) + offset_y,
      radius=candidate.radius * ((scale_x + scale_y) / 2),
      confidence=candidate.confidence,
    )
    for candidate in candidates
  ]
  mapped.sort(key=lambda candidate: candidate.radius, reverse=True)
  return mapped[:MAX_CANDIDATES_PER_FRAME], crop_width, crop_height


def _shoulder_relative_offset(
  candidate: Candidate,
  shoulder: tuple[float, float] | None,
) -> tuple[float, float] | None:
  if not shoulder:
    return None

  return candidate.x - shoulder[0], candidate.y - shoulder[1]


def _temporal_tracking_bounds(
  base_bounds: tuple[float, float, float, float],
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> tuple[float, float, float, float]:
  if not previous or not shoulder or "dx" not in previous or "dy" not in previous:
    return base_bounds

  expected_x = shoulder[0] + previous["dx"]
  expected_y = shoulder[1] + previous["dy"]
  x_margin = max(width * 0.12, 36.0)
  y_margin = max(height * 0.09, 28.0)
  min_x, min_y, max_x, max_y = base_bounds

  return (
    max(min_x, expected_x - x_margin, 0.0),
    max(min_y, expected_y - y_margin, 0.0),
    min(max_x, expected_x + x_margin, float(width)),
    min(max_y, expected_y + y_margin, float(height)),
  )


def _score_plate_candidate(
  candidate: Candidate,
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> float:
  score = candidate.confidence
  bootstrapping = previous is None
  min_dimension = max(min(width, height), 1)
  radius_ratio = candidate.radius / min_dimension
  score += min(radius_ratio / 0.18, 1.0) * (1.1 if bootstrapping else 0.52)

  if shoulder:
    shoulder_distance = math.hypot(candidate.x - shoulder[0], candidate.y - shoulder[1])
    score += max(0.0, 0.38 * (1.0 - shoulder_distance / (max(width, height) * 0.42)))
    vertical_offset = (shoulder[1] - candidate.y) / height
    ideal_offset = 0.06
    tolerance = 0.16
    band_score = max(0.0, 1.0 - (abs(vertical_offset - ideal_offset) / tolerance))
    score += band_score * (1.0 if bootstrapping else 0.5)

    if vertical_offset > 0.18:
      score -= min((vertical_offset - 0.18) / 0.08, 1.0) * (1.15 if bootstrapping else 0.72)
    if vertical_offset < -0.12:
      score -= min(abs(vertical_offset + 0.12) / 0.08, 1.0) * (0.8 if bootstrapping else 0.4)

  if previous:
    previous_distance = math.hypot(candidate.x - previous["x"], candidate.y - previous["y"])
    score += max(0.0, 0.18 * (1.0 - previous_distance / (max(width, height) * 0.24)))
    score += _score_plate_relative_to_shoulder(candidate, previous=previous, shoulder=shoulder, width=width, height=height)
    previous_radius = previous.get("radius")
    if previous_radius:
      radius_delta = abs(candidate.radius - previous_radius) / max(previous_radius, 1.0)
      score += max(0.0, 0.34 * (1.0 - radius_delta / 0.24))

  return score


def _score_plate_relative_to_shoulder(
  candidate: Candidate,
  *,
  previous: dict[str, float],
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> float:
  offset = _shoulder_relative_offset(candidate, shoulder)
  if not offset or "dx" not in previous or "dy" not in previous:
    return 0.0

  relative_jump = math.hypot(offset[0] - previous["dx"], offset[1] - previous["dy"])
  score = max(0.0, 0.82 * (1.0 - relative_jump / (max(width, height) * 0.15)))

  previous_shoulder_x = previous.get("shoulder_x")
  previous_shoulder_y = previous.get("shoulder_y")
  if previous_shoulder_x is not None and previous_shoulder_y is not None:
    shoulder_motion = math.hypot(shoulder[0] - previous_shoulder_x, shoulder[1] - previous_shoulder_y) if shoulder else 0.0
    absolute_motion = math.hypot(candidate.x - previous["x"], candidate.y - previous["y"])
    if shoulder_motion >= 4.0 and absolute_motion <= max(1.5, shoulder_motion * 0.35):
      score -= 0.95

  return score


def _select_candidate(
  candidates: list[Candidate],
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> Candidate:
  if previous is None and shoulder:
    preferred = [
      candidate
      for candidate in candidates
      if shoulder[1] - (height * 0.18) <= candidate.y <= shoulder[1] + (height * 0.13)
    ]
    if preferred:
      candidates = preferred

  return max(
    candidates,
    key=lambda candidate: _score_plate_candidate(
      candidate,
      previous=previous,
      shoulder=shoulder,
      width=width,
      height=height,
    ),
  )


def _plate_rejection_reason(
  candidate: Candidate,
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> str | None:
  if shoulder:
    offset = _shoulder_relative_offset(candidate, shoulder)
    if offset:
      if abs(offset[0]) > width * 0.34:
        return "outside_plate_zone"
      if offset[1] < -height * 0.19:
        return "too_high_above_shoulder"
      if offset[1] > height * 0.16:
        return "outside_plate_zone"

    vertical_offset = (shoulder[1] - candidate.y) / height
    if vertical_offset > 0.19:
      return "too_high_above_shoulder"

  if previous:
    jump_distance = math.hypot(candidate.x - previous["x"], candidate.y - previous["y"])
    if jump_distance > max(width, height) * 0.24:
      return "absolute_jump"

    previous_radius = previous.get("radius")
    if previous_radius and abs(candidate.radius - previous_radius) / max(previous_radius, 1.0) > 0.38:
      return "outside_plate_zone"

    offset = _shoulder_relative_offset(candidate, shoulder)
    if offset and "dx" in previous and "dy" in previous:
      relative_jump = math.hypot(offset[0] - previous["dx"], offset[1] - previous["dy"])
      if relative_jump > max(width, height) * 0.13:
        return "relative_offset_jump"

      previous_shoulder_x = previous.get("shoulder_x")
      previous_shoulder_y = previous.get("shoulder_y")
      if previous_shoulder_x is not None and previous_shoulder_y is not None and shoulder:
        shoulder_motion = math.hypot(shoulder[0] - previous_shoulder_x, shoulder[1] - previous_shoulder_y)
        absolute_motion = math.hypot(candidate.x - previous["x"], candidate.y - previous["y"])
        if shoulder_motion >= 4.0 and absolute_motion <= max(1.5, shoulder_motion * 0.35):
          return "stationary_hardware_like"

  return None


def _estimate_collar_from_plate(
  plate: Candidate,
  *,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
  previous: dict[str, float] | None = None,
) -> tuple[float, float]:
  if previous and "collar_direction_x" in previous and "collar_direction_y" in previous:
    direction_x = previous["collar_direction_x"]
    direction_y = previous["collar_direction_y"]
  elif shoulder:
    direction_x = 1.0 if plate.x >= shoulder[0] else -1.0
    direction_y = -0.08 if plate.y <= shoulder[1] else 0.04
  else:
    direction_x = 1.0
    direction_y = -0.06

  magnitude = max(math.hypot(direction_x, direction_y), 0.01)
  direction_x /= magnitude
  direction_y /= magnitude
  offset = max(plate.radius * COLLAR_OFFSET_RATIO, min(width, height) * 0.025)
  return (
    min(max(plate.x + direction_x * offset, 0.0), float(width)),
    min(max(plate.y + direction_y * offset, 0.0), float(height)),
  )


def _refine_collar_point(
  cv2: Any,
  frame: Any,
  *,
  predicted: tuple[float, float],
  plate: Candidate,
) -> tuple[float, float]:
  height, width = frame.shape[:2]
  radius = max(int(round(plate.radius * 0.16)), 8)
  x0 = max(int(round(predicted[0])) - radius, 0)
  y0 = max(int(round(predicted[1])) - radius, 0)
  x1 = min(int(round(predicted[0])) + radius + 1, width)
  y1 = min(int(round(predicted[1])) + radius + 1, height)

  if x1 <= x0 or y1 <= y0:
    return predicted

  crop = frame[y0:y1, x0:x1]
  gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
  gray = cv2.GaussianBlur(gray, (5, 5), 0)
  edges = cv2.Canny(gray, 60, 150)
  moments = cv2.moments(edges)
  if moments["m00"] <= 0:
    return predicted

  refined = (
    x0 + (moments["m10"] / moments["m00"]),
    y0 + (moments["m01"] / moments["m00"]),
  )
  if math.hypot(refined[0] - predicted[0], refined[1] - predicted[1]) > radius * 0.55:
    return predicted

  return refined


def _interpolate_missing(samples: list[dict[str, Any] | None]) -> tuple[list[dict[str, Any]], int]:
  filled: list[dict[str, Any] | None] = samples[:]
  interpolated_count = 0
  index = 0

  while index < len(filled):
    if filled[index] is not None:
      index += 1
      continue

    gap_start = index
    while index < len(filled) and filled[index] is None:
      index += 1
    gap_end = index - 1
    previous_index = gap_start - 1
    next_index = index

    if (
      previous_index < 0
      or next_index >= len(filled)
      or filled[previous_index] is None
      or filled[next_index] is None
      or (gap_end - gap_start + 1) > MAX_INTERPOLATION_GAP_FRAMES
    ):
      continue

    previous = filled[previous_index]
    next_point = filled[next_index]
    if previous is None or next_point is None:
      continue

    total_steps = next_index - previous_index
    for missing_index in range(gap_start, gap_end + 1):
      progress = (missing_index - previous_index) / total_steps
      filled[missing_index] = {
        "time": samples[missing_index]["time"] if samples[missing_index] else (
          previous["time"] + ((next_point["time"] - previous["time"]) * progress)
        ),
        "x": previous["x"] + ((next_point["x"] - previous["x"]) * progress),
        "y": previous["y"] + ((next_point["y"] - previous["y"]) * progress),
        "confidence": min(previous["confidence"], next_point["confidence"]) * 0.72,
        "interpolated": True,
      }
      interpolated_count += 1

  return [point for point in filled if point is not None], interpolated_count


def _smooth_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
  smoothed: list[dict[str, Any]] = []

  for index, point in enumerate(points):
    window = points[max(index - 1, 0):min(index + 2, len(points))]
    confidence_sum = sum(max(float(item["confidence"]), 0.01) for item in window)
    smoothed.append(
      {
        "time": round(float(point["time"]), 4),
        "x": round(
          sum(float(item["x"]) * max(float(item["confidence"]), 0.01) for item in window)
          / confidence_sum,
          4,
        ),
        "y": round(
          sum(float(item["y"]) * max(float(item["confidence"]), 0.01) for item in window)
          / confidence_sum,
          4,
        ),
        "confidence": round(float(point["confidence"]), 3),
      }
    )

  return smoothed


def _draw_debug_frame(
  cv2: Any,
  frame: Any,
  *,
  bounds: tuple[float, float, float, float],
  candidates: list[Candidate],
  rejected: list[Candidate],
  selected_plate: Candidate | None,
  predicted_collar: tuple[float, float] | None,
  refined_collar: tuple[float, float] | None,
) -> Any:
  debug = frame.copy()
  min_x, min_y, max_x, max_y = bounds
  cv2.rectangle(debug, (int(min_x), int(min_y)), (int(max_x), int(max_y)), (255, 180, 0), 2)
  rejected_ids = {id(candidate) for candidate in rejected}

  for candidate in candidates:
    color = (0, 0, 255) if id(candidate) in rejected_ids else (0, 255, 255)
    cv2.circle(debug, (int(candidate.x), int(candidate.y)), max(int(candidate.radius), 3), color, 2)

  if selected_plate:
    cv2.circle(debug, (int(selected_plate.x), int(selected_plate.y)), max(int(selected_plate.radius), 4), (0, 255, 0), 3)
    cv2.circle(debug, (int(selected_plate.x), int(selected_plate.y)), 3, (0, 255, 0), -1)

  if predicted_collar:
    cv2.drawMarker(
      debug,
      (int(predicted_collar[0]), int(predicted_collar[1])),
      (255, 0, 255),
      markerType=cv2.MARKER_CROSS,
      markerSize=12,
      thickness=2,
    )

  if refined_collar:
    cv2.drawMarker(
      debug,
      (int(refined_collar[0]), int(refined_collar[1])),
      (40, 235, 52),
      markerType=cv2.MARKER_TILTED_CROSS,
      markerSize=12,
      thickness=2,
    )

  return debug


class BarbellTracker:
  def track(
    self,
    file_path: str,
    *,
    pose_frames: list[dict[str, Any]],
    frame_step: int,
    processed_width: int | None,
    processed_height: int | None,
    debug_output_path: str | None = None,
  ) -> dict[str, Any]:
    import cv2

    started = time.perf_counter()
    if not Path(file_path).is_file():
      return _empty_result("video_unavailable")

    capture = cv2.VideoCapture(file_path)
    if not capture.isOpened():
      return _empty_result("video_unavailable")

    if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
      capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    width = processed_width or frame_width
    height = processed_height or frame_height
    if width <= 0 or height <= 0:
      capture.release()
      return _empty_result("invalid_video_dimensions")

    pose_frame_step = max(int(frame_step or 1), 1)
    target_frame_step = max(int(round(fps / BARBELL_TRACK_TARGET_FPS)), 1) if fps > 0 else pose_frame_step
    tracking_frame_step = pose_frame_step * max(int(round(target_frame_step / pose_frame_step)), 1)
    pose_by_source_index = {
      int(frame.get("source_frame_index", -1)): frame
      for frame in pose_frames
      if frame.get("source_frame_index") is not None
    }
    if not pose_by_source_index:
      capture.release()
      return _empty_result(
        "no_pose_frames",
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
    )

    samples: list[dict[str, Any] | None] = []
    previous_plate: dict[str, float] | None = None
    detected_count = 0
    rejected_candidate_count = 0
    rejection_reason_counts: dict[str, int] = {}
    skipped_no_pose_frame_count = 0
    crop_widths: list[int] = []
    crop_heights: list[int] = []
    selected_plate: Candidate | None = None
    predicted_collar: tuple[float, float] | None = None
    refined_collar: tuple[float, float] | None = None
    frame_index = 0
    debug_writer = None

    if debug_output_path:
      debug_writer = cv2.VideoWriter(
        debug_output_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        BARBELL_TRACK_TARGET_FPS,
        (width, height),
      )

    try:
      while capture.isOpened():
        success, frame = capture.read()
        if not success:
          break

        if frame_index % tracking_frame_step != 0:
          frame_index += 1
          continue

        if frame.shape[1] != width or frame.shape[0] != height:
          frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

        timestamp = frame_index / fps if fps > 0 else len(samples) / 18.0
        pose_frame = pose_by_source_index.get(frame_index)
        if not pose_frame:
          skipped_no_pose_frame_count += 1
          frame_index += 1
          continue

        bounds = _pose_bounds(pose_frame, width=width, height=height)
        shoulder = bounds[4]
        candidate_bounds = _temporal_tracking_bounds(
          bounds[:4],
          previous=previous_plate,
          shoulder=shoulder,
          width=width,
          height=height,
        )
        candidates, crop_width, crop_height = _detect_crop_candidates(cv2, frame, candidate_bounds)
        crop_widths.append(crop_width)
        crop_heights.append(crop_height)
        candidates = [candidate for candidate in candidates if _candidate_in_bounds(candidate, candidate_bounds)]
        rejected: list[Candidate] = []
        plausible_candidates: list[Candidate] = []

        for candidate in candidates:
          reason = _plate_rejection_reason(
            candidate,
            previous=previous_plate,
            shoulder=shoulder,
            width=width,
            height=height,
          )
          if reason:
            rejected.append(candidate)
            rejected_candidate_count += 1
            rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1
          else:
            plausible_candidates.append(candidate)

        if not plausible_candidates:
          samples.append(None)
          if debug_writer:
            debug_writer.write(
              _draw_debug_frame(
                cv2,
                frame,
                bounds=candidate_bounds,
                candidates=candidates,
                rejected=rejected,
                selected_plate=None,
                predicted_collar=None,
                refined_collar=None,
              )
            )
          frame_index += 1
          continue

        selected_plate = _select_candidate(
          plausible_candidates,
          previous=previous_plate,
          shoulder=shoulder,
          width=width,
          height=height,
        )
        predicted_collar = _estimate_collar_from_plate(
          selected_plate,
          shoulder=shoulder,
          width=width,
          height=height,
          previous=previous_plate,
        )
        refined_collar = _refine_collar_point(
          cv2,
          frame,
          predicted=predicted_collar,
          plate=selected_plate,
        )
        confidence = min(
          _score_plate_candidate(
            selected_plate,
            previous=previous_plate,
            shoulder=shoulder,
            width=width,
            height=height,
          ),
          1.0,
        )
        point = {
          "time": timestamp,
          "x": refined_collar[0] / width,
          "y": refined_collar[1] / height,
          "confidence": confidence,
        }
        relative_offset = _shoulder_relative_offset(selected_plate, shoulder)
        direction_x = (predicted_collar[0] - selected_plate.x) / max(math.hypot(predicted_collar[0] - selected_plate.x, predicted_collar[1] - selected_plate.y), 0.01)
        direction_y = (predicted_collar[1] - selected_plate.y) / max(math.hypot(predicted_collar[0] - selected_plate.x, predicted_collar[1] - selected_plate.y), 0.01)
        previous_plate = {
          "x": selected_plate.x,
          "y": selected_plate.y,
          "dx": relative_offset[0] if relative_offset else 0.0,
          "dy": relative_offset[1] if relative_offset else 0.0,
          "radius": selected_plate.radius,
          "shoulder_x": shoulder[0] if shoulder else selected_plate.x,
          "shoulder_y": shoulder[1] if shoulder else selected_plate.y,
          "collar_direction_x": direction_x,
          "collar_direction_y": direction_y,
        }
        samples.append(point)
        detected_count += 1
        if debug_writer:
          debug_writer.write(
            _draw_debug_frame(
              cv2,
              frame,
              bounds=candidate_bounds,
              candidates=candidates,
              rejected=rejected,
              selected_plate=selected_plate,
              predicted_collar=predicted_collar,
              refined_collar=refined_collar,
            )
          )
        frame_index += 1
    finally:
      capture.release()
      if debug_writer:
        debug_writer.release()

    sampled_count = len(samples)
    processing_duration_ms = int((time.perf_counter() - started) * 1000)
    average_crop_width = round(sum(crop_widths) / len(crop_widths), 1) if crop_widths else None
    average_crop_height = round(sum(crop_heights) / len(crop_heights), 1) if crop_heights else None
    if sampled_count == 0:
      return _empty_result(
        "no_sampled_frames",
        skipped_no_pose_frame_count=skipped_no_pose_frame_count,
        processing_duration_ms=processing_duration_ms,
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
        rejected_candidate_count=rejected_candidate_count,
        rejection_reason_counts=rejection_reason_counts,
        crop_width=average_crop_width,
        crop_height=average_crop_height,
        selected_plate=selected_plate,
        predicted_collar=predicted_collar,
        refined_collar=refined_collar,
      )

    points, interpolated_count = _interpolate_missing(samples)
    coverage = len(points) / sampled_count if sampled_count else 0.0

    if len(points) < MIN_TRACK_POINTS or coverage < MIN_TRACK_COVERAGE:
      return _empty_result(
        "low_barbell_tracking_coverage",
        sampled_frame_count=sampled_count,
        detected_point_count=detected_count,
        skipped_no_pose_frame_count=skipped_no_pose_frame_count,
        processing_duration_ms=processing_duration_ms,
        target_fps=BARBELL_TRACK_TARGET_FPS,
        tracking_frame_step=tracking_frame_step,
        rejected_candidate_count=rejected_candidate_count,
        rejection_reason_counts=rejection_reason_counts,
        crop_width=average_crop_width,
        crop_height=average_crop_height,
        selected_plate=selected_plate,
        predicted_collar=predicted_collar,
        refined_collar=refined_collar,
      )

    smoothed_points = _smooth_points(points)
    coverage = round(coverage, 3)
    return {
      "barbellPath": {
        "available": True,
        "target": TRACKING_TARGET,
        "source": TRACKING_SOURCE,
        "coverage": coverage,
        "points": smoothed_points,
      },
      "diagnostics": {
        "available": True,
        "target": TRACKING_TARGET,
        "source": TRACKING_SOURCE,
        "coverage": coverage,
        "sampled_frame_count": sampled_count,
        "detected_point_count": detected_count,
        "interpolated_point_count": interpolated_count,
        "rejected_frame_count": max(sampled_count - detected_count - interpolated_count, 0),
        "rejected_candidate_count": rejected_candidate_count,
        "rejection_reason_counts": rejection_reason_counts,
        "skipped_no_pose_frame_count": skipped_no_pose_frame_count,
        "failure_reason": None,
        "processing_duration_ms": processing_duration_ms,
        "target_fps": BARBELL_TRACK_TARGET_FPS,
        "tracking_frame_step": tracking_frame_step,
        "crop_width": average_crop_width,
        "crop_height": average_crop_height,
        "average_crop_width": average_crop_width,
        "average_crop_height": average_crop_height,
        "selected_candidate_type": "plate" if selected_plate else "none",
        "plate_center_x": round(selected_plate.x, 2) if selected_plate else None,
        "plate_center_y": round(selected_plate.y, 2) if selected_plate else None,
        "plate_radius": round(selected_plate.radius, 2) if selected_plate else None,
        "predicted_collar_x": round(predicted_collar[0], 2) if predicted_collar else None,
        "predicted_collar_y": round(predicted_collar[1], 2) if predicted_collar else None,
        "refined_collar_x": round(refined_collar[0], 2) if refined_collar else None,
        "refined_collar_y": round(refined_collar[1], 2) if refined_collar else None,
      },
    }
