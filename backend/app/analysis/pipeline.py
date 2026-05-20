from __future__ import annotations

import logging
import time
import traceback
from dataclasses import replace
from typing import Any

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
  fallback_triggered: bool,
  fallback_reason: str | None,
  fallback_recommended: bool | None = None,
  fallback_unavailable_reason: str | None = None,
) -> None:
  diagnostics = result.setdefault("diagnostics", {})
  pose_backend = estimation.get("pose_backend")
  recommended = fallback_triggered if fallback_recommended is None else fallback_recommended
  fallback_model = estimation.get("fallback_model") if fallback_triggered else ("rtmpose" if recommended else None)
  diagnostics["pose_backend"] = pose_backend
  diagnostics["requested_pose_backend"] = estimation.get("requested_pose_backend")
  diagnostics["fallback_model"] = fallback_model
  diagnostics["fallback_frame_count"] = estimation.get("fallback_frame_count", 0)
  diagnostics["fallback_recommended"] = recommended
  diagnostics["fallback_triggered"] = fallback_triggered
  diagnostics["fallback_reason"] = fallback_reason
  diagnostics["fallback_unavailable_reason"] = fallback_unavailable_reason
  diagnostics["landmark_model"] = estimation.get("landmark_model")
  result["pose_backend"] = pose_backend
  result["fallback_model"] = fallback_model
  result["fallback_frame_count"] = estimation.get("fallback_frame_count", 0)
  result["fallback_recommended"] = recommended
  result["fallback_triggered"] = fallback_triggered
  result["fallback_reason"] = fallback_reason
  result["fallback_unavailable_reason"] = fallback_unavailable_reason
  result["landmark_model"] = estimation.get("landmark_model")


def _fallback_unavailable_reason(fallback_error: Exception) -> str | None:
  message = str(fallback_error).lower()
  if isinstance(fallback_error, ImportError) or "rtmlib" in message or "dependency" in message:
    return "fallback_dependency_missing"
  return None


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
      fallback_triggered=False,
      fallback_reason=fallback_reason,
      fallback_recommended=fallback_recommended,
      fallback_unavailable_reason=fallback_unavailable_reason,
    )

    if fallback_recommended and estimator.config.pose_fallback_enabled:
      stage_started = time.perf_counter()
      fallback_config = replace(estimator.config, pose_backend="rtmpose")
      try:
        fallback_estimation = PoseEstimator(config=fallback_config).run(str(temp_file))
        if fallback_estimation["frames"]:
          fallback_result = _analyze_squat_result(
            video_id=video_id,
            video=video,
            estimation=fallback_estimation,
          )
          _annotate_pose_backend(
            fallback_result,
            fallback_estimation,
            fallback_triggered=True,
            fallback_reason=fallback_reason,
            fallback_recommended=True,
            fallback_unavailable_reason=None,
          )
          result = fallback_result
          estimation = fallback_estimation
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
        diagnostics["fallback_unavailable_reason"] = fallback_unavailable_reason
        result["fallback_error"] = str(fallback_error)
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
