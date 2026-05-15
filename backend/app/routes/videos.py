from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from ..analysis.pipeline import analyze_video
from ..services.auth import get_current_user_id
from ..services.storage_service import StorageService
from ..services.video_repository import VideoRepository


logger = logging.getLogger(__name__)
router = APIRouter()
QUEUEABLE_ANALYSIS_STATUSES = ("uploaded", "failed")
IDEMPOTENT_ANALYSIS_STATUSES = {"queued", "processing", "completed"}


class AnalyzeResponse(BaseModel):
  video_id: UUID
  status: str


class VideoStatusResponse(BaseModel):
  video_id: UUID
  status: str
  exercise_type: str
  view_type: str
  updated_at: str


class AnalysisResponse(BaseModel):
  video_id: UUID
  status: str
  result_json: dict


class SaveVideoResponse(BaseModel):
  video_id: UUID
  save_state: str


class DiscardVideoResponse(BaseModel):
  video_id: UUID
  discarded: bool


class CleanupExpiredVideosResponse(BaseModel):
  deleted_count: int


def _run_analysis_job(video_id: str) -> None:
  # Background tasks run analysis outside the request lifecycle.
  try:
    analyze_video(video_id)
  except Exception:
    logger.exception("Background analysis failed for video %s", video_id)


@router.post("/analyze/{video_id}", response_model=AnalyzeResponse)
def queue_analysis(
  video_id: UUID,
  background_tasks: BackgroundTasks,
  user_id: str = Depends(get_current_user_id),
) -> AnalyzeResponse:
  # Queue analysis only when the video belongs to the current user.
  repository = VideoRepository()
  video_id_str = str(video_id)
  video = repository.require_owned_video(video_id_str, user_id)
  current_status = video["status"]

  if current_status in IDEMPOTENT_ANALYSIS_STATUSES:
    return AnalyzeResponse(video_id=video_id, status=current_status)

  if current_status not in QUEUEABLE_ANALYSIS_STATUSES:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=f"Video cannot be queued for analysis from status '{current_status}'.",
    )

  StorageService().validate_video_object(video["storage_path"])
  queued_video = repository.queue_owned_video_if_status(
    video_id_str,
    user_id,
    QUEUEABLE_ANALYSIS_STATUSES,
  )

  if queued_video:
    background_tasks.add_task(_run_analysis_job, video_id_str)
    return AnalyzeResponse(video_id=video_id, status=queued_video["status"])

  latest_video = repository.require_owned_video(video_id_str, user_id)
  latest_status = latest_video["status"]

  if latest_status in IDEMPOTENT_ANALYSIS_STATUSES:
    return AnalyzeResponse(video_id=video_id, status=latest_status)

  raise HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail=f"Video could not be queued because its status is now '{latest_status}'.",
  )


@router.post("/videos/{video_id}/save", response_model=SaveVideoResponse)
def save_video(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> SaveVideoResponse:
  # Mark a finished analysis as saved in the user's library.
  repository = VideoRepository()
  repository.require_owned_video(str(video_id), user_id)
  saved_video = repository.mark_saved(str(video_id))
  return SaveVideoResponse(video_id=video_id, save_state=saved_video["save_state"])


@router.post("/videos/{video_id}/discard", response_model=DiscardVideoResponse)
def discard_video(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> DiscardVideoResponse:
  # Discard removes both the storage object and the DB row.
  repository = VideoRepository()
  video = repository.require_owned_video(str(video_id), user_id)
  StorageService().delete_storage_path(video["storage_path"])
  if video.get("thumbnail_path"):
    StorageService().delete_storage_path(video["thumbnail_path"])
  repository.delete_video_with_analysis(str(video_id))
  return DiscardVideoResponse(video_id=video_id, discarded=True)


@router.post("/videos/cleanup-expired", response_model=CleanupExpiredVideosResponse)
def cleanup_expired_videos() -> CleanupExpiredVideosResponse:
  repository = VideoRepository()
  storage = StorageService()
  expired_videos = repository.list_expired_pending_videos()
  deleted_count = 0

  for video in expired_videos:
    storage.delete_storage_path(video["storage_path"])
    if video.get("thumbnail_path"):
      storage.delete_storage_path(video["thumbnail_path"])
    repository.delete_video_with_analysis(video["id"])
    deleted_count += 1

  logger.info(
    "Cleaned up %s expired pending videos at %s",
    deleted_count,
    datetime.now(timezone.utc).isoformat(),
  )
  return CleanupExpiredVideosResponse(deleted_count=deleted_count)


@router.get("/videos/{video_id}/status", response_model=VideoStatusResponse)
def get_video_status(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> VideoStatusResponse:
  # Status polling lets the client show upload progress.
  repository = VideoRepository()
  video = repository.require_owned_video(str(video_id), user_id)
  return VideoStatusResponse(
    video_id=video_id,
    status=video["status"],
    exercise_type=video["exercise_type"],
    view_type=video["view_type"],
    updated_at=video["updated_at"],
  )


@router.get("/analysis/{video_id}", response_model=AnalysisResponse)
def get_analysis(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> AnalysisResponse:
  # Return the latest completed analysis payload for review.
  repository = VideoRepository()
  video = repository.require_owned_video(str(video_id), user_id)
  result = repository.get_analysis_result(str(video_id))

  if not result:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail="Analysis result not available yet.",
    )

  return AnalysisResponse(
    video_id=video_id,
    status=video["status"],
    result_json=result["result_json"],
  )
