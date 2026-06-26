from __future__ import annotations

import copy
import logging
import tempfile
import time
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .barbell_tracker import BarbellTracker
from .feedback_engine import build_depth_summary_debug, build_feedback
from .exercises.squat import SquatAnalyzer
from .manual_tracking import (
  barbell_track_priors,
  fuse_manual_body_tracks,
  track_manual_anchors,
  validate_tracking_setup,
)
from .pose_fallback import analysis_needs_pose_fallback
from .pose_estimator import PoseEstimator
from .pose_validator import is_body_point_occluded_by_plate, validate_squat_pose_frames
from ..services.config import get_settings
from ..services.storage_service import IMMUTABLE_CACHE_CONTROL_SECONDS, StorageService
from ..services.video_assets import (
  build_playback_storage_path,
  build_thumbnail_storage_path,
  compress_video_for_playback,
  create_video_thumbnail,
)
from ..services.video_repository import VideoRepository


logger = logging.getLogger(__name__)


def _is_squat_variation(exercise_type: str) -> bool:
  return exercise_type.strip().lower().endswith("squat")


def _apply_tracking_assistance(
  *,
  file_path: str,
  video: dict[str, Any],
  estimation: dict[str, Any],
) -> dict[str, Any]:
  requested_setup = video.get("tracking_setup")
  validated_setup, validation_error = validate_tracking_setup(
    requested_setup,
    duration_ms=estimation.get("duration_ms"),
  )
  assistance: dict[str, Any] = {
    "requestedMode": "pins" if requested_setup is not None else "automatic",
    "actualMode": "automatic",
    "used": False,
    "fallbackReason": validation_error,
    "selectedSide": None,
    "fusedLandmarkCount": 0,
    "directlyAnchoredLandmarkCount": 0,
    "blendedLandmarkCount": 0,
    "fallbackLandmarkCount": 0,
    "rejectedTrackCount": 0,
    "rejectionReasons": {},
    "coverage": {},
    "velocityCapCount": 0,
    "velocityCapCounts": {},
    "barbellSeedUsed": False,
    "manualBarbellPointCount": 0,
    "automaticBarbellPointCount": 0,
    "upperBackAnchorKey": "upper_back",
    "upperBackAnchorSemantics": "upper_back_anchor",
    "upperBackAnchorUsedCount": 0,
    "upperBackAnchorCoverage": 0.0,
    "pinOwnedLandmarkCount": 0,
    "modelDivergenceAcceptedCount": 0,
    "bodyBarbellOccluderRejectionCount": 0,
    "bodyPinFrames": [],
    "sourceCounts": {},
    "reference": None,
  }
  assisted_estimation = dict(estimation)
  assisted_estimation["tracking_assistance"] = assistance
  assisted_estimation["manual_tracking"] = {"tracks": {}}

  if validated_setup is None:
    if requested_setup is not None:
      assistance["actualMode"] = "automatic_fallback"
    return assisted_estimation

  try:
    width = int(estimation.get("processed_frame_width") or estimation.get("frame_width") or 0)
    height = int(estimation.get("processed_frame_height") or estimation.get("frame_height") or 0)
    tracking = track_manual_anchors(
      file_path,
      setup=validated_setup,
      pose_frames=estimation.get("frames") or [],
      fps=estimation.get("fps"),
      width=width,
      height=height,
    )
    fused_frames, fusion = fuse_manual_body_tracks(
      estimation.get("frames") or [],
      setup=validated_setup,
      tracking=tracking,
    )
    assisted_estimation["frames"] = fused_frames
    assisted_estimation["manual_tracking"] = tracking
    assistance.update(
      {
        "actualMode": "pin_assisted" if fusion["used"] else "automatic_fallback",
        "used": bool(fusion["used"]),
        "fallbackReason": None if fusion["used"] else "manual_tracks_unavailable",
        "selectedSide": fusion.get("selected_side"),
        "fusedLandmarkCount": int(fusion.get("fused_landmark_count") or 0),
        "directlyAnchoredLandmarkCount": int(
          fusion.get("directly_anchored_landmark_count") or 0
        ),
        "blendedLandmarkCount": int(fusion.get("blended_landmark_count") or 0),
        "fallbackLandmarkCount": int(fusion.get("fallback_landmark_count") or 0),
        "rejectedTrackCount": int(fusion.get("rejected_track_count") or 0),
        "rejectionReasons": fusion.get("rejection_reasons") or {},
        "coverage": fusion.get("coverage") or {},
        "velocityCapCount": int(tracking.get("velocity_cap_count") or 0),
        "velocityCapCounts": tracking.get("velocity_cap_counts") or {},
        "upperBackAnchorKey": fusion.get("upper_back_anchor_key") or "upper_back",
        "upperBackAnchorSemantics": fusion.get("upper_back_anchor_semantics") or "upper_back_anchor",
        "upperBackAnchorUsedCount": int(fusion.get("upper_back_anchor_used_count") or 0),
        "upperBackAnchorCoverage": float(fusion.get("upper_back_anchor_coverage") or 0.0),
        "pinOwnedLandmarkCount": int(fusion.get("pin_owned_landmark_count") or 0),
        "modelDivergenceAcceptedCount": int(fusion.get("model_divergence_accepted_count") or 0),
        "bodyBarbellOccluderRejectionCount": int(fusion.get("body_barbell_occluder_rejection_count") or 0),
        "bodyPinFrames": fusion.get("body_pin_frames") or [],
        "sourceCounts": fusion.get("source_counts") or {},
        "reference": {
          "version": validated_setup["version"],
          "timeMs": validated_setup["reference_time_ms"],
          "selectedSide": fusion.get("selected_side"),
          "anchors": {
            **{
              name: copy.deepcopy(point)
              for name, point in validated_setup["anchors"].items()
              if name != "upper_back"
            },
            "shoulder": copy.deepcopy(validated_setup["anchors"]["upper_back"]),
          },
        },
      }
    )
  except Exception as error:
    logger.warning("Pin-assisted tracking fell back to automatic analysis for video %s: %s", video.get("id"), error)
    assistance["actualMode"] = "automatic_fallback"
    assistance["fallbackReason"] = "manual_tracking_error"
    assistance["error"] = str(error)
  return assisted_estimation


def _attach_tracking_assistance(result: dict[str, Any], estimation: dict[str, Any]) -> None:
  assistance = dict(estimation.get("tracking_assistance") or {})
  result["trackingAssistance"] = assistance
  result.setdefault("diagnostics", {})["tracking_assistance"] = assistance


def _barbell_pose_frames_with_upper_back_context(
  frames: list[dict[str, Any]],
  *,
  manual_tracking: dict[str, Any],
  selected_side: str | None,
) -> tuple[list[dict[str, Any]], int]:
  if selected_side not in {"left", "right"}:
    return frames, 0

  tracks = manual_tracking.get("tracks") or {}
  upper_back_tracks = tracks.get("upper_back") or tracks.get("shoulder") or {}
  if not upper_back_tracks:
    return frames, 0

  contextual_frames = copy.deepcopy(frames)
  replaced_count = 0
  for frame in contextual_frames:
    source_index = frame.get("source_frame_index")
    if source_index is None:
      continue
    track = upper_back_tracks.get(int(source_index))
    if not track or float(track.get("confidence") or 0.0) < 0.42:
      continue
    landmark = (frame.get("landmarks") or {}).get(f"{selected_side}_shoulder")
    if not landmark:
      continue
    landmark["x"] = float(track["x"])
    landmark["y"] = float(track["y"])
    landmark["visibility"] = max(
      float(landmark.get("visibility") or 0.0),
      min(float(track.get("confidence") or 0.0), 0.92),
    )
    landmark["upper_back_context"] = True
    replaced_count += 1

  return contextual_frames, replaced_count


def _apply_barbell_occlusion_pose_overlay(
  result: dict[str, Any],
  *,
  selected_side: str | None,
  width: int | None,
  height: int | None,
) -> dict[str, Any]:
  if selected_side not in {"left", "right"}:
    return {"corrected_count": 0, "frames": []}
  pose_frames = result.get("poseFrames")
  barbell_points = ((result.get("barbellPath") or {}).get("points") or [])
  if not isinstance(pose_frames, list) or not pose_frames or not barbell_points:
    return {"corrected_count": 0, "frames": []}

  width_px = float(width or result.get("processedVideoWidth") or result.get("videoWidth") or 1)
  height_px = float(height or result.get("processedVideoHeight") or result.get("videoHeight") or 1)
  width_px = max(width_px, 1.0)
  height_px = max(height_px, 1.0)
  max_dimension = max(width_px, height_px)
  tracking_diagnostics = (result.get("diagnostics") or {}).get("barbell_tracking") or {}
  plate_radius_px = tracking_diagnostics.get("plate_radius")
  if not isinstance(plate_radius_px, (int, float)) or float(plate_radius_px) <= 0:
    plate_radius_px = max(28.0, max_dimension * 0.10)
  else:
    plate_radius_px = max(float(plate_radius_px), max_dimension * 0.075)
  margin_px = max(6.0, max_dimension * 0.01)
  sorted_barbell_points = sorted(
    [
      point for point in barbell_points
      if isinstance(point, dict)
      and isinstance(point.get("time"), (int, float))
      and isinstance(point.get("x"), (int, float))
      and isinstance(point.get("y"), (int, float))
      and float(point.get("confidence") or 0.0) >= 0.35
      and point.get("trackingState") != "estimated"
      and point.get("coastingFrame") is not True
      and point.get("stationaryHardwareRejected") is not True
      and point.get("selectedSource") not in {"kinematic_coast", "gap"}
    ],
    key=lambda point: float(point["time"]),
  )
  if not sorted_barbell_points:
    return {"corrected_count": 0, "frames": []}

  keypoint_names = [
    f"{selected_side}_upper_back",
    f"{selected_side}_shoulder",
    f"{selected_side}_hip",
    f"{selected_side}_knee",
  ]

  def nearest_barbell_point(time_seconds: float) -> dict[str, Any] | None:
    nearest = min(
      sorted_barbell_points,
      key=lambda point: abs(float(point["time"]) - time_seconds),
    )
    if abs(float(nearest["time"]) - time_seconds) > 0.25:
      return None
    return nearest

  def keypoint_by_name(frame: dict[str, Any], name: str) -> dict[str, Any] | None:
    keypoints = frame.get("keypoints")
    if not isinstance(keypoints, list):
      return None
    return next(
      (
        keypoint
        for keypoint in keypoints
        if isinstance(keypoint, dict) and keypoint.get("name") == name
      ),
      None,
    )

  occluded: set[tuple[int, str]] = set()
  frame_barbell_points: dict[int, dict[str, Any]] = {}
  for frame_index, frame in enumerate(pose_frames):
    time_seconds = frame.get("time")
    if not isinstance(time_seconds, (int, float)):
      continue
    barbell_point = nearest_barbell_point(float(time_seconds))
    if barbell_point is None:
      continue
    frame_barbell_points[frame_index] = barbell_point
    plate_center_px = (
      float(barbell_point["x"]) * width_px,
      float(barbell_point["y"]) * height_px,
    )
    for name in keypoint_names:
      keypoint = keypoint_by_name(frame, name)
      if not keypoint or not isinstance(keypoint.get("x"), (int, float)) or not isinstance(keypoint.get("y"), (int, float)):
        continue
      if is_body_point_occluded_by_plate(
        (float(keypoint["x"]) * width_px, float(keypoint["y"]) * height_px),
        plate_center_px,
        float(plate_radius_px),
        margin_px,
      ):
        occluded.add((frame_index, name))

  def replacement_point(frame_index: int, name: str) -> dict[str, float] | None:
    previous: tuple[int, dict[str, Any]] | None = None
    following: tuple[int, dict[str, Any]] | None = None
    for offset in range(1, 5):
      candidate_index = frame_index - offset
      if candidate_index < 0:
        break
      if (candidate_index, name) in occluded:
        continue
      keypoint = keypoint_by_name(pose_frames[candidate_index], name)
      if keypoint and float(keypoint.get("confidence") or 0.0) >= 0.24:
        previous = (candidate_index, keypoint)
        break
    for offset in range(1, 5):
      candidate_index = frame_index + offset
      if candidate_index >= len(pose_frames):
        break
      if (candidate_index, name) in occluded:
        continue
      keypoint = keypoint_by_name(pose_frames[candidate_index], name)
      if keypoint and float(keypoint.get("confidence") or 0.0) >= 0.24:
        following = (candidate_index, keypoint)
        break
    if previous and following:
      span = max(following[0] - previous[0], 1)
      progress = (frame_index - previous[0]) / span
      return {
        "x": float(previous[1]["x"]) + ((float(following[1]["x"]) - float(previous[1]["x"])) * progress),
        "y": float(previous[1]["y"]) + ((float(following[1]["y"]) - float(previous[1]["y"])) * progress),
        "confidence": min(float(previous[1].get("confidence") or 0.48), float(following[1].get("confidence") or 0.48), 0.48),
      }
    if previous:
      return {
        "x": float(previous[1]["x"]),
        "y": float(previous[1]["y"]),
        "confidence": min(float(previous[1].get("confidence") or 0.48), 0.36),
      }
    if following:
      return {
        "x": float(following[1]["x"]),
        "y": float(following[1]["y"]),
        "confidence": min(float(following[1].get("confidence") or 0.48), 0.36),
      }
    return None

  corrected_frames: list[dict[str, Any]] = []
  corrected_count = 0
  for frame_index, name in sorted(occluded):
    frame = pose_frames[frame_index]
    keypoint = keypoint_by_name(frame, name)
    if keypoint is None:
      continue
    replacement = replacement_point(frame_index, name)
    if replacement is None:
      keypoint["confidence"] = min(float(keypoint.get("confidence") or 0.0), 0.2)
      keypoint["trackingState"] = "estimated"
      keypoint["acceptedSource"] = "barbell_occlusion_rejected"
      keypoint["chainValid"] = False
      keypoint["visualOnly"] = True
      keypoint["chainFailureReason"] = "barbell_plate_occlusion"
      keypoint["occlusionReason"] = "barbell_plate_occlusion"
    else:
      keypoint["rawModelPoint"] = {
        "x": keypoint["x"],
        "y": keypoint["y"],
        "confidence": keypoint.get("confidence"),
      }
      keypoint["x"] = replacement["x"]
      keypoint["y"] = replacement["y"]
      keypoint["confidence"] = max(min(replacement["confidence"], 0.48), 0.24)
      keypoint["trackingState"] = "estimated"
      keypoint["acceptedSource"] = "barbell_occlusion_estimate"
      keypoint["chainValid"] = True
      keypoint["visualOnly"] = False
      keypoint["occlusionReason"] = "barbell_plate_occlusion"
      keypoint.pop("chainFailureReason", None)
    corrected_count += 1
    if len(corrected_frames) < 120:
      barbell_point = frame_barbell_points.get(frame_index)
      corrected_frames.append({
        "frame_index": frame_index,
        "time": frame.get("time"),
        "keypoint": name,
        "barbell_x": round(float(barbell_point["x"]), 4) if barbell_point else None,
        "barbell_y": round(float(barbell_point["y"]), 4) if barbell_point else None,
        "reason": "barbell_plate_occlusion",
      })

  return {
    "corrected_count": corrected_count,
    "frames": corrected_frames,
    "plate_radius_px": round(float(plate_radius_px), 2),
    "margin_px": round(margin_px, 2),
  }


def build_limited_result(
  *,
  video_id: str,
  exercise_type: str,
  view_type: str,
  reason: str,
  rep_count: int = 0,
  error_code: str | None = None,
) -> dict[str, Any]:
  # Return a lightweight payload when full analysis is not supported.
  result: dict[str, Any] = {
    "video_id": video_id,
    "exercise": exercise_type,
    "view": view_type,
    "analysis_limited": True,
    "rep_count": rep_count,
    "reps": [],
    "summary_flags": [reason],
    "coach_feedback": [
      "Detailed v1 analysis is currently available only for squat videos from the side view."
    ],
    "videoId": video_id,
    "cameraView": view_type,
    "duration": 0,
    "poseFrames": [],
    "summaryFlags": [reason],
    "videoQuality": {
      "overallQuality": 0,
      "poseCoverage": 0,
      "lowerBodyVisibility": 0,
      "sideViewConfidence": 0,
      "squatMotionSignal": 0,
    },
    "coachingFeedback": [
      "Detailed v1 analysis is currently available only for squat videos from the side view."
    ],
  }

  if error_code:
    result["error"] = {
      "code": error_code,
      "message": reason,
    }

  return result


def _annotate_pose_backend(
  result: dict[str, Any],
  estimation: dict[str, Any],
  *,
  fallback_attempted: bool = False,
  fallback_triggered: bool,
  fallback_reason: str | None,
  fallback_recommended: bool | None = None,
  fallback_unavailable_reason: str | None = None,
  fallback_frame_count: int | None = None,
) -> None:
  diagnostics = result.setdefault("diagnostics", {})
  pose_backend = estimation.get("pose_backend")
  recommended = fallback_triggered if fallback_recommended is None else fallback_recommended
  fallback_model = estimation.get("fallback_model") if fallback_triggered else ("rtmpose" if recommended else None)
  resolved_fallback_frame_count = (
    fallback_frame_count
    if fallback_frame_count is not None
    else estimation.get("fallback_frame_count", 0)
  )
  diagnostics["pose_backend"] = pose_backend
  diagnostics["requested_pose_backend"] = estimation.get("requested_pose_backend")
  diagnostics["fallback_model"] = fallback_model
  diagnostics["fallback_frame_count"] = resolved_fallback_frame_count
  diagnostics["fallback_recommended"] = recommended
  diagnostics["fallback_attempted"] = fallback_attempted
  diagnostics["fallback_triggered"] = fallback_triggered
  diagnostics["fallback_reason"] = fallback_reason
  diagnostics["fallback_unavailable_reason"] = fallback_unavailable_reason
  diagnostics["landmark_model"] = estimation.get("landmark_model")
  result["pose_backend"] = pose_backend
  result["fallback_model"] = fallback_model
  result["fallback_frame_count"] = resolved_fallback_frame_count
  result["fallback_recommended"] = recommended
  result["fallback_attempted"] = fallback_attempted
  result["fallback_triggered"] = fallback_triggered
  result["fallback_reason"] = fallback_reason
  result["fallback_unavailable_reason"] = fallback_unavailable_reason
  result["landmark_model"] = estimation.get("landmark_model")


def _fallback_unavailable_reason(fallback_error: Exception) -> str | None:
  message = str(fallback_error).lower()
  if isinstance(fallback_error, ImportError) or "rtmlib" in message or "dependency" in message:
    return "fallback_dependency_missing"
  return None


def _fallback_selection_score(result: dict[str, Any]) -> float:
  diagnostics = result.get("diagnostics") or {}
  quality_score = float(diagnostics.get("quality_score") or 0.0)
  pose_validation = diagnostics.get("pose_validation") or {}
  validation_penalty = float(pose_validation.get("quality_score_penalty") or 0.0)
  depth_counts = diagnostics.get("depth_status_counts") or {}
  reps = result.get("reps") or []
  depth_confidences = [
    float(rep.get("depth_confidence", rep.get("depthConfidence", 0.0)) or 0.0)
    for rep in reps
  ]
  average_depth_confidence = (
    sum(depth_confidences) / len(depth_confidences)
    if depth_confidences
    else 0.0
  )
  uncertain_penalty = 0.08 * int(depth_counts.get("uncertain_depth_count") or 0)
  insufficient_penalty = 0.03 * int(depth_counts.get("insufficient_depth_count") or 0)
  return (
    (quality_score * 0.45)
    + (average_depth_confidence * 0.45)
    + ((1.0 - validation_penalty) * 0.10)
    - uncertain_penalty
    - insufficient_penalty
  )


def _should_select_fallback_result(
  *,
  primary_result: dict[str, Any],
  fallback_result: dict[str, Any],
  fallback_reason: str,
) -> bool:
  primary_score = _fallback_selection_score(primary_result)
  fallback_score = _fallback_selection_score(fallback_result)
  primary_counts = (primary_result.get("diagnostics") or {}).get("depth_status_counts") or {}
  fallback_counts = (fallback_result.get("diagnostics") or {}).get("depth_status_counts") or {}
  primary_rep_count = int(primary_result.get("rep_count") or len(primary_result.get("reps") or []))
  fallback_rep_count = int(fallback_result.get("rep_count") or len(fallback_result.get("reps") or []))

  if primary_rep_count > 0 and fallback_rep_count <= 0:
    return False

  if int(fallback_counts.get("hit_depth_count") or 0) > int(primary_counts.get("hit_depth_count") or 0):
    return True
  if fallback_score >= primary_score + 0.03:
    return True
  if fallback_reason in {
    "plate_rack_occlusion_suspected",
    "excessive_landmark_jitter",
    "pose_validation_rejections",
    "uncertain_depth",
    "bottom_depth_landmarks_unreliable",
    "low_bottom_depth_confidence",
  }:
    return fallback_score >= primary_score - 0.05
  return False


def _rep_depth_delta_px(rep: dict[str, Any]) -> float | None:
  evidence = rep.get("depth_evidence") or {}
  components = rep.get("depth_components") or {}
  value = evidence.get("depth_delta_px", evidence.get("depthDeltaPx", components.get("depth_delta_px")))
  return float(value) if value is not None else None


def _rep_depth_tolerance_px(rep: dict[str, Any]) -> float:
  evidence = rep.get("depth_evidence") or {}
  components = rep.get("depth_components") or {}
  value = evidence.get(
    "depth_tolerance_px",
    evidence.get("depthTolerancePx", components.get("depth_tolerance_px")),
  )
  return float(value) if value is not None else 8.0


def _depth_models_disagree(primary_rep: dict[str, Any], fallback_rep: dict[str, Any]) -> bool:
  primary_status = primary_rep.get("depth_status") or primary_rep.get("depthStatus")
  fallback_status = fallback_rep.get("depth_status") or fallback_rep.get("depthStatus")
  if {primary_status, fallback_status} == {"hit_depth", "insufficient_depth"}:
    return True

  primary_delta = _rep_depth_delta_px(primary_rep)
  fallback_delta = _rep_depth_delta_px(fallback_rep)
  if primary_delta is None or fallback_delta is None:
    return False

  tolerance = max(_rep_depth_tolerance_px(primary_rep), _rep_depth_tolerance_px(fallback_rep), 1.0)
  crosses_depth_line = (primary_delta >= 0 > fallback_delta) or (fallback_delta >= 0 > primary_delta)
  return crosses_depth_line and abs(primary_delta - fallback_delta) > tolerance * 1.5


def _refresh_depth_status_counts(result: dict[str, Any]) -> None:
  reps = result.get("reps") or []
  diagnostics = result.setdefault("diagnostics", {})
  diagnostics["depth_status_counts"] = {
    "hit_depth_count": sum(1 for rep in reps if rep.get("depth_status") == "hit_depth"),
    "insufficient_depth_count": sum(
      1 for rep in reps if rep.get("depth_status") == "insufficient_depth"
    ),
    "uncertain_depth_count": sum(1 for rep in reps if rep.get("depth_status") == "uncertain_depth"),
  }


def _downgrade_depth_for_model_disagreement(
  *,
  selected_result: dict[str, Any],
  alternate_result: dict[str, Any],
) -> None:
  selected_reps = selected_result.get("reps") or []
  alternate_reps = alternate_result.get("reps") or []
  changed = False

  for index, (selected_rep, alternate_rep) in enumerate(zip(selected_reps, alternate_reps), start=1):
    if not _depth_models_disagree(selected_rep, alternate_rep):
      continue

    changed = True
    flags = [flag for flag in selected_rep.get("flags", []) if flag != "insufficient_depth"]
    if "low_depth_confidence" not in flags:
      flags.append("low_depth_confidence")
    selected_rep["flags"] = flags
    selected_rep["depth_status"] = "uncertain_depth"
    selected_rep["depthStatus"] = "uncertain_depth"
    selected_rep["depth_reason"] = "model_disagreement"
    selected_rep["depthReason"] = "model_disagreement"

    for container_name in ("depth_evidence", "depth_components"):
      container = selected_rep.get(container_name)
      if not isinstance(container, dict):
        continue
      container["depth_status"] = "uncertain_depth"
      container["depthStatus"] = "uncertain_depth"
      container["depth_classification"] = "uncertain_depth"
      container["depthClassification"] = "uncertain_depth"
      container["depth_reason"] = "model_disagreement"
      container["depthReason"] = "model_disagreement"

    diagnostics = selected_result.setdefault("diagnostics", {})
    diagnostics.setdefault("model_disagreement_reps", []).append(index)

  if not changed:
    return

  diagnostics = selected_result.setdefault("diagnostics", {})
  diagnostics["pose_model_disagreement"] = True
  if "quality_flags" in diagnostics and "pose_model_disagreement" not in diagnostics["quality_flags"]:
    diagnostics["quality_flags"].append("pose_model_disagreement")
  _refresh_depth_status_counts(selected_result)
  diagnostics["depth_summary_debug"] = build_depth_summary_debug(selected_reps)
  if diagnostics.get("depth_debug"):
    for debug_entry, rep in zip(diagnostics["depth_debug"], selected_reps):
      debug_entry["depth_status"] = rep.get("depth_status")
      debug_entry["depthClassification"] = rep.get("depth_status")
      debug_entry["depthReason"] = rep.get("depth_reason")
      debug_entry["depth_reason"] = rep.get("depth_reason")
  summary_flags, coach_feedback = build_feedback(selected_reps, diagnostics)
  selected_result["summary_flags"] = summary_flags
  selected_result["summaryFlags"] = summary_flags
  selected_result["coach_feedback"] = coach_feedback
  selected_result["coachingFeedback"] = coach_feedback


def _analyze_squat_result(
  *,
  video_id: str,
  video: dict[str, Any],
  estimation: dict[str, Any],
) -> dict[str, Any]:
  if not _is_squat_variation(video["exercise_type"]) or video["view_type"] != "side":
    return build_limited_result(
      video_id=video_id,
      exercise_type=video["exercise_type"],
      view_type=video["view_type"],
      reason="Limited analysis: full support is available only for squat side view in v1.",
    )

  if not estimation["frames"]:
    result = build_limited_result(
      video_id=video_id,
      exercise_type=video["exercise_type"],
      view_type=video["view_type"],
      reason="No pose detected. Make sure your full body is visible from the side.",
      error_code="no_pose_detected",
    )
    result["diagnostics"] = {
      "quality_score": 0.0,
      "pose_coverage": 0.0,
      "sampled_frame_count": estimation.get("sampled_frame_count", 0),
      "quality_flags": ["low_pose_coverage"],
    }
    return result

  analyzer = SquatAnalyzer()
  assistance = estimation.get("tracking_assistance") or {}
  selected_side_override = (
    assistance.get("selectedSide")
    if assistance.get("actualMode") == "pin_assisted"
    else None
  )
  return analyzer.analyze(
    video_id=video_id,
    exercise_type=video["exercise_type"],
    view_type=video["view_type"],
    frames=estimation["frames"],
    sampled_frame_count=estimation.get("sampled_frame_count"),
    selected_side_override=selected_side_override,
  )

def _finalize_storage_assets(
  *,
  video: dict[str, Any],
  video_id: str,
  source_path: Path,
  repository: VideoRepository,
  storage: StorageService,
) -> None:
  user_id = str(video.get("user_id") or "")
  if not user_id:
    logger.warning("Skipping storage asset finalization for video %s because user_id is missing.", video_id)
    return

  thumbnail_temp: Path | None = None
  compressed_temp: Path | None = None
  thumbnail_path: str | None = None
  original_path = str(video["storage_path"])

  try:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_thumbnail:
      thumbnail_temp = Path(temp_thumbnail.name)

    thumbnail_path = build_thumbnail_storage_path(user_id, video_id)
    create_video_thumbnail(source_path, thumbnail_temp)
    storage.upload_file(
      thumbnail_path,
      thumbnail_temp,
      "image/jpeg",
      cache_control=IMMUTABLE_CACHE_CONTROL_SECONDS,
    )
    try:
      repository.update_video(video_id, {"thumbnail_path": thumbnail_path})
    except Exception:
      logger.exception(
        "Failed to save thumbnail metadata for video %s; deleting uploaded thumbnail %s.",
        video_id,
        thumbnail_path,
      )
      storage.delete_storage_path(thumbnail_path)
      raise
    logger.info(
      "Uploaded thumbnail for video %s to %s size_bytes=%s.",
      video_id,
      thumbnail_path,
      thumbnail_temp.stat().st_size,
    )
  except Exception as error:
    logger.warning("Unable to create thumbnail for video %s: %s", video_id, error)
    return
  finally:
    if thumbnail_temp:
      storage.remove_tempfile(thumbnail_temp)

  try:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_compressed:
      compressed_temp = Path(temp_compressed.name)

    playback_path = build_playback_storage_path(user_id, video_id)
    compress_video_for_playback(source_path, compressed_temp)
    storage.upload_file(
      playback_path,
      compressed_temp,
      "video/mp4",
      cache_control=IMMUTABLE_CACHE_CONTROL_SECONDS,
    )
    try:
      repository.update_video(
        video_id,
        {
          "playback_path": playback_path,
          "original_storage_path": original_path,
          "storage_optimized_at": datetime.now(timezone.utc).isoformat(),
          "storage_optimization_error": None,
        },
      )
    except Exception:
      logger.exception(
        "Failed to save playback metadata for video %s; deleting uploaded playback %s.",
        video_id,
        playback_path,
      )
      storage.delete_storage_path(playback_path)
      raise

    if original_path != playback_path:
      try:
        storage.delete_storage_path(original_path)
        logger.info("Deleted original uploaded video for %s at %s.", video_id, original_path)
      except Exception as error:
        logger.warning("Unable to delete original uploaded video for %s at %s: %s", video_id, original_path, error)

    logger.info(
      "Uploaded compressed playback video for %s to %s size_bytes=%s.",
      video_id,
      playback_path,
      compressed_temp.stat().st_size,
    )
  except Exception as error:
    logger.warning("Unable to create compressed playback video for %s: %s", video_id, error)
  finally:
    if compressed_temp:
      storage.remove_tempfile(compressed_temp)


def _attach_barbell_tracking(
  *,
  result: dict[str, Any],
  video: dict[str, Any],
  file_path: str,
  estimation: dict[str, Any],
) -> None:
  if not _is_squat_variation(video["exercise_type"]) or video["view_type"] != "side":
    return

  diagnostics = result.setdefault("diagnostics", {})
  selected_side = (
    (result.get("trackingAssistance") or {}).get("selectedSide")
    or (diagnostics.get("tracking_assistance") or {}).get("selectedSide")
    or (diagnostics.get("pose_validation") or {}).get("selected_side")
    or diagnostics.get("selected_side")
  )
  rep_windows = [
    {
      "rep_index": int(rep.get("rep_index", index)),
      "start": float(rep["startTime"]),
      "bottom": float(rep.get("bottomTimestampMs", rep.get("bottom_timestamp_ms", 0))) / 1000,
      "end": float(rep["endTime"]),
    }
    for index, rep in enumerate(result.get("reps") or [], start=1)
    if rep.get("startTime") is not None
    and rep.get("endTime") is not None
    and (rep.get("bottomTimestampMs") is not None or rep.get("bottom_timestamp_ms") is not None)
  ]
  try:
    tracker = BarbellTracker()
    pose_context_frames = estimation.get("frames") or []
    pose_context_validation: dict[str, Any] = {}
    pose_context_validated = False
    if pose_context_frames:
      try:
        pose_context_frames, pose_context_validation = validate_squat_pose_frames(
          pose_context_frames,
          selected_side_override=selected_side,
        )
        pose_context_validated = True
      except Exception as validation_error:
        pose_context_frames = estimation.get("frames") or []
        pose_context_validation = {"error": str(validation_error), "failed_open": True}
    barbell_pose_frames, upper_back_context_count = _barbell_pose_frames_with_upper_back_context(
      pose_context_frames,
      manual_tracking=estimation.get("manual_tracking") or {},
      selected_side=selected_side,
    )
    tracking = tracker.track(
      file_path,
      pose_frames=barbell_pose_frames,
      frame_step=int(estimation.get("frame_step") or 1),
      processed_width=estimation.get("processed_frame_width") or estimation.get("frame_width"),
      processed_height=estimation.get("processed_frame_height") or estimation.get("frame_height"),
      selected_side=selected_side,
      rep_windows=rep_windows,
      manual_barbell_priors=barbell_track_priors(estimation.get("manual_tracking") or {}),
    )
    manual_seed_count = tracker.manual_seed_count if isinstance(tracker.manual_seed_count, int) else 0
    tracking_diagnostics = tracking.get("diagnostics") or {}
    manual_point_count = int(
      tracking_diagnostics.get("manual_point_count")
      or getattr(tracker, "manual_point_count", 0)
      or 0
    )
    automatic_point_count = int(
      tracking_diagnostics.get("automatic_point_count")
      or getattr(tracker, "automatic_point_count", 0)
      or 0
    )
    manual_barbell_used = bool(
      manual_point_count > 0
      and (tracking.get("barbellPath") or {}).get("available")
    )
    assistance = result.get("trackingAssistance") or {}
    assistance["barbellSeedUsed"] = manual_barbell_used
    assistance["manualBarbellPointCount"] = manual_point_count
    assistance["automaticBarbellPointCount"] = automatic_point_count
    lane_fusion = tracking_diagnostics.get("barbell_lane_fusion") or {}
    lane_source_counts = lane_fusion.get("source_counts") or {}
    if isinstance(lane_source_counts, dict) and lane_source_counts:
      assistance["barbellSourceCounts"] = dict(lane_source_counts)
      assistance["barbellCoastingPointCount"] = int(lane_source_counts.get("kinematic_coast") or 0)
      assistance["barbellGapPointCount"] = int(lane_source_counts.get("gap") or 0)
    if manual_barbell_used:
      assistance["used"] = True
      assistance["actualMode"] = "pin_assisted"
      assistance["fallbackReason"] = None
    result["trackingAssistance"] = assistance
    diagnostics["tracking_assistance"] = assistance
    result["barbellPath"] = tracking["barbellPath"]
    tracking_diagnostics["manual_seed_count"] = manual_seed_count
    tracking_diagnostics["manual_point_count"] = manual_point_count
    tracking_diagnostics["automatic_point_count"] = automatic_point_count
    tracking_diagnostics["upper_back_context_frame_count"] = upper_back_context_count
    tracking_diagnostics["pose_context_validated"] = pose_context_validated
    tracking_diagnostics["pose_context_validation"] = pose_context_validation
    diagnostics["barbell_tracking"] = tracking_diagnostics
    pose_overlay_occlusion = _apply_barbell_occlusion_pose_overlay(
      result,
      selected_side=selected_side,
      width=estimation.get("processed_frame_width") or estimation.get("frame_width"),
      height=estimation.get("processed_frame_height") or estimation.get("frame_height"),
    )
    if pose_overlay_occlusion.get("corrected_count"):
      diagnostics["barbell_pose_occlusion_overlay"] = pose_overlay_occlusion
  except Exception as error:
    logger.warning("Barbell tracking failed for video %s: %s", video.get("id"), error)
    result["barbellPath"] = {
      "available": False,
      "target": "near_plate_collar_center",
      "source": "opencv_circle_tracker",
      "coverage": 0.0,
      "points": [],
    }
    diagnostics["barbell_tracking"] = {
      "available": False,
      "target": "near_plate_collar_center",
      "source": "opencv_circle_tracker",
      "coverage": 0.0,
      "failure_reason": "tracker_error",
      "error": str(error),
    }


def analyze_video(video_id: str) -> None:
  # The pipeline loads the video, estimates pose, then stores results.
  analysis_started = time.perf_counter()
  repository = VideoRepository()
  storage = StorageService()
  settings = get_settings()

  video = repository.get_video(video_id)
  if not video:
    raise RuntimeError(f"Video {video_id} was not found.")

  temp_file = None

  try:
    repository.update_video(video_id, {"status": "processing"})
    # Download the clip into a temporary file for local processing.
    stage_started = time.perf_counter()
    source_storage_path = video.get("playback_path") or video["storage_path"]
    temp_file = storage.download_to_tempfile(source_storage_path)
    logger.info(
      "Downloaded video %s from %s in %sms.",
      video_id,
      source_storage_path,
      int((time.perf_counter() - stage_started) * 1000),
    )

    # Pose estimation is the first stage of the backend analysis flow.
    estimator = PoseEstimator()
    stage_started = time.perf_counter()
    estimation = _apply_tracking_assistance(
      file_path=str(temp_file),
      video=video,
      estimation=estimator.run(str(temp_file)),
    )
    logger.info(
      "Estimated pose for video %s in %sms.",
      video_id,
      int((time.perf_counter() - stage_started) * 1000),
    )
    repository.update_video(
      video_id,
      {
        "fps": estimation["fps"],
        "duration_ms": estimation["duration_ms"],
      },
    )

    stage_started = time.perf_counter()
    result = _analyze_squat_result(video_id=video_id, video=video, estimation=estimation)
    _attach_tracking_assistance(result, estimation)
    _annotate_pose_backend(
      result,
      estimation,
      fallback_attempted=False,
      fallback_triggered=False,
      fallback_reason=None,
    )
    logger.info(
      "Analyzed squat metrics for video %s in %sms.",
      video_id,
      int((time.perf_counter() - stage_started) * 1000),
    )

    fallback_reason = (
      analysis_needs_pose_fallback(result)
      if estimation.get("pose_backend") == "mediapipe" and estimator.config.pose_backend == "hybrid"
      else None
    )
    fallback_recommended = fallback_reason is not None
    fallback_unavailable_reason = (
      "fallback_disabled" if fallback_recommended and not estimator.config.pose_fallback_enabled else None
    )
    _annotate_pose_backend(
      result,
      estimation,
      fallback_attempted=False,
      fallback_triggered=False,
      fallback_reason=fallback_reason,
      fallback_recommended=fallback_recommended,
      fallback_unavailable_reason=fallback_unavailable_reason,
    )

    if fallback_recommended and estimator.config.pose_fallback_enabled:
      stage_started = time.perf_counter()
      fallback_config = replace(estimator.config, pose_backend="rtmpose")
      fallback_attempted = True
      try:
        fallback_estimation = _apply_tracking_assistance(
          file_path=str(temp_file),
          video=video,
          estimation=PoseEstimator(config=fallback_config).run(str(temp_file)),
        )
        if fallback_estimation["frames"]:
          fallback_result = _analyze_squat_result(
            video_id=video_id,
            video=video,
            estimation=fallback_estimation,
          )
          _attach_tracking_assistance(fallback_result, fallback_estimation)
          fallback_selected = _should_select_fallback_result(
            primary_result=result,
            fallback_result=fallback_result,
            fallback_reason=fallback_reason,
          )
          if fallback_selected:
            _annotate_pose_backend(
              fallback_result,
              fallback_estimation,
              fallback_attempted=fallback_attempted,
              fallback_triggered=True,
              fallback_reason=fallback_reason,
              fallback_recommended=True,
              fallback_unavailable_reason=None,
            )
            _downgrade_depth_for_model_disagreement(
              selected_result=fallback_result,
              alternate_result=result,
            )
            result = fallback_result
            estimation = fallback_estimation
          else:
            diagnostics = result.setdefault("diagnostics", {})
            diagnostics["fallback_candidate_quality_score"] = round(
              _fallback_selection_score(fallback_result),
              3,
            )
            diagnostics["primary_quality_score"] = round(
              _fallback_selection_score(result),
              3,
            )
            diagnostics["fallback_selection"] = "primary_retained"
            _annotate_pose_backend(
              result,
              estimation,
              fallback_attempted=fallback_attempted,
              fallback_triggered=False,
              fallback_reason=fallback_reason,
              fallback_recommended=True,
              fallback_unavailable_reason=None,
              fallback_frame_count=fallback_estimation.get("fallback_frame_count", 0),
            )
            _downgrade_depth_for_model_disagreement(
              selected_result=result,
              alternate_result=fallback_result,
            )
        else:
          _annotate_pose_backend(
            result,
            estimation,
            fallback_attempted=fallback_attempted,
            fallback_triggered=False,
            fallback_reason=fallback_reason,
            fallback_recommended=True,
            fallback_unavailable_reason="fallback_no_pose_detected",
          )
      except Exception as fallback_error:
        fallback_unavailable_reason = _fallback_unavailable_reason(fallback_error)
        logger.warning(
          "RTMPose fallback failed for video %s after %s: %s",
          video_id,
          fallback_reason,
          fallback_error,
        )
        diagnostics = result.setdefault("diagnostics", {})
        diagnostics["fallback_error"] = str(fallback_error)
        diagnostics["fallback_attempted"] = fallback_attempted
        diagnostics["fallback_unavailable_reason"] = fallback_unavailable_reason
        result["fallback_error"] = str(fallback_error)
        result["fallback_attempted"] = fallback_attempted
        result["fallback_unavailable_reason"] = fallback_unavailable_reason
      logger.info(
        "Handled RTMPose fallback for video %s in %sms.",
        video_id,
        int((time.perf_counter() - stage_started) * 1000),
      )

    result["duration"] = (estimation["duration_ms"] or 0) / 1000
    result["videoWidth"] = estimation.get("frame_width")
    result["videoHeight"] = estimation.get("frame_height")
    stage_started = time.perf_counter()
    _attach_barbell_tracking(
      result=result,
      video=video,
      file_path=str(temp_file),
      estimation=estimation,
    )
    logger.info(
      "Tracked barbell path for video %s in %sms.",
      video_id,
      int((time.perf_counter() - stage_started) * 1000),
    )
    video_metadata = {
      "fps": estimation.get("fps"),
      "duration_ms": estimation.get("duration_ms"),
      "frame_count": estimation.get("frame_count"),
      "original_width": estimation.get("original_frame_width") or estimation.get("frame_width"),
      "original_height": estimation.get("original_frame_height") or estimation.get("frame_height"),
      "processed_width": estimation.get("processed_frame_width"),
      "processed_height": estimation.get("processed_frame_height"),
      "sampled_frame_count": estimation.get("sampled_frame_count"),
      "pose_frame_count": estimation.get("pose_frame_count"),
      "target_fps": estimation.get("target_fps"),
      "frame_step": estimation.get("frame_step"),
      "pose_model_complexity": estimation.get("pose_model_complexity"),
      "pose_backend": estimation.get("pose_backend"),
      "requested_pose_backend": estimation.get("requested_pose_backend"),
      "fallback_model": result.get("fallback_model"),
      "fallback_frame_count": result.get("fallback_frame_count", 0),
      "fallback_recommended": result.get("fallback_recommended", False),
      "fallback_triggered": result.get("fallback_triggered", False),
      "fallback_reason": result.get("fallback_reason"),
      "fallback_unavailable_reason": result.get("fallback_unavailable_reason"),
      "landmark_model": estimation.get("landmark_model"),
      "pose_processing_duration_ms": estimation.get("processing_duration_ms"),
    }
    result["video_metadata"] = video_metadata
    result["videoMetadata"] = video_metadata
    result["processedVideoWidth"] = estimation.get("processed_frame_width")
    result["processedVideoHeight"] = estimation.get("processed_frame_height")
    result["sampledFrameCount"] = estimation.get("sampled_frame_count")
    result["poseFrameCount"] = estimation.get("pose_frame_count")
    result["model_version"] = settings.model_version
    result["analysis_model_version"] = settings.model_version
    diagnostics = result.setdefault("diagnostics", {})
    diagnostics["analysis_model_version"] = settings.model_version
    stage_started = time.perf_counter()
    repository.save_analysis_result(video_id, settings.model_version, result)
    logger.info(
      "Saved analysis for video %s in %sms.",
      video_id,
      int((time.perf_counter() - stage_started) * 1000),
    )
    stage_started = time.perf_counter()
    _finalize_storage_assets(
      video=video,
      video_id=video_id,
      source_path=temp_file,
      repository=repository,
      storage=storage,
    )
    logger.info(
      "Finalized storage assets for video %s in %sms.",
      video_id,
      int((time.perf_counter() - stage_started) * 1000),
    )
    repository.update_video(video_id, {"status": "completed"})
    logger.info(
      "Completed analysis for video %s in %sms.",
      video_id,
      int((time.perf_counter() - analysis_started) * 1000),
    )
  except Exception as error:
    repository.update_video(video_id, {"status": "failed"})
    raise RuntimeError(
      f"Video analysis failed for {video_id}: {error}\n{traceback.format_exc()}"
    ) from error
  finally:
    if temp_file:
      storage.remove_tempfile(temp_file)
