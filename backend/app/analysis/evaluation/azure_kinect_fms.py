from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..pose_estimator import empty_landmarks


FMS_SQUAT_MOVEMENTS = {"m01", "m02"}
FMS_PRIMARY_MOVEMENT = "m01"
FMS_STRESS_MOVEMENT = "m02"
AZURE_COLOR_WIDTH = 2048
AZURE_COLOR_HEIGHT = 1536

# Azure Kinect Body Tracking SDK joint order.
AZURE_TO_PESO_LANDMARK = {
  5: "left_shoulder",
  12: "right_shoulder",
  18: "left_hip",
  19: "left_knee",
  20: "left_ankle",
  22: "right_hip",
  23: "right_knee",
  24: "right_ankle",
}
CONFIDENCE_TO_VISIBILITY = {0: 0.0, 1: 0.35, 2: 0.70, 3: 0.95}
SEQUENCE_NAME = re.compile(
  r"^(?P<view>front|side)_(?P<subject>s\d+)_(?P<movement>m\d+)_(?P<timestamp>\d{14})_(?P<episode>e\d+)\.json$"
)


@dataclass(frozen=True)
class FmsSequenceIdentity:
  view: str
  subject: str
  movement: str
  recorded_at: str
  episode: str

  @property
  def condition(self) -> str:
    return "primary" if self.movement == FMS_PRIMARY_MOVEMENT else "heels_elevated_stress"


def parse_fms_sequence_name(path: str | Path) -> FmsSequenceIdentity:
  match = SEQUENCE_NAME.match(Path(path).name)
  if match is None:
    raise ValueError(f"Unsupported FMS sequence name: {Path(path).name}")
  values = match.groupdict()
  if values["movement"] not in FMS_SQUAT_MOVEMENTS:
    raise ValueError(f"FMS movement {values['movement']} is not a squat reference movement.")
  return FmsSequenceIdentity(
    view=values["view"],
    subject=values["subject"],
    movement=values["movement"],
    recorded_at=values["timestamp"],
    episode=values["episode"],
  )


def iter_fms_squat_paths(root: str | Path) -> Iterable[Path]:
  root = Path(root)
  for path in sorted(root.rglob("*.json")):
    try:
      parse_fms_sequence_name(path)
    except ValueError:
      continue
    yield path


def _source_indices(payload: dict[str, Any], frame_count: int) -> list[int]:
  # The source dataset misspells this field in the published JSON.
  values = payload.get("original_frame_num") or payload.get("original_frmae_num") or []
  if isinstance(values, list) and len(values) == frame_count:
    return [int(value) for value in values]
  return list(range(frame_count))


def adapt_fms_sequence(
  payload: dict[str, Any],
  *,
  identity: FmsSequenceIdentity,
  image_width: int = AZURE_COLOR_WIDTH,
  image_height: int = AZURE_COLOR_HEIGHT,
) -> dict[str, Any]:
  """Map a published Azure Kinect FMS sequence into Peso's pose-frame contract.

  Missing-body frames remain explicit zero-confidence gaps. This reference data
  is for kinematic stress testing only and must not be reported as RGB accuracy.
  """
  source_frames = payload.get("frames")
  if not isinstance(source_frames, list):
    raise ValueError("FMS payload must contain a frames list.")
  source_indices = _source_indices(payload, len(source_frames))
  frames: list[dict[str, Any]] = []

  for offset, source_frame in enumerate(source_frames):
    landmarks = empty_landmarks()
    bodies = source_frame.get("bodies") if isinstance(source_frame, dict) else None
    if isinstance(bodies, list) and bodies and isinstance(bodies[0], dict):
      body = bodies[0]
      positions = body.get("joint_position_2d_color") or []
      confidence_levels = body.get("confidence_level") or []
      for azure_index, landmark_name in AZURE_TO_PESO_LANDMARK.items():
        if azure_index >= len(positions):
          continue
        position = positions[azure_index]
        if not isinstance(position, list) or len(position) < 2:
          continue
        confidence = int(confidence_levels[azure_index]) if azure_index < len(confidence_levels) else 0
        landmarks[landmark_name] = {
          "x": float(position[0]) / max(float(image_width), 1.0),
          "y": float(position[1]) / max(float(image_height), 1.0),
          "z": 0.0,
          "visibility": CONFIDENCE_TO_VISIBILITY.get(confidence, 0.0),
        }

    timestamp_usec = source_frame.get("timestamp_usec", offset * 33_333) if isinstance(source_frame, dict) else offset * 33_333
    frames.append({
      "timestamp_ms": int(round(float(timestamp_usec) / 1000.0)),
      "source_frame_index": source_indices[offset],
      "frame_width": image_width,
      "frame_height": image_height,
      "processed_frame_width": image_width,
      "processed_frame_height": image_height,
      "pose_backend": "azure_kinect_fms_reference",
      "landmark_model": "azure_kinect_body_tracking_32",
      "landmarks": landmarks,
    })

  return {
    "frames": frames,
    "frame_count": len(frames),
    "fps": _estimated_fps(frames),
    "accuracy_claim_eligible": False,
    "reference_purpose": "kinematic_stress_test",
    "sequence": {
      "view": identity.view,
      "subject": identity.subject,
      "movement": identity.movement,
      "condition": identity.condition,
      "episode": identity.episode,
      "recorded_at": identity.recorded_at,
    },
  }


def _estimated_fps(frames: list[dict[str, Any]]) -> float | None:
  deltas = [
    current["timestamp_ms"] - previous["timestamp_ms"]
    for previous, current in zip(frames, frames[1:])
    if current["timestamp_ms"] > previous["timestamp_ms"]
  ]
  return round(1000.0 / statistics.median(deltas), 3) if deltas else None


def _distance(first: dict[str, float], second: dict[str, float]) -> float:
  return math.hypot(first["x"] - second["x"], first["y"] - second["y"])


def summarize_fms_sequence(adapted: dict[str, Any]) -> dict[str, Any]:
  frames = adapted.get("frames") or []
  coverage: dict[str, int] = {name: 0 for name in AZURE_TO_PESO_LANDMARK.values()}
  segment_lengths: dict[str, list[float]] = {
    "left_thigh": [], "left_shin": [], "right_thigh": [], "right_shin": [],
  }
  hip_y: list[tuple[int, float]] = []
  identity_signs: list[int] = []

  for frame_index, frame in enumerate(frames):
    landmarks = frame.get("landmarks") or {}
    for name in coverage:
      if float((landmarks.get(name) or {}).get("visibility") or 0.0) >= 0.35:
        coverage[name] += 1
    for side in ("left", "right"):
      hip = landmarks.get(f"{side}_hip") or {}
      knee = landmarks.get(f"{side}_knee") or {}
      ankle = landmarks.get(f"{side}_ankle") or {}
      if min(float(hip.get("visibility") or 0), float(knee.get("visibility") or 0)) >= 0.35:
        segment_lengths[f"{side}_thigh"].append(_distance(hip, knee))
      if min(float(knee.get("visibility") or 0), float(ankle.get("visibility") or 0)) >= 0.35:
        segment_lengths[f"{side}_shin"].append(_distance(knee, ankle))
    visible_hips = [landmarks.get("left_hip") or {}, landmarks.get("right_hip") or {}]
    if min(float(point.get("visibility") or 0.0) for point in visible_hips) >= 0.35:
      hip_y.append((frame_index, statistics.fmean(float(point["y"]) for point in visible_hips)))
      separation = float(visible_hips[0]["x"]) - float(visible_hips[1]["x"])
      if abs(separation) >= 0.002:
        identity_signs.append(1 if separation > 0 else -1)

  frame_count = len(frames)
  sign_switches = sum(current != previous for previous, current in zip(identity_signs, identity_signs[1:]))
  coefficients = {}
  for name, values in segment_lengths.items():
    mean = statistics.fmean(values) if values else 0.0
    coefficients[name] = round(statistics.pstdev(values) / mean, 5) if len(values) > 1 and mean > 0 else None

  return {
    "sequence": adapted.get("sequence") or {},
    "frame_count": frame_count,
    "joint_coverage": {
      name: round(count / max(frame_count, 1), 5)
      for name, count in coverage.items()
    },
    "missing_body_frame_count": sum(
      1 for frame in frames
      if max(float(point.get("visibility") or 0.0) for point in (frame.get("landmarks") or {}).values()) == 0.0
    ),
    "segment_coefficient_of_variation": coefficients,
    "side_identity_sign_switches": sign_switches,
    "bottom_frame_index": max(hip_y, key=lambda value: value[1])[0] if hip_y else None,
    "accuracy_claim_eligible": False,
  }
