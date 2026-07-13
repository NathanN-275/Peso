from __future__ import annotations

import copy
import math
import os
from collections import Counter
from dataclasses import dataclass
from statistics import median
from typing import Any

from .metrics_calculator import clamp, select_tracking_side_for_clip
from .pose_validator import validate_squat_pose_frames


REPAIR_JOINTS = ("shoulder", "hip", "knee", "ankle")
OPTIONAL_QUALITY_JOINTS = ("heel", "foot_index")
SEGMENTS = (
  ("shoulder", "hip", "torso"),
  ("hip", "knee", "thigh"),
  ("knee", "ankle", "shin"),
  ("ankle", "heel", "ankle_heel"),
  ("ankle", "foot_index", "ankle_foot"),
)


@dataclass(frozen=True)
class PoseRepairConfig:
  enabled: bool = True
  min_visibility: float = 0.35
  max_gap_frames: int = 3
  velocity_gap_frames: int = 2
  recovery_hysteresis_frames: int = 2


def _bool_from_env(name: str, default: bool) -> bool:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default
  normalized = raw_value.strip().lower()
  if normalized in {"1", "true", "yes", "on"}:
    return True
  if normalized in {"0", "false", "no", "off"}:
    return False
  return default


def _int_from_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
  raw_value = os.getenv(name)
  if raw_value is None or not raw_value.strip():
    return default
  try:
    value = int(raw_value)
  except ValueError:
    return default
  return value if minimum <= value <= maximum else default


def pose_repair_config_from_env() -> PoseRepairConfig:
  return PoseRepairConfig(
    enabled=_bool_from_env("POSE_REPAIR_ENABLED", True),
    max_gap_frames=_int_from_env("POSE_REPAIR_MAX_GAP_FRAMES", 3, minimum=1, maximum=12),
    velocity_gap_frames=_int_from_env("POSE_REPAIR_VELOCITY_GAP_FRAMES", 2, minimum=1, maximum=6),
    recovery_hysteresis_frames=_int_from_env(
      "POSE_REPAIR_RECOVERY_HYSTERESIS_FRAMES",
      2,
      minimum=1,
      maximum=6,
    ),
  )


def _distance(first: dict[str, Any], second: dict[str, Any]) -> float:
  return math.hypot(float(first["x"]) - float(second["x"]), float(first["y"]) - float(second["y"]))


def _landmark(frame: dict[str, Any], side: str, joint: str) -> dict[str, Any] | None:
  point = (frame.get("landmarks") or {}).get(f"{side}_{joint}")
  return point if isinstance(point, dict) else None


def _is_pin_owned(point: dict[str, Any] | None) -> bool:
  if not point:
    return False
  return bool(
    point.get("manual_assisted")
    or point.get("user_pinned")
    or point.get("tracking_state") in {"reference", "guided"}
    or point.get("manual_source") in {"reference_pin", "pin_guided"}
  )


def _is_reliable(point: dict[str, Any] | None, config: PoseRepairConfig) -> bool:
  if not point:
    return False
  if _is_pin_owned(point):
    return True
  return (
    float(point.get("visibility") or 0.0) >= config.min_visibility
    and point.get("accepted_source") != "gap"
    and point.get("chain_valid") is not False
  )


def _available_quality_joints(frames: list[dict[str, Any]], side: str) -> tuple[str, ...]:
  optional = tuple(
    joint
    for joint in OPTIONAL_QUALITY_JOINTS
    if any(_landmark(frame, side, joint) is not None for frame in frames)
  )
  return REPAIR_JOINTS + optional


def _median_segment_lengths(
  frames: list[dict[str, Any]],
  side: str,
  config: PoseRepairConfig,
) -> dict[str, float]:
  values: dict[str, list[float]] = {name: [] for _, _, name in SEGMENTS}
  for frame in frames:
    for first_name, second_name, segment_name in SEGMENTS:
      first = _landmark(frame, side, first_name)
      second = _landmark(frame, side, second_name)
      if not _is_reliable(first, config) or not _is_reliable(second, config):
        continue
      length = _distance(first, second)
      if length > 1e-6:
        values[segment_name].append(length)
  return {name: median(lengths) if lengths else 0.0 for name, lengths in values.items()}


def _joint_jump_penalty(
  frames: list[dict[str, Any]],
  frame_index: int,
  side: str,
  joint: str,
  subject_scale: float,
) -> tuple[float, str | None]:
  if frame_index <= 0 or frame_index >= len(frames) - 1:
    return 0.0, None
  previous = _landmark(frames[frame_index - 1], side, joint)
  current = _landmark(frames[frame_index], side, joint)
  following = _landmark(frames[frame_index + 1], side, joint)
  if not previous or not current or not following:
    return 0.0, None
  if min(float(previous.get("visibility") or 0.0), float(following.get("visibility") or 0.0)) < 0.35:
    return 0.0, None
  midpoint = {
    "x": (float(previous["x"]) + float(following["x"])) / 2,
    "y": (float(previous["y"]) + float(following["y"])) / 2,
  }
  residual = _distance(current, midpoint)
  threshold = max(0.045, subject_scale * (0.16 if joint in {"shoulder", "hip"} else 0.22))
  if residual <= threshold:
    return 0.0, None
  return clamp((residual - threshold) / max(threshold, 1e-6), 0.0, 1.0), "temporal_jump"


def score_selected_side_pose(
  frames: list[dict[str, Any]],
  *,
  selected_side: str,
  config: PoseRepairConfig,
) -> dict[str, Any]:
  quality_joints = _available_quality_joints(frames, selected_side)
  median_lengths = _median_segment_lengths(frames, selected_side, config)
  subject_scale = sum(
    median_lengths.get(name, 0.0)
    for name in ("torso", "thigh", "shin")
  ) or 0.45
  automatic_side, side_confidence = select_tracking_side_for_clip(frames) if frames else (selected_side, 0.0)
  frame_scores: list[dict[str, Any]] = []
  reason_counts: Counter[str] = Counter()

  for frame_index, frame in enumerate(frames):
    point_scores: dict[str, float] = {}
    frame_reasons: set[str] = set()
    for joint in quality_joints:
      point = _landmark(frame, selected_side, joint)
      visibility = clamp(float((point or {}).get("visibility") or 0.0), 0.0, 1.0)
      score = visibility
      if visibility < config.min_visibility:
        frame_reasons.add(f"{joint}_low_visibility")
        score *= 0.35
      jump_penalty, jump_reason = _joint_jump_penalty(
        frames,
        frame_index,
        selected_side,
        joint,
        subject_scale,
      )
      if jump_reason:
        frame_reasons.add(f"{joint}_{jump_reason}")
        score *= 1.0 - (jump_penalty * 0.75)
      point_scores[joint] = clamp(score, 0.0, 1.0)

    for first_name, second_name, segment_name in SEGMENTS:
      reference = median_lengths.get(segment_name) or 0.0
      first = _landmark(frame, selected_side, first_name)
      second = _landmark(frame, selected_side, second_name)
      if reference <= 1e-6 or not first or not second:
        continue
      ratio = _distance(first, second) / reference
      if ratio < 0.62 or ratio > 1.48:
        frame_reasons.add(f"{segment_name}_length_inconsistent")
        for joint in (first_name, second_name):
          if joint in point_scores:
            point_scores[joint] *= 0.55

    if automatic_side != selected_side and side_confidence >= 0.12:
      frame_reasons.add("selected_side_visibility_conflict")
    score = sum(point_scores.values()) / max(len(point_scores), 1)
    if "selected_side_visibility_conflict" in frame_reasons:
      score *= 0.85
    reasons = sorted(frame_reasons)
    reason_counts.update(reasons)
    frame_scores.append({
      "frame_index": frame_index,
      "source_frame_index": frame.get("source_frame_index"),
      "timestamp_ms": frame.get("timestamp_ms"),
      "score": round(clamp(score, 0.0, 1.0), 3),
      "joint_scores": {name: round(value, 3) for name, value in point_scores.items()},
      "reasons": reasons,
    })

  average_quality = (
    sum(float(frame["score"]) for frame in frame_scores) / len(frame_scores)
    if frame_scores
    else 0.0
  )
  worst_frames = sorted(frame_scores, key=lambda item: (item["score"], item["frame_index"]))[:8]
  return {
    "selected_side": selected_side,
    "automatic_side": automatic_side,
    "side_consistency_confidence": side_confidence,
    "average_quality": round(average_quality, 3),
    "frame_quality": frame_scores,
    "worst_segments": worst_frames,
    "reason_counts": dict(reason_counts),
    "median_segment_lengths": {
      name: round(value, 5)
      for name, value in median_lengths.items()
      if value > 0
    },
  }


def _unreliable_runs(
  raw_frames: list[dict[str, Any]],
  repaired_frames: list[dict[str, Any]],
  *,
  side: str,
  joint: str,
  config: PoseRepairConfig,
) -> list[tuple[int, int]]:
  invalid_indices = []
  for index, raw_frame in enumerate(raw_frames):
    raw_point = _landmark(raw_frame, side, joint)
    repaired_point = _landmark(repaired_frames[index], side, joint)
    if _is_pin_owned(raw_point):
      continue
    if not _is_reliable(raw_point, config) or (repaired_point or {}).get("accepted_source") == "gap":
      invalid_indices.append(index)
  if not invalid_indices:
    return []
  runs: list[tuple[int, int]] = []
  start = previous = invalid_indices[0]
  for index in invalid_indices[1:]:
    if index != previous + 1:
      runs.append((start, previous))
      start = index
    previous = index
  runs.append((start, previous))
  return runs


def _interpolated_point(
  previous: dict[str, Any],
  following: dict[str, Any],
  fraction: float,
) -> dict[str, float]:
  return {
    "x": float(previous["x"]) + ((float(following["x"]) - float(previous["x"])) * fraction),
    "y": float(previous["y"]) + ((float(following["y"]) - float(previous["y"])) * fraction),
    "z": float(previous.get("z") or 0.0) + (
      (float(following.get("z") or 0.0) - float(previous.get("z") or 0.0)) * fraction
    ),
  }


def _velocity_point(first: dict[str, Any], second: dict[str, Any], horizon: int) -> dict[str, float]:
  return {
    "x": float(second["x"]) + ((float(second["x"]) - float(first["x"])) * horizon),
    "y": float(second["y"]) + ((float(second["y"]) - float(first["y"])) * horizon),
    "z": float(second.get("z") or 0.0) + (
      (float(second.get("z") or 0.0) - float(first.get("z") or 0.0)) * horizon
    ),
  }


def _constrain_to_segment(
  candidate: dict[str, float],
  frame: dict[str, Any],
  *,
  side: str,
  joint: str,
  segment_lengths: dict[str, float],
) -> tuple[dict[str, float], bool]:
  anchor_name: str | None = None
  segment_name: str | None = None
  if joint == "shoulder":
    anchor_name, segment_name = "hip", "torso"
  elif joint == "hip":
    anchor_name, segment_name = "knee", "thigh"
  elif joint == "knee":
    anchor_name, segment_name = "hip", "thigh"
  elif joint == "ankle":
    anchor_name, segment_name = "knee", "shin"
  target_length = segment_lengths.get(segment_name or "") or 0.0
  anchor = _landmark(frame, side, anchor_name or "")
  if not anchor or target_length <= 1e-6:
    return candidate, False
  dx = candidate["x"] - float(anchor["x"])
  dy = candidate["y"] - float(anchor["y"])
  current_length = math.hypot(dx, dy)
  if current_length <= 1e-6:
    return candidate, False
  ratio = current_length / target_length
  if 0.72 <= ratio <= 1.32:
    return candidate, False
  constrained_length = clamp(current_length, target_length * 0.82, target_length * 1.18)
  scale = constrained_length / current_length
  return {
    **candidate,
    "x": float(anchor["x"]) + (dx * scale),
    "y": float(anchor["y"]) + (dy * scale),
  }, True


def _write_repair(
  target: dict[str, Any],
  candidate: dict[str, float],
  *,
  source: str,
  reasons: list[str],
  confidence: float,
) -> None:
  target.update(candidate)
  target["visibility"] = min(max(confidence, 0.2), 0.48)
  target["tracking_state"] = "estimated"
  target["accepted_source"] = source
  target["chain_valid"] = True
  target["visual_only"] = False
  target["pose_repair_reasons"] = reasons
  target.pop("chain_failure_reason", None)


def _mark_gap(target: dict[str, Any], *, reasons: list[str]) -> None:
  target["visibility"] = min(float(target.get("visibility") or 0.0), 0.2)
  target["tracking_state"] = "estimated"
  target["accepted_source"] = "gap"
  target["chain_valid"] = False
  target["visual_only"] = True
  target["chain_failure_reason"] = "pose_repair_long_gap"
  target["pose_repair_reasons"] = reasons


def _repair_short_gaps(
  raw_frames: list[dict[str, Any]],
  repaired_frames: list[dict[str, Any]],
  *,
  side: str,
  config: PoseRepairConfig,
  segment_lengths: dict[str, float],
) -> dict[str, int]:
  counts = {
    "temporal_interpolated": 0,
    "velocity_estimated": 0,
    "segment_constrained": 0,
    "gap": 0,
    "hysteresis_hold": 0,
  }
  for joint in REPAIR_JOINTS:
    runs = _unreliable_runs(
      raw_frames,
      repaired_frames,
      side=side,
      joint=joint,
      config=config,
    )
    for start, end in runs:
      run_length = end - start + 1
      reasons = ["low_visibility_or_invalid", f"{joint}_unreliable"]
      if run_length > config.max_gap_frames:
        for index in range(start, end + 1):
          target = _landmark(repaired_frames[index], side, joint)
          if target is not None:
            _mark_gap(target, reasons=reasons + ["long_gap"])
            counts["gap"] += 1
        continue

      previous = _landmark(raw_frames[start - 1], side, joint) if start > 0 else None
      following = _landmark(raw_frames[end + 1], side, joint) if end + 1 < len(raw_frames) else None
      can_interpolate = _is_reliable(previous, config) and _is_reliable(following, config)
      previous_two = _landmark(raw_frames[start - 2], side, joint) if start > 1 else None
      can_velocity = (
        run_length <= config.velocity_gap_frames
        and _is_reliable(previous_two, config)
        and _is_reliable(previous, config)
      )

      if not can_interpolate and not can_velocity:
        for index in range(start, end + 1):
          target = _landmark(repaired_frames[index], side, joint)
          if target is not None:
            _mark_gap(target, reasons=reasons + ["insufficient_temporal_context"])
            counts["gap"] += 1
        continue

      for offset, index in enumerate(range(start, end + 1), start=1):
        if can_interpolate and previous is not None and following is not None:
          candidate = _interpolated_point(previous, following, offset / (run_length + 1))
          source = "pose_repair_interpolated"
          counts["temporal_interpolated"] += 1
        else:
          assert previous_two is not None and previous is not None
          candidate = _velocity_point(previous_two, previous, offset)
          source = "pose_repair_velocity"
          counts["velocity_estimated"] += 1
        candidate, constrained = _constrain_to_segment(
          candidate,
          repaired_frames[index],
          side=side,
          joint=joint,
          segment_lengths=segment_lengths,
        )
        if constrained:
          source = f"{source}_constrained"
          counts["segment_constrained"] += 1
        target = _landmark(repaired_frames[index], side, joint)
        if target is not None:
          _write_repair(
            target,
            candidate,
            source=source,
            reasons=reasons,
            confidence=0.46 if can_interpolate else 0.42,
          )

      recovery_start = end + 1
      if recovery_start >= len(repaired_frames):
        continue
      for recovery_offset in range(config.recovery_hysteresis_frames - 1):
        index = recovery_start + recovery_offset
        if index >= len(repaired_frames):
          break
        raw_point = _landmark(raw_frames[index], side, joint)
        if not _is_reliable(raw_point, config) or _is_pin_owned(raw_point):
          break
        previous_output = _landmark(repaired_frames[index - 1], side, joint) if index > 0 else None
        previous_previous_output = _landmark(repaired_frames[index - 2], side, joint) if index > 1 else None
        if not previous_output or not previous_previous_output:
          break
        predicted = _velocity_point(previous_previous_output, previous_output, 1)
        candidate = {
          "x": (float(raw_point["x"]) * 0.65) + (predicted["x"] * 0.35),
          "y": (float(raw_point["y"]) * 0.65) + (predicted["y"] * 0.35),
          "z": (float(raw_point.get("z") or 0.0) * 0.65) + (predicted["z"] * 0.35),
        }
        candidate, constrained = _constrain_to_segment(
          candidate,
          repaired_frames[index],
          side=side,
          joint=joint,
          segment_lengths=segment_lengths,
        )
        target = _landmark(repaired_frames[index], side, joint)
        if target is not None:
          _write_repair(
            target,
            candidate,
            source="pose_repair_hysteresis_constrained" if constrained else "pose_repair_hysteresis",
            reasons=["recovery_hysteresis"],
            confidence=min(float(raw_point.get("visibility") or 0.0), 0.48),
          )
          counts["hysteresis_hold"] += 1
          if constrained:
            counts["segment_constrained"] += 1
  return counts


def _raw_repair_debug(
  raw_frames: list[dict[str, Any]],
  repaired_frames: list[dict[str, Any]],
  *,
  side: str,
  limit: int = 160,
) -> tuple[list[dict[str, Any]], bool]:
  entries: list[dict[str, Any]] = []
  for frame_index, (raw_frame, repaired_frame) in enumerate(zip(raw_frames, repaired_frames)):
    for joint in REPAIR_JOINTS:
      raw_point = _landmark(raw_frame, side, joint)
      repaired_point = _landmark(repaired_frame, side, joint)
      if not raw_point or not repaired_point:
        continue
      accepted_source = str(repaired_point.get("accepted_source") or "")
      changed = (
        abs(float(raw_point.get("x") or 0.0) - float(repaired_point.get("x") or 0.0)) > 1e-5
        or abs(float(raw_point.get("y") or 0.0) - float(repaired_point.get("y") or 0.0)) > 1e-5
        or accepted_source.startswith("pose_repair_")
        or accepted_source == "gap"
      )
      if not changed:
        continue
      if len(entries) >= limit:
        return entries, True
      entries.append({
        "frame_index": frame_index,
        "source_frame_index": raw_frame.get("source_frame_index"),
        "timestamp_ms": raw_frame.get("timestamp_ms"),
        "joint": joint,
        "raw": {
          "x": round(float(raw_point.get("x") or 0.0), 4),
          "y": round(float(raw_point.get("y") or 0.0), 4),
          "visibility": round(float(raw_point.get("visibility") or 0.0), 3),
        },
        "repaired": {
          "x": round(float(repaired_point.get("x") or 0.0), 4),
          "y": round(float(repaired_point.get("y") or 0.0), 4),
          "visibility": round(float(repaired_point.get("visibility") or 0.0), 3),
          "accepted_source": accepted_source,
        },
      })
  return entries, False


def repair_selected_side_pose(
  frames: list[dict[str, Any]],
  *,
  selected_side_override: str | None = None,
  config: PoseRepairConfig | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  config = config or pose_repair_config_from_env()
  if not frames:
    return frames, {
      "enabled": config.enabled,
      "selected_side": None,
      "raw_frame_count": 0,
      "repaired_frame_count": 0,
      "estimated_landmark_count": 0,
      "gap_count": 0,
      "average_quality": 0.0,
      "worst_segments": [],
      "pose_validation": {},
    }

  automatic_side, side_confidence = select_tracking_side_for_clip(frames)
  selected_side = selected_side_override if selected_side_override in {"left", "right"} else automatic_side
  quality = score_selected_side_pose(frames, selected_side=selected_side, config=config)
  if not config.enabled:
    return copy.deepcopy(frames), {
      "enabled": False,
      "selected_side": selected_side,
      "selected_side_overridden": selected_side != automatic_side,
      "tracking_side_confidence": side_confidence,
      "raw_frame_count": len(frames),
      "repaired_frame_count": 0,
      "estimated_landmark_count": 0,
      "gap_count": 0,
      **quality,
      "pose_validation": {
        "selected_side": selected_side,
        "selected_side_overridden": selected_side != automatic_side,
        "tracking_side_confidence": side_confidence,
        "corrected_landmark_count": 0,
        "rejected_landmark_count": 0,
        "quality_score_penalty": 0.0,
        "unreliable_landmarks": [],
      },
    }

  validated_frames, validation = validate_squat_pose_frames(
    frames,
    selected_side_override=selected_side,
  )
  segment_lengths = _median_segment_lengths(frames, selected_side, config)
  temporal_counts = _repair_short_gaps(
    frames,
    validated_frames,
    side=selected_side,
    config=config,
    segment_lengths=segment_lengths,
  )
  raw_repair_debug, raw_repair_debug_truncated = _raw_repair_debug(
    frames,
    validated_frames,
    side=selected_side,
  )
  repaired_frame_indices = {
    index
    for index, frame in enumerate(validated_frames)
    if any(
      str((_landmark(frame, selected_side, joint) or {}).get("accepted_source") or "").startswith("pose_repair_")
      or (_landmark(frame, selected_side, joint) or {}).get("accepted_source") == "gap"
      for joint in REPAIR_JOINTS
    )
  }
  validator_estimated = int(validation.get("corrected_landmark_count") or 0) + int(
    validation.get("smoothed_landmark_count") or 0
  )
  estimated_count = (
    validator_estimated
    + temporal_counts["temporal_interpolated"]
    + temporal_counts["velocity_estimated"]
    + temporal_counts["hysteresis_hold"]
  )
  validation = dict(validation)
  validation["pose_repair_temporal_counts"] = temporal_counts
  return validated_frames, {
    "enabled": True,
    "selected_side": selected_side,
    "selected_side_overridden": selected_side != automatic_side,
    "tracking_side_confidence": side_confidence,
    "raw_frame_count": len(frames),
    "repaired_frame_count": len(repaired_frame_indices),
    "estimated_landmark_count": estimated_count,
    "gap_count": temporal_counts["gap"] + int(validation.get("visual_only_landmark_count") or 0),
    "interpolated_landmark_count": temporal_counts["temporal_interpolated"] + int(
      validation.get("interpolated_landmark_count") or 0
    ),
    "velocity_estimated_landmark_count": temporal_counts["velocity_estimated"],
    "segment_constrained_landmark_count": temporal_counts["segment_constrained"],
    "hysteresis_hold_landmark_count": temporal_counts["hysteresis_hold"],
    "raw_repair_debug": raw_repair_debug,
    "raw_repair_debug_truncated": raw_repair_debug_truncated,
    **quality,
    "pose_validation": validation,
  }
