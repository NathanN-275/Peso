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
MIN_TRACK_COVERAGE = 0.2
MIN_TRACK_POINTS = 4
MAX_INTERPOLATION_GAP_FRAMES = 4


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
  processing_duration_ms: int = 0,
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
      "failure_reason": reason,
      "processing_duration_ms": processing_duration_ms,
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
  x_margin = max((max(xs) - min(xs)) * 1.8, width * 0.22)

  if shoulder:
    y_min = shoulder[1] - max(torso_height * 1.45, height * 0.2)
    y_max = shoulder[1] + max(torso_height * 0.45, height * 0.1)
  else:
    y_min = min(ys) - height * 0.12
    y_max = max(ys) + height * 0.12

  return (
    max(min(xs) - x_margin, 0.0),
    max(y_min, 0.0),
    min(max(xs) + x_margin, float(width)),
    min(y_max, float(height)),
    shoulder,
  )


def _candidate_in_bounds(candidate: Candidate, bounds: tuple[float, float, float, float]) -> bool:
  min_x, min_y, max_x, max_y = bounds
  return min_x <= candidate.x <= max_x and min_y <= candidate.y <= max_y


def _detect_circle_candidates(cv2: Any, frame: Any) -> list[Candidate]:
  height, width = frame.shape[:2]
  min_dimension = max(min(width, height), 1)
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
    maxRadius=max(12, int(min_dimension * 0.22)),
  )

  if circles is None:
    return []

  return [
    Candidate(
      x=float(circle[0]),
      y=float(circle[1]),
      radius=float(circle[2]),
      confidence=0.62,
    )
    for circle in circles[0]
  ]


def _score_candidate(
  candidate: Candidate,
  *,
  previous: dict[str, float] | None,
  shoulder: tuple[float, float] | None,
  width: int,
  height: int,
) -> float:
  score = candidate.confidence
  min_dimension = max(min(width, height), 1)
  radius_ratio = candidate.radius / min_dimension
  score += min(radius_ratio / 0.16, 1.0) * 0.42

  if shoulder:
    shoulder_distance = math.hypot(candidate.x - shoulder[0], candidate.y - shoulder[1])
    score += max(0.0, 0.18 * (1.0 - shoulder_distance / max(width, height)))
    if candidate.y <= shoulder[1]:
      score += min((shoulder[1] - candidate.y) / (height * 0.28), 1.0) * 0.7
    else:
      score -= min((candidate.y - shoulder[1]) / (height * 0.18), 1.0) * 0.24

  if previous:
    previous_distance = math.hypot(candidate.x - previous["x"], candidate.y - previous["y"])
    score += max(0.0, 0.34 * (1.0 - previous_distance / (max(width, height) * 0.22)))

  return score


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


class BarbellTracker:
  def track(
    self,
    file_path: str,
    *,
    pose_frames: list[dict[str, Any]],
    frame_step: int,
    processed_width: int | None,
    processed_height: int | None,
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

    frame_step = max(int(frame_step or 1), 1)
    pose_by_source_index = {
      int(frame.get("source_frame_index", -1)): frame
      for frame in pose_frames
      if frame.get("source_frame_index") is not None
    }
    samples: list[dict[str, Any] | None] = []
    previous_point: dict[str, float] | None = None
    detected_count = 0
    frame_index = 0

    try:
      while capture.isOpened():
        success, frame = capture.read()
        if not success:
          break

        if frame_index % frame_step != 0:
          frame_index += 1
          continue

        if frame.shape[1] != width or frame.shape[0] != height:
          frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

        timestamp = frame_index / fps if fps > 0 else len(samples) / 18.0
        pose_frame = pose_by_source_index.get(frame_index)
        bounds = _pose_bounds(pose_frame, width=width, height=height)
        candidate_bounds = bounds[:4]
        shoulder = bounds[4]
        candidates = [
          candidate
          for candidate in _detect_circle_candidates(cv2, frame)
          if _candidate_in_bounds(candidate, candidate_bounds)
        ]

        if not candidates:
          samples.append(None)
          frame_index += 1
          continue

        selected = max(
          candidates,
          key=lambda candidate: _score_candidate(
            candidate,
            previous=previous_point,
            shoulder=shoulder,
            width=width,
            height=height,
          ),
        )
        point = {
          "time": timestamp,
          "x": selected.x / width,
          "y": selected.y / height,
          "confidence": min(
            _score_candidate(
              selected,
              previous=previous_point,
              shoulder=shoulder,
              width=width,
              height=height,
            ),
            1.0,
          ),
        }
        previous_point = {"x": selected.x, "y": selected.y}
        samples.append(point)
        detected_count += 1
        frame_index += 1
    finally:
      capture.release()

    sampled_count = len(samples)
    processing_duration_ms = int((time.perf_counter() - started) * 1000)
    if sampled_count == 0:
      return _empty_result("no_sampled_frames", processing_duration_ms=processing_duration_ms)

    points, interpolated_count = _interpolate_missing(samples)
    coverage = len(points) / sampled_count if sampled_count else 0.0

    if len(points) < MIN_TRACK_POINTS or coverage < MIN_TRACK_COVERAGE:
      return _empty_result(
        "low_barbell_tracking_coverage",
        sampled_frame_count=sampled_count,
        detected_point_count=detected_count,
        processing_duration_ms=processing_duration_ms,
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
        "failure_reason": None,
        "processing_duration_ms": processing_duration_ms,
      },
    }
