from __future__ import annotations

import copy
import math
from statistics import median
from typing import Any


TRACKING_SETUP_VERSION = 1
BODY_ANCHORS = ("shoulder", "hip", "knee", "ankle")
ALL_ANCHORS = (*BODY_ANCHORS, "barbell")
MIN_TRACK_CONFIDENCE = 0.42


def validate_tracking_setup(value: Any, *, duration_ms: int | None = None) -> tuple[dict[str, Any] | None, str | None]:
  if value is None:
    return None, None
  if not isinstance(value, dict):
    return None, "tracking_setup_not_object"
  if value.get("version") != TRACKING_SETUP_VERSION:
    return None, "unsupported_tracking_setup_version"
  if value.get("barbell_target") != "near_side_collar":
    return None, "unsupported_barbell_target"

  reference_time_ms = value.get("reference_time_ms")
  if not isinstance(reference_time_ms, (int, float)) or not math.isfinite(reference_time_ms):
    return None, "invalid_reference_time"
  if reference_time_ms < 0 or (duration_ms is not None and reference_time_ms > duration_ms + 500):
    return None, "reference_time_out_of_bounds"

  anchors = value.get("anchors")
  if not isinstance(anchors, dict):
    return None, "missing_tracking_anchors"

  normalized_anchors: dict[str, dict[str, float]] = {}
  for name in ALL_ANCHORS:
    point = anchors.get(name)
    if not isinstance(point, dict):
      return None, f"missing_{name}_anchor"
    x = point.get("x")
    y = point.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
      return None, f"invalid_{name}_anchor"
    if not math.isfinite(x) or not math.isfinite(y) or not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
      return None, f"invalid_{name}_anchor"
    normalized_anchors[name] = {"x": float(x), "y": float(y)}

  shoulder = normalized_anchors["shoulder"]
  hip = normalized_anchors["hip"]
  knee = normalized_anchors["knee"]
  ankle = normalized_anchors["ankle"]
  if not (shoulder["y"] < hip["y"] < ankle["y"]):
    return None, "invalid_body_anchor_order"
  if knee["y"] <= hip["y"] - 0.04 or knee["y"] >= ankle["y"] + 0.04:
    return None, "invalid_knee_anchor_order"

  return {
    "version": TRACKING_SETUP_VERSION,
    "reference_time_ms": int(round(reference_time_ms)),
    "barbell_target": "near_side_collar",
    "anchors": normalized_anchors,
  }, None


def _point_distance(first: dict[str, float], second: dict[str, float]) -> float:
  return math.hypot(first["x"] - second["x"], first["y"] - second["y"])


def select_manual_tracking_side(reference_frame: dict[str, Any], anchors: dict[str, dict[str, float]]) -> str:
  landmarks = reference_frame.get("landmarks") or {}
  scores: dict[str, float] = {}
  for side in ("left", "right"):
    distances: list[float] = []
    for joint in BODY_ANCHORS:
      model_point = landmarks.get(f"{side}_{joint}")
      if not model_point:
        distances.append(2.0)
        continue
      distances.append(_point_distance(anchors[joint], model_point))
    scores[side] = sum(distances)
  return min(scores, key=scores.get)


def _read_sampled_gray_frames(
  file_path: str,
  *,
  source_indices: list[int],
  width: int,
  height: int,
) -> dict[int, Any]:
  import cv2

  wanted = set(source_indices)
  frames: dict[int, Any] = {}
  capture = cv2.VideoCapture(file_path)
  if not capture.isOpened():
    return frames
  if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
    capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

  frame_index = 0
  try:
    while capture.isOpened() and wanted:
      success, frame = capture.read()
      if not success:
        break
      if frame_index in wanted:
        if frame.shape[1] != width or frame.shape[0] != height:
          frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        frames[frame_index] = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        wanted.remove(frame_index)
      frame_index += 1
  finally:
    capture.release()
  return frames


def _feature_points(cv2: Any, gray: Any, point: tuple[float, float]) -> Any:
  import numpy as np

  height, width = gray.shape[:2]
  radius = max(int(round(max(width, height) * 0.025)), 12)
  mask = np.zeros_like(gray)
  cv2.circle(mask, (int(round(point[0])), int(round(point[1]))), radius, 255, -1)
  features = cv2.goodFeaturesToTrack(
    gray,
    maxCorners=30,
    qualityLevel=0.01,
    minDistance=3,
    blockSize=5,
    mask=mask,
  )
  if features is not None and len(features) >= 4:
    return features

  offsets = [(-6, -6), (0, -6), (6, -6), (-6, 0), (0, 0), (6, 0), (-6, 6), (0, 6), (6, 6)]
  points = [
    [min(max(point[0] + dx, 0.0), width - 1.0), min(max(point[1] + dy, 0.0), height - 1.0)]
    for dx, dy in offsets
  ]
  return np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)


def _track_step(cv2: Any, previous_gray: Any, gray: Any, point: tuple[float, float]) -> tuple[tuple[float, float] | None, float]:
  import numpy as np

  previous_points = _feature_points(cv2, previous_gray, point)
  next_points, status, _ = cv2.calcOpticalFlowPyrLK(previous_gray, gray, previous_points, None)
  if next_points is None or status is None:
    return None, 0.0

  valid_old = previous_points[status.flatten() == 1]
  valid_new = next_points[status.flatten() == 1]
  if len(valid_new) < 4:
    return None, 0.0

  back_points, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, previous_gray, valid_new, None)
  if back_points is None or back_status is None:
    return None, 0.0
  back_error = np.linalg.norm(back_points.reshape(-1, 2) - valid_old.reshape(-1, 2), axis=1)
  inlier_mask = (back_status.flatten() == 1) & (back_error <= 2.5)
  if int(inlier_mask.sum()) < 4:
    return None, 0.0

  motions = valid_new.reshape(-1, 2)[inlier_mask] - valid_old.reshape(-1, 2)[inlier_mask]
  dx = float(median(float(value) for value in motions[:, 0]))
  dy = float(median(float(value) for value in motions[:, 1]))
  max_jump = max(gray.shape[:2]) * 0.10
  if math.hypot(dx, dy) > max_jump:
    return None, 0.0

  next_point = (point[0] + dx, point[1] + dy)
  height, width = gray.shape[:2]
  if not (0 <= next_point[0] < width and 0 <= next_point[1] < height):
    return None, 0.0
  confidence = min(1.0, (float(inlier_mask.sum()) / max(len(previous_points), 1)) * 1.15)
  return next_point, confidence


def _track_direction(
  cv2: Any,
  frames: dict[int, Any],
  ordered_indices: list[int],
  initial_point: tuple[float, float],
) -> dict[int, dict[str, float]]:
  if not ordered_indices:
    return {}
  tracks = {
    ordered_indices[0]: {"x": initial_point[0], "y": initial_point[1], "confidence": 1.0}
  }
  current_point = initial_point
  previous_index = ordered_indices[0]
  for frame_index in ordered_indices[1:]:
    next_point, confidence = _track_step(
      cv2,
      frames[previous_index],
      frames[frame_index],
      current_point,
    )
    if next_point is None:
      break
    tracks[frame_index] = {"x": next_point[0], "y": next_point[1], "confidence": confidence}
    current_point = next_point
    previous_index = frame_index
  return tracks


def _smooth_anchor_track(
  tracks: dict[int, dict[str, float]],
  *,
  reference_index: int,
) -> dict[int, dict[str, float]]:
  ordered_indices = sorted(tracks)
  if len(ordered_indices) < 3:
    return tracks

  smoothed: dict[int, dict[str, float]] = {}
  for position, source_index in enumerate(ordered_indices):
    point = tracks[source_index]
    if source_index == reference_index:
      smoothed[source_index] = dict(point)
      continue
    neighbor_indices = ordered_indices[max(position - 1, 0):min(position + 2, len(ordered_indices))]
    neighbors = [tracks[index] for index in neighbor_indices]
    smoothed[source_index] = {
      "x": float(median(float(item["x"]) for item in neighbors)),
      "y": float(median(float(item["y"]) for item in neighbors)),
      "confidence": float(point["confidence"]),
    }
  return smoothed


def track_manual_anchors(
  file_path: str,
  *,
  setup: dict[str, Any],
  pose_frames: list[dict[str, Any]],
  fps: float | None,
  width: int,
  height: int,
) -> dict[str, Any]:
  import cv2

  source_indices = sorted({int(frame["source_frame_index"]) for frame in pose_frames})
  if not source_indices or width <= 0 or height <= 0:
    return {"tracks": {}, "reference_source_index": None, "coverage": {name: 0.0 for name in ALL_ANCHORS}}

  requested_source_index = int(round((setup["reference_time_ms"] / 1000) * (fps or 0.0)))
  reference_index = min(source_indices, key=lambda index: abs(index - requested_source_index))
  gray_frames = _read_sampled_gray_frames(
    file_path,
    source_indices=source_indices,
    width=width,
    height=height,
  )
  available_indices = [index for index in source_indices if index in gray_frames]
  if reference_index not in gray_frames or not available_indices:
    return {"tracks": {}, "reference_source_index": reference_index, "coverage": {name: 0.0 for name in ALL_ANCHORS}}

  reference_position = available_indices.index(reference_index)
  tracks: dict[str, dict[int, dict[str, float]]] = {}
  for name in ALL_ANCHORS:
    anchor = setup["anchors"][name]
    initial_point = (anchor["x"] * width, anchor["y"] * height)
    forward = _track_direction(cv2, gray_frames, available_indices[reference_position:], initial_point)
    backward = _track_direction(cv2, gray_frames, list(reversed(available_indices[:reference_position + 1])), initial_point)
    combined = {**backward, **forward}
    normalized_tracks = {
      index: {
        "x": point["x"] / width,
        "y": point["y"] / height,
        "confidence": point["confidence"],
      }
      for index, point in combined.items()
    }
    tracks[name] = _smooth_anchor_track(
      normalized_tracks,
      reference_index=reference_index,
    )

  coverage = {
    name: round(len(anchor_tracks) / max(len(available_indices), 1), 3)
    for name, anchor_tracks in tracks.items()
  }
  return {
    "tracks": tracks,
    "reference_source_index": reference_index,
    "coverage": coverage,
  }


def fuse_manual_body_tracks(
  pose_frames: list[dict[str, Any]],
  *,
  setup: dict[str, Any],
  tracking: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  if not pose_frames or not tracking.get("tracks"):
    return pose_frames, {
      "used": False,
      "selected_side": None,
      "fused_landmark_count": 0,
      "directly_anchored_landmark_count": 0,
      "rejected_track_count": 0,
      "coverage": tracking.get("coverage") or {},
    }

  reference_source_index = tracking.get("reference_source_index")
  reference_frame = min(
    pose_frames,
    key=lambda frame: abs(int(frame.get("source_frame_index", 0)) - int(reference_source_index or 0)),
  )
  selected_side = select_manual_tracking_side(reference_frame, setup["anchors"])
  fused_frames = copy.deepcopy(pose_frames)
  fused_count = 0
  rejected_count = 0
  manual_active = {joint: False for joint in BODY_ANCHORS}
  manual_has_activated = {joint: False for joint in BODY_ANCHORS}
  manual_reentry_streak = {joint: 0 for joint in BODY_ANCHORS}

  for frame in fused_frames:
    source_index = int(frame.get("source_frame_index", -1))
    landmarks = frame.get("landmarks") or {}
    available_points: dict[str, dict[str, float]] = {}
    for joint in BODY_ANCHORS:
      track = (tracking["tracks"].get(joint) or {}).get(source_index)
      if track and float(track.get("confidence") or 0.0) >= MIN_TRACK_CONFIDENCE:
        available_points[joint] = track

    if {"shoulder", "hip", "knee", "ankle"}.issubset(available_points):
      if not (
        available_points["shoulder"]["y"] < available_points["hip"]["y"]
        and available_points["hip"]["y"] - 0.04 < available_points["knee"]["y"]
        and available_points["knee"]["y"] < available_points["ankle"]["y"] + 0.04
      ):
        rejected_count += len(available_points)
        for joint in available_points:
          manual_active[joint] = False
          manual_reentry_streak[joint] = 0
        continue

    for joint in BODY_ANCHORS:
      track = available_points.get(joint)
      if not track:
        manual_active[joint] = False
        manual_reentry_streak[joint] = 0
        continue

      force_reference_anchor = (
        reference_source_index is not None
        and source_index == int(reference_source_index)
      )
      use_manual_track = force_reference_anchor or not manual_has_activated[joint] or manual_active[joint]
      if not use_manual_track:
        manual_reentry_streak[joint] += 1
        use_manual_track = manual_reentry_streak[joint] >= 2
      if not use_manual_track:
        continue

      manual_active[joint] = True
      manual_has_activated[joint] = True
      manual_reentry_streak[joint] = 0
      landmark = landmarks.get(f"{selected_side}_{joint}")
      if not landmark:
        rejected_count += 1
        continue
      model_visibility = float(landmark.get("visibility") or 0.0)
      landmark["x"] = float(track["x"])
      landmark["y"] = float(track["y"])
      landmark["visibility"] = max(model_visibility, min(float(track["confidence"]), 0.92))
      landmark["manual_assisted"] = True
      landmark["manual_source"] = "optical_flow"
      fused_count += 1

  return fused_frames, {
    "used": fused_count > 0,
    "selected_side": selected_side,
    "fused_landmark_count": fused_count,
    "directly_anchored_landmark_count": fused_count,
    "rejected_track_count": rejected_count,
    "coverage": tracking.get("coverage") or {},
  }


def barbell_track_priors(tracking: dict[str, Any]) -> dict[int, dict[str, float]]:
  return {
    int(source_index): point
    for source_index, point in ((tracking.get("tracks") or {}).get("barbell") or {}).items()
    if float(point.get("confidence") or 0.0) >= MIN_TRACK_CONFIDENCE
  }
