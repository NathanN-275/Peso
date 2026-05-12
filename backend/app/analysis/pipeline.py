from __future__ import annotations

import traceback
from typing import Any

from .exercises.squat import SquatAnalyzer
from .pose_estimator import PoseEstimator
from ..services.config import get_settings
from ..services.storage_service import StorageService
from ..services.video_repository import VideoRepository


def build_limited_result(
  *,
  video_id: str,
  exercise_type: str,
  view_type: str,
  reason: str,
  rep_count: int = 0,
  error_code: str | None = None,
) -> dict[str, Any]:
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


def analyze_video(video_id: str) -> None:
  repository = VideoRepository()
  storage = StorageService()
  settings = get_settings()

  video = repository.get_video(video_id)
  if not video:
    raise RuntimeError(f"Video {video_id} was not found.")

  temp_file = None

  try:
    repository.update_video(video_id, {"status": "processing"})
    temp_file = storage.download_to_tempfile(video["storage_path"])

    estimator = PoseEstimator()
    estimation = estimator.run(str(temp_file))
    repository.update_video(
      video_id,
      {
        "fps": estimation["fps"],
        "duration_ms": estimation["duration_ms"],
      },
    )

    if video["exercise_type"] != "squat" or video["view_type"] != "side":
      result = build_limited_result(
        video_id=video_id,
        exercise_type=video["exercise_type"],
        view_type=video["view_type"],
        reason="Limited analysis: full support is available only for squat side view in v1.",
      )
    elif not estimation["frames"]:
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
    else:
      analyzer = SquatAnalyzer()
      result = analyzer.analyze(
        video_id=video_id,
        exercise_type=video["exercise_type"],
        view_type=video["view_type"],
        frames=estimation["frames"],
        sampled_frame_count=estimation.get("sampled_frame_count"),
      )

    result["duration"] = (estimation["duration_ms"] or 0) / 1000
    result["videoWidth"] = estimation.get("frame_width")
    result["videoHeight"] = estimation.get("frame_height")
    result["model_version"] = settings.model_version
    repository.save_analysis_result(video_id, settings.model_version, result)
    repository.update_video(video_id, {"status": "completed"})
  except Exception as error:
    repository.update_video(video_id, {"status": "failed"})
    raise RuntimeError(
      f"Video analysis failed for {video_id}: {error}\n{traceback.format_exc()}"
    ) from error
  finally:
    if temp_file:
      storage.remove_tempfile(temp_file)
