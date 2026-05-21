from __future__ import annotations

import logging
import time
import traceback
from dataclasses import replace
from typing import Any

from .feedback_engine import build_depth_summary_debug, build_feedback
from .exercises.squat import SquatAnalyzer
from .pose_fallback import analysis_needs_pose_fallback
from .pose_estimator import PoseEstimator
from ..services.config import get_settings
from ..services.storage_service import StorageService
from ..services.video_repository import VideoRepository


logger = logging.getLogger(__name__)


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
  if video["exercise_type"] != "squat" or video["view_type"] != "side":
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
  return analyzer.analyze(
    video_id=video_id,
    exercise_type=video["exercise_type"],
    view_type=video["view_type"],
    frames=estimation["frames"],
    sampled_frame_count=estimation.get("sampled_frame_count"),
  )


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
    temp_file = storage.download_to_tempfile(video["storage_path"])
    logger.info(
      "Downloaded video %s in %sms.",
      video_id,
      int((time.perf_counter() - stage_started) * 1000),
    )

    # Pose estimation is the first stage of the backend analysis flow.
    estimator = PoseEstimator()
    stage_started = time.perf_counter()
    estimation = estimator.run(str(temp_file))
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
        fallback_estimation = PoseEstimator(config=fallback_config).run(str(temp_file))
        if fallback_estimation["frames"]:
          fallback_result = _analyze_squat_result(
            video_id=video_id,
            video=video,
            estimation=fallback_estimation,
          )
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
