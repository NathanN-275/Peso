from __future__ import annotations

import copy
from typing import Any

from ..metrics_calculator import clamp, joint_angle
from ..rep_detector import detect_reps
from .base import BaseExerciseAnalyzer
from .squat import _build_pose_frames


FRONT_BODY_LANDMARKS = tuple(
  f"{side}_{joint}"
  for side in ("left", "right")
  for joint in ("shoulder", "hip", "knee", "ankle")
)
FRONT_PRIMARY_LANDMARKS = tuple(
  f"{side}_{joint}"
  for side in ("left", "right")
  for joint in ("knee", "ankle")
)
MIN_RELIABLE_VISIBILITY = 0.35
MAX_ESTIMATED_GAP_FRAMES = 3


def _landmark(frame: dict[str, Any], name: str) -> dict[str, Any] | None:
  point = (frame.get("landmarks") or {}).get(name)
  return point if isinstance(point, dict) else None


def _is_reliable(point: dict[str, Any] | None) -> bool:
  return bool(
    point
    and isinstance(point.get("x"), (int, float))
    and isinstance(point.get("y"), (int, float))
    and float(point.get("visibility") or 0.0) >= MIN_RELIABLE_VISIBILITY
  )


def _is_front_reliable(point: dict[str, Any] | None) -> bool:
  if not _is_reliable(point):
    return False
  accepted_source = str(point.get("accepted_source") or "")
  tracking_state = str(point.get("tracking_state") or "")
  return (
    accepted_source != "gap"
    and not (
      tracking_state == "estimated"
      and accepted_source != "front_short_gap_estimate"
    )
  )


def _mark_front_gap(target: dict[str, Any]) -> None:
  target.update({
    "visibility": 0.0,
    "tracking_state": "uncertain",
    "accepted_source": "gap",
    "chain_valid": False,
    "visual_only": True,
    "front_gap_estimated": False,
  })


def repair_front_pose_frames(
  frames: list[dict[str, Any]],
  *,
  max_gap_frames: int = MAX_ESTIMATED_GAP_FRAMES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
  """Interpolate short bilateral landmark gaps without changing joint identity."""
  repaired = copy.deepcopy(frames)
  estimated_counts = {name: 0 for name in FRONT_BODY_LANDMARKS}
  gap_counts = {name: 0 for name in FRONT_BODY_LANDMARKS}
  identity_switch_counts = {joint: 0 for joint in ("shoulder", "hip", "knee", "ankle")}

  for joint in identity_switch_counts:
    differences = []
    for current in repaired:
      left = _landmark(current, f"left_{joint}")
      right = _landmark(current, f"right_{joint}")
      if _is_front_reliable(left) and _is_front_reliable(right):
        differences.append(float(left["x"]) - float(right["x"]))
    expected_sign = 1.0 if sum(value > 0 for value in differences) >= sum(value < 0 for value in differences) else -1.0
    for current in repaired:
      left = _landmark(current, f"left_{joint}")
      right = _landmark(current, f"right_{joint}")
      if (
        _is_front_reliable(left)
        and _is_front_reliable(right)
        and (float(left["x"]) - float(right["x"])) * expected_sign <= 0
      ):
        _mark_front_gap(left)
        _mark_front_gap(right)
        identity_switch_counts[joint] += 1

  for name in FRONT_BODY_LANDMARKS:
    index = 0
    while index < len(repaired):
      if _is_front_reliable(_landmark(repaired[index], name)):
        index += 1
        continue

      gap_start = index
      while index < len(repaired) and not _is_front_reliable(_landmark(repaired[index], name)):
        index += 1
      gap_end = index - 1
      gap_length = gap_end - gap_start + 1
      previous_index = gap_start - 1
      next_index = index
      if (
        gap_length > max_gap_frames
        or previous_index < 0
        or next_index >= len(repaired)
      ):
        for frame_index in range(gap_start, gap_end + 1):
          target = repaired[frame_index].setdefault("landmarks", {}).setdefault(name, {})
          _mark_front_gap(target)
          gap_counts[name] += 1
        continue

      previous = _landmark(repaired[previous_index], name)
      following = _landmark(repaired[next_index], name)
      if not _is_front_reliable(previous) or not _is_front_reliable(following):
        continue

      for offset, frame_index in enumerate(range(gap_start, gap_end + 1), start=1):
        progress = offset / (gap_length + 1)
        original = _landmark(repaired[frame_index], name) or {}
        estimate = {
          **original,
          "x": float(previous["x"]) + ((float(following["x"]) - float(previous["x"])) * progress),
          "y": float(previous["y"]) + ((float(following["y"]) - float(previous["y"])) * progress),
          "z": float(previous.get("z", 0.0))
          + ((float(following.get("z", 0.0)) - float(previous.get("z", 0.0))) * progress),
          "visibility": min(
            float(previous.get("visibility") or 0.0),
            float(following.get("visibility") or 0.0),
            0.48,
          ),
          "tracking_state": "estimated",
          "accepted_source": "front_short_gap_estimate",
          "chain_valid": True,
          "visual_only": False,
          "front_gap_estimated": True,
        }
        repaired[frame_index].setdefault("landmarks", {})[name] = estimate
        estimated_counts[name] += 1

  estimated_count = sum(estimated_counts.values())
  return repaired, {
    "enabled": True,
    "mode": "front_bilateral",
    "max_gap_frames": max_gap_frames,
    "estimated_landmark_count": estimated_count,
    "estimated_counts": estimated_counts,
    "gap_landmark_count": sum(gap_counts.values()),
    "gap_counts": gap_counts,
    "identity_switch_frame_count": sum(identity_switch_counts.values()),
    "identity_switch_counts": identity_switch_counts,
  }


def _side_knee_flexion(frame: dict[str, Any], side: str) -> tuple[float, float] | None:
  hip = _landmark(frame, f"{side}_hip")
  knee = _landmark(frame, f"{side}_knee")
  ankle = _landmark(frame, f"{side}_ankle")
  if not all(_is_reliable(point) for point in (hip, knee, ankle)):
    return None
  angle = joint_angle(hip, knee, ankle)
  score = clamp((175.0 - angle) / 110.0, 0.0, 1.0)
  confidence = min(
    float(hip.get("visibility") or 0.0),
    float(knee.get("visibility") or 0.0),
    float(ankle.get("visibility") or 0.0),
  )
  return score, confidence


def _mean_axis_point(
  frame: dict[str, Any],
  joint: str,
) -> tuple[float, float] | None:
  points = [
    point
    for point in (
      _landmark(frame, f"left_{joint}"),
      _landmark(frame, f"right_{joint}"),
    )
    if _is_reliable(point)
  ]
  if not points:
    return None
  total_weight = sum(max(float(point.get("visibility") or 0.0), 0.01) for point in points)
  return (
    sum(float(point["y"]) * max(float(point.get("visibility") or 0.0), 0.01) for point in points)
    / total_weight,
    min(float(point.get("visibility") or 0.0) for point in points),
  )


def _front_motion_signals(
  frames: list[dict[str, Any]],
) -> tuple[list[float], list[float], list[float]]:
  knee_scores: list[float] = []
  raw_leg_spans: list[float] = []

  for frame in frames:
    side_scores = [
      result
      for side in ("left", "right")
      if (result := _side_knee_flexion(frame, side)) is not None
    ]
    if side_scores:
      total_confidence = sum(result[1] for result in side_scores)
      knee_scores.append(
        sum(result[0] * result[1] for result in side_scores) / max(total_confidence, 1e-6)
      )
    else:
      knee_scores.append(knee_scores[-1] if knee_scores else 0.0)

    hip = _mean_axis_point(frame, "hip")
    ankle = _mean_axis_point(frame, "ankle")
    raw_leg_spans.append(
      max(float(ankle[0]) - float(hip[0]), 0.0)
      if hip is not None and ankle is not None
      else raw_leg_spans[-1] if raw_leg_spans else 0.0
    )

  positive_spans = sorted(span for span in raw_leg_spans if span > 0)
  standing_span = (
    positive_spans[min(round((len(positive_spans) - 1) * 0.8), len(positive_spans) - 1)]
    if positive_spans
    else 1.0
  )
  pelvis_drop = [
    clamp(1.0 - (span / max(standing_span, 1e-6)), 0.0, 1.0)
    for span in raw_leg_spans
  ]
  fused = [
    (knee * 0.72) + (drop * 0.28)
    for knee, drop in zip(knee_scores, pelvis_drop)
  ]
  return fused, knee_scores, pelvis_drop


def _joint_coverage(
  frames: list[dict[str, Any]],
) -> dict[str, float]:
  if not frames:
    return {name: 0.0 for name in FRONT_BODY_LANDMARKS}
  return {
    name: round(
      sum(_is_reliable(_landmark(frame, name)) for frame in frames) / len(frames),
      3,
    )
    for name in FRONT_BODY_LANDMARKS
  }


class FrontSquatAnalyzer(BaseExerciseAnalyzer):
  def analyze(
    self,
    *,
    video_id: str,
    exercise_type: str,
    view_type: str,
    frames: list[dict[str, Any]],
    sampled_frame_count: int | None = None,
    repair_diagnostics: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    coverage = _joint_coverage(frames)
    pose_coverage = len(frames) / max(sampled_frame_count or len(frames), 1)
    primary_coverage = (
      sum(coverage[name] for name in FRONT_PRIMARY_LANDMARKS)
      / max(len(FRONT_PRIMARY_LANDMARKS), 1)
    )
    fused_motion, knee_flexion, pelvis_drop = _front_motion_signals(frames)
    reps, rep_detection = detect_reps(
      hip_depths=fused_motion,
      knee_flexions=knee_flexion,
      hip_flexions=pelvis_drop,
      frames=frames,
      high_threshold_ratio=0.45,
      low_threshold_ratio=0.30,
      minimum_half_duration_ms=250,
      peak_spacing_ms=900,
      boundary_search_ms=3200,
    )

    quality_flags: list[str] = []
    if pose_coverage < 0.55:
      quality_flags.append("low_pose_coverage")
    if primary_coverage < 0.58:
      quality_flags.append("lower_body_occluded")
    if rep_detection.get("reason"):
      quality_flags.append(str(rep_detection["reason"]))

    rep_summaries = []
    for rep_index, rep in enumerate(reps, start=1):
      start_ms = int(rep["start_timestamp_ms"])
      bottom_ms = int(rep["bottom_timestamp_ms"])
      end_ms = int(rep["end_timestamp_ms"])
      bottom_frame = frames[int(rep["bottom_index"])]
      side_confidences = [
        result[1]
        for side in ("left", "right")
        if (result := _side_knee_flexion(bottom_frame, side)) is not None
      ]
      confidence = sum(side_confidences) / len(side_confidences) if side_confidences else 0.0
      flags = ["low_tracking_confidence"] if confidence < 0.45 else []
      rep_summaries.append({
        "rep_index": rep_index,
        "repIndex": rep_index,
        "startTime": start_ms / 1000,
        "bottomTime": bottom_ms / 1000,
        "bottomTimestampMs": bottom_ms,
        "bottom_index": int(rep["bottom_index"]),
        "bottomIndex": int(rep["bottom_index"]),
        "endTime": end_ms / 1000,
        "duration": round(max(end_ms - start_ms, 0) / 1000, 3),
        "confidence": round(confidence, 3),
        "flags": flags,
        "timestamps_ms": {
          "start": start_ms,
          "bottom": bottom_ms,
          "end": end_ms,
        },
      })

    summary_flags: list[str] = []
    coaching_feedback: list[str] = []
    if not rep_summaries:
      summary_flags.append("No clear squat reps detected")
      coaching_feedback.append(
        "Include the standing start, full descent, and return to standing with both knees and ankles visible."
      )
    elif quality_flags:
      summary_flags.append("Tracking confidence was limited")
      coaching_feedback.append(
        "Keep both knees and ankles visible and the camera steady for clearer front-view tracking."
      )
    else:
      coaching_feedback.append(
        "Front-view tracking completed. Review the knee and ankle trails for movement patterns."
      )

    diagnostics = {
      "quality_score": round(clamp((pose_coverage * 0.45) + (primary_coverage * 0.55), 0.0, 1.0), 3),
      "pose_coverage": round(pose_coverage, 3),
      "lower_body_visibility": round(primary_coverage, 3),
      "quality_flags": quality_flags,
      "rep_detection": rep_detection,
      "front_tracking": {
        "joint_coverage": coverage,
        "primary_joint_coverage": round(primary_coverage, 3),
        "estimated_landmark_count": int(
          (repair_diagnostics or {}).get("estimated_landmark_count") or 0
        ),
        "estimated_counts": (repair_diagnostics or {}).get("estimated_counts") or {},
        "gap_landmark_count": int(
          (repair_diagnostics or {}).get("gap_landmark_count") or 0
        ),
        "gap_counts": (repair_diagnostics or {}).get("gap_counts") or {},
        "identity_switch_frame_count": int(
          (repair_diagnostics or {}).get("identity_switch_frame_count") or 0
        ),
        "identity_switch_counts": (
          (repair_diagnostics or {}).get("identity_switch_counts") or {}
        ),
      },
    }
    capabilities = {
      "poseTracking": True,
      "repCounting": True,
      "depthAssessment": False,
      "torsoAssessment": False,
      "kneeAlignmentAssessment": False,
      "barbellTracking": False,
    }
    return {
      "video_id": video_id,
      "videoId": video_id,
      "exercise": exercise_type,
      "view": view_type,
      "cameraView": view_type,
      "analysis_limited": False,
      "analysisMode": "front_squat_tracking_v1",
      "analysisCapabilities": capabilities,
      "rep_count": len(rep_summaries),
      "reps": rep_summaries,
      "summary_flags": summary_flags,
      "summaryFlags": summary_flags,
      "coach_feedback": coaching_feedback,
      "coachingFeedback": coaching_feedback,
      "duration": frames[-1]["timestamp_ms"] / 1000 if frames else 0,
      "poseFrames": _build_pose_frames(frames),
      "videoQuality": {
        "overallQuality": diagnostics["quality_score"],
        "poseCoverage": diagnostics["pose_coverage"],
        "lowerBodyVisibility": diagnostics["lower_body_visibility"],
        "squatMotionSignal": rep_detection.get("motion_amplitude", 0),
      },
      "diagnostics": diagnostics,
    }
