from __future__ import annotations

import math
from typing import Any

from ..feedback_engine import build_depth_summary_debug, build_feedback
from ..metrics_calculator import (
  blended_point,
  clamp,
  hip_flexion_score,
  hip_depth_ratio,
  knee_flexion_score,
  point_for_side,
  select_depth_side,
  select_tracking_side_for_clip,
  squat_depth_assessment,
  torso_angle_change,
  torso_angle_from_vertical,
)
from ..pose_validator import validate_squat_pose_frames
from ..rep_detector import detect_reps
from .base import BaseExerciseAnalyzer


DEPTH_PARALLEL_THRESHOLD = 0.64
DEPTH_CONFIDENCE_THRESHOLD = 0.55
DEPTH_JUDGMENT_CONFIDENCE_THRESHOLD = 0.45
DEPTH_BOTTOM_WINDOW = 2


def _clean_depth_flags(rep_summaries: list[dict[str, Any]]) -> None:
  for rep in rep_summaries:
    flags = list(rep.get("flags") or [])
    depth_status = rep.get("depth_status") or rep.get("depthStatus")

    if depth_status != "insufficient_depth":
      flags = [flag for flag in flags if flag != "insufficient_depth"]
    if depth_status == "uncertain_depth" and "low_depth_confidence" not in flags:
      flags.append("low_depth_confidence")

    rep["flags"] = flags


def _public_point(point: dict[str, Any]) -> dict[str, Any]:
  return {
    "x": round(point["x"], 4),
    "y": round(point["y"], 4),
    "z": round(point.get("z", 0.0), 4),
    "visibility": round(point.get("visibility", 0.0), 3),
  }


def _build_pose_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
  # Reformat backend frames into the shape the client expects.
  def public_keypoint(name: str, point: dict[str, Any]) -> dict[str, Any]:
    manual_source = point.get("manual_source")
    user_pinned = bool(
      point.get("user_pinned")
      or point.get("manual_assisted")
      or manual_source in {"reference_pin", "pin_guided", "pin_estimated"}
    )
    return {
      "name": name,
      "x": point["x"],
      "y": point["y"],
      "confidence": point["visibility"],
      **(
        {"trackingState": point["tracking_state"]}
        if point.get("tracking_state") in {"reference", "guided", "automatic", "estimated"}
        else {}
      ),
      **({"manualSource": manual_source} if isinstance(manual_source, str) else {}),
      **({"userPinned": True} if user_pinned else {}),
    }

  return [
    {
      "time": frame["timestamp_ms"] / 1000,
      "keypoints": [
        public_keypoint(name, point)
        for name, point in frame["landmarks"].items()
      ],
    }
    for frame in frames
  ]


def _calculate_velocity_stats(
  *,
  frames: list[dict[str, Any]],
  start_index: int,
  end_index: int,
) -> dict[str, float]:
  # Estimate movement speed from hip motion over time.
  if end_index <= start_index:
    return {
      "avg_velocity": 0.0,
      "peak_velocity": 0.0,
    }

  hip_points = [
    (
      frames[index]["timestamp_ms"] / 1000,
      blended_point(frames[index], "hip")["y"],
    )
    for index in range(start_index, end_index + 1)
  ]
  velocities: list[float] = []
  total_distance = 0.0

  for previous, current in zip(hip_points, hip_points[1:]):
    previous_time, previous_y = previous
    current_time, current_y = current
    elapsed = current_time - previous_time

    if elapsed <= 0:
      continue

    distance = abs(current_y - previous_y)
    total_distance += distance
    velocities.append(distance / elapsed)

  duration = hip_points[-1][0] - hip_points[0][0]

  return {
    "avg_velocity": round(total_distance / duration, 3) if duration > 0 else 0.0,
    "peak_velocity": round(max(velocities), 3) if velocities else 0.0,
  }


def _calculate_landmark_jitter(frames: list[dict[str, Any]], side: str, subject_height: float) -> float:
  # Use second differences so normal descent/ascent motion is not mistaken for jitter.
  if len(frames) < 3 or subject_height <= 1e-6:
    return 0.0

  jitter_values: list[float] = []

  for joint in ("hip", "knee", "ankle"):
    points = [point_for_side(frame, side, joint) for frame in frames]

    for previous, current, following in zip(points, points[1:], points[2:]):
      if min(
        previous.get("visibility", 0.0),
        current.get("visibility", 0.0),
        following.get("visibility", 0.0),
      ) < 0.35:
        continue

      acceleration_x = following["x"] - (2 * current["x"]) + previous["x"]
      acceleration_y = following["y"] - (2 * current["y"]) + previous["y"]
      jitter_values.append(math.hypot(acceleration_x, acceleration_y) / subject_height)

  if not jitter_values:
    return 0.0

  return sum(jitter_values) / len(jitter_values)


def _depth_status(depth_assessment: dict[str, Any], *, bottom_landmarks_unreliable: bool = False) -> str:
  # Separate the coaching decision from the composite numeric score.
  if bottom_landmarks_unreliable or depth_assessment["confidence"] < DEPTH_JUDGMENT_CONFIDENCE_THRESHOLD:
    return "uncertain_depth"
  if depth_assessment.get("depth_classification"):
    return depth_assessment["depth_classification"]
  if depth_assessment["parallel_score"] >= DEPTH_PARALLEL_THRESHOLD:
    return "hit_depth"
  return "insufficient_depth"


def _has_unreliable_bottom_depth_landmarks(pose_validation: dict[str, Any], bottom_index: int) -> bool:
  return any(
    landmark.get("frame_index") == bottom_index
    and landmark.get("joint") in {"hip", "knee"}
    for landmark in pose_validation.get("unreliable_landmarks", [])
  )


def _has_unreliable_bottom_occlusion_landmarks(pose_validation: dict[str, Any], bottom_index: int) -> bool:
  return any(
    landmark.get("frame_index") == bottom_index
    and landmark.get("joint") in {"shoulder", "hip"}
    for landmark in pose_validation.get("unreliable_landmarks", [])
  )


def _rep_bottom_depth_assessment(
  *,
  frames: list[dict[str, Any]],
  bottom_index: int,
  pose_validation: dict[str, Any],
  selected_side_override: str | None = None,
) -> tuple[dict[str, Any], int]:
  # Use a small window around the detected bottom so one noisy hip frame cannot fail depth.
  start_index = max(0, bottom_index - DEPTH_BOTTOM_WINDOW)
  end_index = min(len(frames) - 1, bottom_index + DEPTH_BOTTOM_WINDOW)
  assessments: list[tuple[dict[str, Any], int]] = []

  for frame_index in range(start_index, end_index + 1):
    frame = frames[frame_index]
    automatic_side, selected_score, alternate_score, side_clarity = select_depth_side(frame)
    selected_side = (
      selected_side_override
      if selected_side_override in {"left", "right"}
      else automatic_side
    )
    if selected_side != automatic_side:
      selected_score, alternate_score = alternate_score, selected_score
    assessment = squat_depth_assessment(
      point_for_side(frame, selected_side, "shoulder"),
      point_for_side(frame, selected_side, "hip"),
      point_for_side(frame, selected_side, "knee"),
      point_for_side(frame, selected_side, "ankle"),
      frame_height_px=frame.get("frame_height"),
      selected_side=selected_side,
      selected_side_score=selected_score,
      alternate_side_score=alternate_score,
      side_clarity=side_clarity,
    )
    assessments.append((assessment, frame_index))

  bottom_assessment, _bottom_frame_index = next(
    item for item in assessments if item[1] == bottom_index
  )
  best_assessment, best_index = bottom_assessment, bottom_index
  bottom_classification = bottom_assessment.get("depth_classification")
  bottom_reliable = not (
    _has_unreliable_bottom_depth_landmarks(pose_validation, bottom_index)
    or _has_unreliable_bottom_occlusion_landmarks(pose_validation, bottom_index)
  )

  for assessment, frame_index in assessments:
    if frame_index == bottom_index:
      continue
    if assessment.get("depth_classification") != bottom_classification:
      continue
    if (
      assessment["confidence"] >= best_assessment["confidence"] + 0.12
      and assessment["parallel_score"] >= best_assessment["parallel_score"]
    ):
      best_assessment, best_index = assessment, frame_index

  if (
    best_assessment.get("depth_classification") == "insufficient_depth"
    and bottom_reliable
    and any(
      assessment.get("depth_classification") != "insufficient_depth"
      and assessment["confidence"] >= best_assessment["confidence"] - 0.08
      for assessment, _frame_index in assessments
    )
  ):
    best_assessment = {
      **best_assessment,
      "depth_classification": "uncertain_depth",
      "depth_reason": "bottom_window_disagreement",
    }

  if best_index != bottom_index:
    best_assessment = {
      **best_assessment,
      "selected_bottom_frame_offset": best_index - bottom_index,
      "selected_bottom_frame_index": best_index,
    }
    if best_assessment.get("depth_classification") != bottom_classification:
      best_assessment = {
        **best_assessment,
        "depth_classification": "uncertain_depth",
        "depth_reason": "scored_frame_disagreement",
      }

  if _has_unreliable_bottom_depth_landmarks(pose_validation, best_index):
    best_assessment = {
      **best_assessment,
      "bottom_depth_landmarks_unreliable": True,
    }
  elif (
    _has_unreliable_bottom_occlusion_landmarks(pose_validation, best_index)
    and best_assessment["parallel_score"] < DEPTH_PARALLEL_THRESHOLD
  ):
    best_assessment = {
      **best_assessment,
      "bottom_depth_landmarks_unreliable": True,
      "detected_bottom_occlusion_landmarks_unreliable": True,
    }
  elif (
    best_index != bottom_index
    and (
      _has_unreliable_bottom_depth_landmarks(pose_validation, bottom_index)
      or _has_unreliable_bottom_occlusion_landmarks(pose_validation, bottom_index)
    )
    and best_assessment["parallel_score"] < DEPTH_PARALLEL_THRESHOLD
  ):
    best_assessment = {
      **best_assessment,
      "bottom_depth_landmarks_unreliable": True,
      "detected_bottom_depth_landmarks_unreliable": True,
      "detected_bottom_occlusion_landmarks_unreliable": _has_unreliable_bottom_occlusion_landmarks(
        pose_validation,
        bottom_index,
      ),
    }

  return best_assessment, best_index


def _depth_evidence(
  *,
  frames: list[dict[str, Any]],
  bottom_index: int,
  depth_frame_index: int,
  depth_assessment: dict[str, Any],
) -> dict[str, Any]:
  bottom_frame = frames[bottom_index]
  depth_frame = frames[depth_frame_index]
  selected_side = depth_assessment.get("selected_side") or "left"
  hip = point_for_side(depth_frame, selected_side, "hip")
  knee = point_for_side(depth_frame, selected_side, "knee")
  shoulder = point_for_side(depth_frame, selected_side, "shoulder")
  ankle = point_for_side(depth_frame, selected_side, "ankle")
  selected_source = depth_frame.get("pose_backend") or "unknown"
  selected_model = depth_frame.get("landmark_model") or "unknown"

  return {
    "selected_side": selected_side,
    "selectedSide": selected_side,
    "selected_source": selected_source,
    "selectedSource": selected_source,
    "selected_model": selected_model,
    "selectedModel": selected_model,
    "bottom_index": bottom_index,
    "bottomFrameIndex": bottom_index,
    "bottom_timestamp_ms": bottom_frame["timestamp_ms"],
    "depth_frame_index": depth_frame_index,
    "depth_timestamp_ms": depth_frame["timestamp_ms"],
    "scored_frame_differs_from_bottom": depth_frame_index != bottom_index,
    "scoring_landmarks": {
      "shoulder": _public_point(shoulder),
      "hip": _public_point(hip),
      "knee": _public_point(knee),
      "ankle": _public_point(ankle),
    },
    "hip_knee_delta": depth_assessment["hip_knee_delta"],
    "parallel_score": depth_assessment["parallel_score"],
    "depth_confidence": depth_assessment["confidence"],
    "hipY": round(hip["y"], 4),
    "kneeY": round(knee["y"], 4),
    "ankleY": round(ankle["y"], 4),
    "hipConfidence": round(hip.get("visibility", 0.0), 3),
    "kneeConfidence": round(knee.get("visibility", 0.0), 3),
    "ankleConfidence": round(ankle.get("visibility", 0.0), 3),
    "estimatedHipCreaseY": depth_assessment["estimated_hip_crease_y"],
    "estimatedKneeTopY": depth_assessment["estimated_knee_top_y"],
    "depthDeltaPx": depth_assessment["depth_delta_px"],
    "depthTolerancePx": depth_assessment["depth_tolerance_px"],
    "depthClassification": depth_assessment["depth_classification"],
    "depthReason": depth_assessment["depth_reason"],
    "estimated_hip_crease_y": depth_assessment["estimated_hip_crease_y"],
    "estimated_knee_top_y": depth_assessment["estimated_knee_top_y"],
    "depth_delta_px": depth_assessment["depth_delta_px"],
    "depth_tolerance_px": depth_assessment["depth_tolerance_px"],
    "depth_classification": depth_assessment["depth_classification"],
    "depth_reason": depth_assessment["depth_reason"],
  }


def _plate_rack_occlusion_suspected(
  *,
  frame: dict[str, Any],
  selected_side: str,
  subject_height: float,
) -> bool:
  shoulder = point_for_side(frame, selected_side, "shoulder")
  hip = point_for_side(frame, selected_side, "hip")
  knee = point_for_side(frame, selected_side, "knee")
  torso_length = math.hypot(shoulder["x"] - hip["x"], shoulder["y"] - hip["y"])
  thigh_length = math.hypot(hip["x"] - knee["x"], hip["y"] - knee["y"])
  normalized_torso = torso_length / max(subject_height, 1e-6)

  return (
    normalized_torso < 0.12
    or torso_length < 0.70 * max(thigh_length, 1e-6)
    or (
      abs(shoulder["x"] - hip["x"]) < 0.07
      and abs(shoulder["y"] - hip["y"]) < 0.10
    )
  )


class SquatAnalyzer(BaseExerciseAnalyzer):
  def _build_quality_report(
    self,
    *,
    frames: list[dict[str, Any]],
    sampled_frame_count: int | None = None,
    selected_side_override: str | None = None,
  ) -> dict[str, Any]:
    # Quality metrics explain how trustworthy the clip is.
    if not frames:
      return {
        "quality_score": 0.0,
        "pose_coverage": 0.0,
        "lower_body_visibility": 0.0,
        "subject_height": 0.0,
        "side_view_score": 0.0,
        "landmark_jitter": 0.0,
        "selected_side": None,
        "tracking_side_confidence": 0.0,
        "sampled_frame_count": sampled_frame_count or 0,
        "pose_frame_count": 0,
        "quality_flags": ["low_pose_coverage"],
      }

    selected_side, tracking_confidence = select_tracking_side_for_clip(frames)
    selected_side = selected_side_override or selected_side
    pose_coverage = len(frames) / max(sampled_frame_count or len(frames), 1)
    lower_body_visibility = sum(
      (
        point_for_side(frame, selected_side, "hip")["visibility"]
        + point_for_side(frame, selected_side, "knee")["visibility"]
        + point_for_side(frame, selected_side, "ankle")["visibility"]
      ) / 3
      for frame in frames
    ) / len(frames)
    subject_heights: list[float] = []
    side_view_scores: list[float] = []

    for frame in frames:
      landmarks = frame["landmarks"]
      tracked_points = [
        point_for_side(frame, selected_side, "shoulder"),
        point_for_side(frame, selected_side, "hip"),
        point_for_side(frame, selected_side, "knee"),
        point_for_side(frame, selected_side, "ankle"),
      ]
      y_values = [point["y"] for point in tracked_points if point["visibility"] >= 0.35]

      if y_values:
        subject_heights.append(max(y_values) - min(y_values))

      shoulder_gap = abs(landmarks["left_shoulder"]["x"] - landmarks["right_shoulder"]["x"])
      hip_gap = abs(landmarks["left_hip"]["x"] - landmarks["right_hip"]["x"])
      side_view_scores.append(clamp(1.0 - ((shoulder_gap + hip_gap) / 0.42), 0.0, 1.0))

    subject_height = sum(subject_heights) / max(len(subject_heights), 1)
    side_view_score = sum(side_view_scores) / max(len(side_view_scores), 1)
    landmark_jitter = _calculate_landmark_jitter(frames, selected_side, subject_height)
    quality_flags: list[str] = []

    if pose_coverage < 0.55:
      quality_flags.append("low_pose_coverage")
    if lower_body_visibility < 0.58:
      quality_flags.append("lower_body_occluded")
    if subject_height < 0.32:
      quality_flags.append("subject_too_small")
    if side_view_score < 0.42:
      quality_flags.append("camera_not_side_view")
    if landmark_jitter > 0.055:
      quality_flags.append("excessive_landmark_jitter")
    if tracking_confidence < 0.10:
      quality_flags.append("ambiguous_tracking_side")

    component_scores = [
      clamp(pose_coverage, 0.0, 1.0),
      clamp(lower_body_visibility, 0.0, 1.0),
      clamp(subject_height / 0.55, 0.0, 1.0),
      clamp(side_view_score, 0.0, 1.0),
      clamp(1.0 - (landmark_jitter / 0.09), 0.0, 1.0),
    ]
    quality_score = sum(component_scores) / len(component_scores)

    return {
      "quality_score": round(quality_score, 3),
      "pose_coverage": round(pose_coverage, 3),
      "lower_body_visibility": round(lower_body_visibility, 3),
      "subject_height": round(subject_height, 3),
      "side_view_score": round(side_view_score, 3),
      "landmark_jitter": round(landmark_jitter, 3),
      "selected_side": selected_side,
      "tracking_side_confidence": tracking_confidence,
      "sampled_frame_count": sampled_frame_count or len(frames),
      "pose_frame_count": len(frames),
      "quality_flags": quality_flags,
    }

  def analyze(
    self,
    *,
    video_id: str,
    exercise_type: str,
    view_type: str,
    frames: list[dict[str, Any]],
    sampled_frame_count: int | None = None,
    selected_side_override: str | None = None,
  ) -> dict[str, Any]:
    # Squat analysis combines quality checks, rep detection, and feedback.
    frames, pose_validation = validate_squat_pose_frames(
      frames,
      selected_side_override=selected_side_override,
    )
    diagnostics = self._build_quality_report(
      frames=frames,
      sampled_frame_count=sampled_frame_count,
      selected_side_override=pose_validation.get("selected_side"),
    )
    diagnostics["pose_validation"] = pose_validation
    selected_side = diagnostics["selected_side"] or "left"
    validation_penalty = pose_validation.get("quality_score_penalty", 0.0)

    if validation_penalty:
      diagnostics["quality_score"] = round(
        clamp(diagnostics.get("quality_score", 0.0) - (validation_penalty * 0.25), 0.0, 1.0),
        3,
      )

    if (
      pose_validation.get("corrected_landmark_count", 0)
      or pose_validation.get("rejected_landmark_count", 0)
    ) and "unreliable_pose_landmarks" not in diagnostics["quality_flags"]:
      diagnostics["quality_flags"].append("unreliable_pose_landmarks")

    hip_depths = []
    knee_flexions = []
    hip_flexions = []

    for frame in frames:
      # Build the motion signals used by rep detection.
      shoulder = point_for_side(frame, selected_side, "shoulder")
      hip = point_for_side(frame, selected_side, "hip")
      knee = point_for_side(frame, selected_side, "knee")
      ankle = point_for_side(frame, selected_side, "ankle")
      hip_depths.append(hip_depth_ratio(shoulder, hip, ankle))
      knee_flexions.append(knee_flexion_score(hip, knee, ankle))
      hip_flexions.append(hip_flexion_score(shoulder, hip, knee))

    reps, rep_detection = detect_reps(
      hip_depths=hip_depths,
      knee_flexions=knee_flexions,
      hip_flexions=hip_flexions,
      frames=frames,
    )
    diagnostics["rep_detection"] = rep_detection

    if rep_detection.get("reason") and rep_detection["reason"] not in diagnostics["quality_flags"]:
      diagnostics["quality_flags"].append(rep_detection["reason"])

    rep_summaries: list[dict[str, Any]] = []

    for rep_index, rep in enumerate(reps, start=1):
      # Summarize each rep with timing, speed, and form metrics.
      start_frame = frames[rep["start_index"]]
      bottom_frame = frames[rep["bottom_index"]]
      duration_seconds = max(
        (rep["end_timestamp_ms"] - rep["start_timestamp_ms"]) / 1000,
        0.001,
      )
      velocity_stats = _calculate_velocity_stats(
        frames=frames,
        start_index=rep["start_index"],
        end_index=rep["end_index"],
      )

      start_shoulder = point_for_side(start_frame, selected_side, "shoulder")
      start_hip = point_for_side(start_frame, selected_side, "hip")
      bottom_shoulder = point_for_side(bottom_frame, selected_side, "shoulder")
      bottom_hip = point_for_side(bottom_frame, selected_side, "hip")

      start_torso = torso_angle_from_vertical(start_shoulder, start_hip)
      bottom_torso = torso_angle_from_vertical(bottom_shoulder, bottom_hip)
      depth_assessment, depth_frame_index = _rep_bottom_depth_assessment(
        frames=frames,
        bottom_index=rep["bottom_index"],
        pose_validation=pose_validation,
        selected_side_override=selected_side,
      )
      rep_depth_side = depth_assessment.get("selected_side") or selected_side
      depth_score = depth_assessment["score"]
      depth_status = _depth_status(
        depth_assessment,
        bottom_landmarks_unreliable=depth_assessment.get("bottom_depth_landmarks_unreliable", False),
      )
      torso_delta = torso_angle_change(start_torso, bottom_torso)
      depth_evidence = _depth_evidence(
        frames=frames,
        bottom_index=rep["bottom_index"],
        depth_frame_index=depth_frame_index,
        depth_assessment=depth_assessment,
      )
      occlusion_suspected = _plate_rack_occlusion_suspected(
        frame=frames[depth_frame_index],
        selected_side=rep_depth_side,
        subject_height=diagnostics.get("subject_height", 0.0),
      ) or depth_assessment.get("detected_bottom_occlusion_landmarks_unreliable", False)
      if occlusion_suspected and depth_status == "insufficient_depth":
        depth_status = "uncertain_depth"
        depth_assessment = {
          **depth_assessment,
          "plate_rack_occlusion_suspected": True,
          "depth_status_downgraded_by_occlusion": True,
          "depth_classification": "uncertain_depth",
          "depth_reason": "occlusion_uncertain",
        }
      depth_evidence["plate_rack_occlusion_suspected"] = occlusion_suspected
      depth_evidence["depth_status"] = depth_status
      depth_evidence["depthStatus"] = depth_status
      depth_evidence["depth_classification"] = depth_status
      depth_evidence["depthClassification"] = depth_status
      depth_evidence["depth_reason"] = depth_assessment.get("depth_reason")
      depth_evidence["depthReason"] = depth_assessment.get("depth_reason")
      depth_evidence["depth_status_downgraded_by_occlusion"] = depth_assessment.get(
        "depth_status_downgraded_by_occlusion",
        False,
      )

      flags: list[str] = []
      if depth_status == "insufficient_depth":
        flags.append("insufficient_depth")
      if depth_status == "uncertain_depth" or depth_assessment["confidence"] < DEPTH_CONFIDENCE_THRESHOLD:
        flags.append("low_depth_confidence")
      if bottom_torso > 42 or torso_delta > 18:
        flags.append("forward_lean")

      rep_summaries.append(
        {
          "rep_index": rep_index,
          "repIndex": rep_index,
          "startTime": rep["start_timestamp_ms"] / 1000,
          "endTime": rep["end_timestamp_ms"] / 1000,
          "duration": round(duration_seconds, 3),
          "repSpeed": round(1 / duration_seconds, 3),
          "avgVelocity": velocity_stats["avg_velocity"],
          "peakVelocity": velocity_stats["peak_velocity"],
          "depthScore": depth_score,
          "depthConfidence": depth_assessment["confidence"],
          "depthStatus": depth_status,
          "depthFrameIndex": depth_frame_index,
          "depthTimestampMs": frames[depth_frame_index]["timestamp_ms"],
          "bottomIndex": rep["bottom_index"],
          "bottomTimestampMs": rep["bottom_timestamp_ms"],
          "selectedSide": rep_depth_side,
          "selectedModel": depth_evidence["selectedModel"],
          "selectedSource": depth_evidence["selectedSource"],
          "depthReason": depth_evidence["depthReason"],
          "torsoAngleChangeDeg": torso_delta,
          "depth_score": depth_score,
          "depth_confidence": depth_assessment["confidence"],
          "depth_status": depth_status,
          "depth_frame_index": depth_frame_index,
          "depth_timestamp_ms": frames[depth_frame_index]["timestamp_ms"],
          "bottom_index": rep["bottom_index"],
          "bottom_timestamp_ms": rep["bottom_timestamp_ms"],
          "selected_side": rep_depth_side,
          "selected_model": depth_evidence["selected_model"],
          "selected_source": depth_evidence["selected_source"],
          "depth_reason": depth_evidence["depth_reason"],
          "depth_components": depth_assessment,
          "depth_evidence": depth_evidence,
          "torso_angle": round(bottom_torso, 2),
          "torso_angle_change": torso_delta,
          "estimated_body_velocity": velocity_stats,
          "flags": flags,
          "timestamps_ms": {
            "start": rep["start_timestamp_ms"],
            "bottom": rep["bottom_timestamp_ms"],
            "end": rep["end_timestamp_ms"],
          },
        }
      )

    _clean_depth_flags(rep_summaries)
    diagnostics["depth_status_counts"] = {
      "hit_depth_count": sum(1 for rep in rep_summaries if rep["depth_status"] == "hit_depth"),
      "insufficient_depth_count": sum(
        1 for rep in rep_summaries if rep["depth_status"] == "insufficient_depth"
      ),
      "uncertain_depth_count": sum(
        1 for rep in rep_summaries if rep["depth_status"] == "uncertain_depth"
      ),
    }
    diagnostics["depth_summary_debug"] = build_depth_summary_debug(rep_summaries)
    diagnostics["depth_debug"] = [
      {
        "rep_index": rep["rep_index"],
        "depth_status": rep["depth_status"],
        "selected_side": rep["selected_side"],
        "selectedSide": rep["selectedSide"],
        "selected_model": rep["selected_model"],
        "selectedModel": rep["selectedModel"],
        "selected_source": rep["selected_source"],
        "selectedSource": rep["selectedSource"],
        "bottom_index": rep["bottom_index"],
        "bottomFrameIndex": rep["bottomIndex"],
        "bottom_timestamp_ms": rep["bottom_timestamp_ms"],
        "depth_frame_index": rep["depth_frame_index"],
        "depth_timestamp_ms": rep["depth_timestamp_ms"],
        "hipY": rep["depth_evidence"]["hipY"],
        "kneeY": rep["depth_evidence"]["kneeY"],
        "ankleY": rep["depth_evidence"]["ankleY"],
        "hipConfidence": rep["depth_evidence"]["hipConfidence"],
        "kneeConfidence": rep["depth_evidence"]["kneeConfidence"],
        "ankleConfidence": rep["depth_evidence"]["ankleConfidence"],
        "estimatedHipCreaseY": rep["depth_evidence"]["estimatedHipCreaseY"],
        "estimatedKneeTopY": rep["depth_evidence"]["estimatedKneeTopY"],
        "depthDeltaPx": rep["depth_evidence"]["depthDeltaPx"],
        "depthTolerancePx": rep["depth_evidence"]["depthTolerancePx"],
        "depthClassification": rep["depth_evidence"]["depthClassification"],
        "depthReason": rep["depth_evidence"]["depthReason"],
        "hip_knee_delta": rep["depth_components"]["hip_knee_delta"],
        "parallel_score": rep["depth_components"]["parallel_score"],
        "depth_confidence": rep["depth_confidence"],
        "scored_frame_differs_from_bottom": rep["depth_evidence"]["scored_frame_differs_from_bottom"],
        "plate_rack_occlusion_suspected": rep["depth_evidence"]["plate_rack_occlusion_suspected"],
      }
      for rep in rep_summaries
    ]

    if any(rep["depth_evidence"]["plate_rack_occlusion_suspected"] for rep in rep_summaries):
      diagnostics["plate_rack_occlusion_suspected"] = True
      if "plate_rack_occlusion_suspected" not in diagnostics["quality_flags"]:
        diagnostics["quality_flags"].append("plate_rack_occlusion_suspected")

    summary_flags, coach_feedback = build_feedback(rep_summaries, diagnostics)

    return {
      "video_id": video_id,
      "exercise": exercise_type,
      "view": view_type,
      "analysis_limited": False,
      "rep_count": len(rep_summaries),
      "reps": rep_summaries,
      "summary_flags": summary_flags,
      "coach_feedback": coach_feedback,
      "diagnostics": diagnostics,
      "videoId": video_id,
      "cameraView": view_type,
      "duration": frames[-1]["timestamp_ms"] / 1000 if frames else 0,
      "poseFrames": _build_pose_frames(frames),
      "summaryFlags": summary_flags,
      "videoQuality": {
        "overallQuality": diagnostics.get("quality_score", 0),
        "poseCoverage": diagnostics.get("pose_coverage", 0),
        "lowerBodyVisibility": diagnostics.get("lower_body_visibility", 0),
        "sideViewConfidence": diagnostics.get("side_view_score", 0),
        "squatMotionSignal": diagnostics.get("rep_detection", {}).get("motion_amplitude", 0),
        "landmarkJitter": diagnostics.get("landmark_jitter", 0),
        "poseValidationReliability": round(1.0 - validation_penalty, 3),
      },
      "coachingFeedback": coach_feedback,
    }
