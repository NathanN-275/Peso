from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..analysis.pipeline import analyze_video
from ..analysis.versioning import annotate_analysis_freshness, analysis_is_current
from ..services.analyzed_video_renderer import render_analyzed_video
from ..services.auth import get_current_user_id
from ..services.config import get_settings
from ..services.storage_service import StorageService, object_size_bytes, object_updated_at
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


class SavedVideoAnalysisResponse(BaseModel):
  id: UUID
  model_version: str
  created_at: str
  result_json: dict
  summary: list[str]
  coaching_feedback: list[str]
  rep_data: list[dict]


class SavedVideoResponse(BaseModel):
  id: UUID
  exercise_type: str
  view_type: str
  storage_path: str
  thumbnail_path: str | None = None
  video_url: str | None = None
  thumbnail_url: str | None = None
  save_state: str
  storage_state: str = "available"
  saved_at: str | None = None
  created_at: str
  analysis: SavedVideoAnalysisResponse | None = None


class SaveVideoResponse(BaseModel):
  video_id: UUID
  save_state: str


class DiscardVideoResponse(BaseModel):
  video_id: UUID
  discarded: bool


class AnalyzedVideoExportResponse(BaseModel):
  video_id: UUID
  analysis_id: UUID
  storage_path: str
  export_url: str


class SavedVideoPlaybackUrlResponse(BaseModel):
  video_id: UUID
  video_url: str


class CleanupExpiredVideosResponse(BaseModel):
  deleted_count: int


class StorageCleanupResponse(BaseModel):
  pending_deleted: int
  saved_media_pruned: int
  exports_deleted: int
  orphans_deleted: int
  bytes_deleted: int


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

  if current_status == "completed":
    analysis = repository.get_analysis_result(video_id_str)

    if not analysis_is_current(analysis):
      StorageService().validate_video_object(video["storage_path"])
      repository.update_video(video_id_str, {"status": "queued"})
      background_tasks.add_task(_run_analysis_job, video_id_str)
      return AnalyzeResponse(video_id=video_id, status="queued")

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


@router.get("/videos/saved", response_model=list[SavedVideoResponse])
def list_saved_videos(
  user_id: str = Depends(get_current_user_id),
) -> list[SavedVideoResponse]:
  repository = VideoRepository()
  storage = StorageService()
  videos = repository.list_saved_videos(user_id)
  saved_videos: list[SavedVideoResponse] = []

  for video in videos:
    analysis = repository.get_analysis_result(video["id"])
    result_json = annotate_analysis_freshness(analysis["result_json"], analysis) if analysis else {}
    normalized_analysis = None

    if analysis:
      normalized_analysis = SavedVideoAnalysisResponse(
        id=analysis["id"],
        model_version=analysis["model_version"],
        created_at=analysis["created_at"],
        result_json=result_json,
        summary=result_json.get("summary_flags") or result_json.get("summaryFlags") or [],
        coaching_feedback=result_json.get("coach_feedback") or result_json.get("coachingFeedback") or [],
        rep_data=result_json.get("reps") or [],
      )

    thumbnail_path = video.get("thumbnail_path")
    storage_state = video.get("storage_state") or "available"
    saved_videos.append(
      SavedVideoResponse(
        id=video["id"],
        exercise_type=video["exercise_type"],
        view_type=video["view_type"],
        storage_path=video["storage_path"],
        thumbnail_path=thumbnail_path,
        video_url=None,
        thumbnail_url=storage.create_signed_url(thumbnail_path) if thumbnail_path else None,
        save_state=video["save_state"],
        storage_state=storage_state,
        saved_at=video.get("saved_at"),
        created_at=video["created_at"],
        analysis=normalized_analysis,
      )
    )

  return saved_videos


@router.get("/videos/{video_id}/playback-url", response_model=SavedVideoPlaybackUrlResponse)
def get_saved_video_playback_url(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> SavedVideoPlaybackUrlResponse:
  repository = VideoRepository()
  storage = StorageService()
  video = repository.require_owned_video(str(video_id), user_id)

  if video.get("save_state") != "saved":
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Only saved videos can be opened from the saved library.",
    )

  if (video.get("storage_state") or "available") != "available":
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="The source video has expired. Analysis is still available, but playback is unavailable.",
    )

  return SavedVideoPlaybackUrlResponse(
    video_id=video_id,
    video_url=storage.create_signed_url(video["storage_path"]),
  )


@router.post("/videos/{video_id}/analyzed-export", response_model=AnalyzedVideoExportResponse)
def export_analyzed_video(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> AnalyzedVideoExportResponse:
  repository = VideoRepository()
  storage = StorageService()
  video_id_str = str(video_id)
  video = repository.require_owned_video(video_id_str, user_id)

  if video.get("save_state") != "saved":
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Only saved videos can be exported.",
    )

  if (video.get("storage_state") or "available") != "available":
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="The source video has expired. Analysis is still available, but export is unavailable.",
    )

  analysis = repository.get_analysis_result(video_id_str)

  if not analysis:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail="Analysis result not available for export.",
    )

  analysis_id = str(analysis["id"])
  export_path = f"{user_id}/exports/{video_id_str}-{analysis_id}-h264-v1.mp4"

  if not storage.storage_path_exists(export_path):
    source_file: Path | None = None
    output_file: Path | None = None

    try:
      source_file = storage.download_to_tempfile(video["storage_path"])

      with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_output:
        output_file = Path(temp_output.name)

      render_analyzed_video(
        source_path=source_file,
        output_path=output_file,
        result_json=annotate_analysis_freshness(analysis["result_json"], analysis),
      )
      storage.upload_file(export_path, output_file, "video/mp4")
    finally:
      if source_file:
        storage.remove_tempfile(source_file)

      if output_file:
        storage.remove_tempfile(output_file)

  return AnalyzedVideoExportResponse(
    video_id=video_id,
    analysis_id=analysis["id"],
    storage_path=export_path,
    export_url=storage.create_signed_url(export_path),
  )


@router.post("/videos/{video_id}/discard", response_model=DiscardVideoResponse)
def discard_video(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> DiscardVideoResponse:
  # Discard removes both the storage object and the DB row.
  repository = VideoRepository()
  storage = StorageService()
  video = repository.require_owned_video(str(video_id), user_id)
  storage.delete_storage_path(video["storage_path"])
  if video.get("thumbnail_path"):
    storage.delete_storage_path(video["thumbnail_path"])
  storage.delete_storage_prefix(f"{user_id}/exports/{video_id}-")
  repository.delete_video_with_analysis(str(video_id))
  return DiscardVideoResponse(video_id=video_id, discarded=True)


def _delete_paths(storage: StorageService, paths: list[str | None]) -> int:
  storage_paths = [path for path in paths if path]
  bytes_deleted = 0

  for path in storage_paths:
    try:
      bytes_deleted += object_size_bytes(storage.get_object_info(path))
    except HTTPException:
      continue

  if storage_paths:
    storage.delete_storage_paths(storage_paths)

  return bytes_deleted


def _cleanup_storage_objects(
  repository: VideoRepository,
  storage: StorageService,
) -> StorageCleanupResponse:
  settings = get_settings()
  now = datetime.now(timezone.utc)
  export_cutoff = now - timedelta(hours=settings.export_storage_ttl_hours)
  pending_deleted = 0
  saved_media_pruned = 0
  exports_deleted = 0
  orphans_deleted = 0
  bytes_deleted = 0

  for video in repository.list_expired_pending_videos():
    bytes_deleted += _delete_paths(storage, [video.get("storage_path"), video.get("thumbnail_path")])
    storage.delete_storage_prefix(f"{video['user_id']}/exports/{video['id']}-")
    repository.delete_video_with_analysis(video["id"])
    pending_deleted += 1

  for video in repository.list_expired_saved_videos_with_media():
    bytes_deleted += _delete_paths(storage, [video.get("storage_path")])
    repository.update_video(
      video["id"],
      {
        "storage_state": "pruned",
        "storage_pruned_at": now.isoformat(),
      },
    )
    saved_media_pruned += 1

  objects = storage.list_objects_recursive()
  export_paths = [
    object_info["path"]
    for object_info in objects
    if "/exports/" in str(object_info.get("path") or "")
    and (
      object_updated_at(object_info) is None
      or object_updated_at(object_info) < export_cutoff
    )
  ]
  bytes_deleted += sum(
    object_size_bytes(object_info)
    for object_info in objects
    if object_info.get("path") in set(export_paths)
  )
  if export_paths:
    storage.delete_storage_paths(export_paths)
  exports_deleted = len(export_paths)

  referenced_paths = repository.list_storage_reference_paths()
  orphan_paths = [
    object_info["path"]
    for object_info in objects
    if object_info.get("path") not in referenced_paths
    and "/exports/" not in str(object_info.get("path") or "")
  ]
  bytes_deleted += sum(
    object_size_bytes(object_info)
    for object_info in objects
    if object_info.get("path") in set(orphan_paths)
  )
  if orphan_paths:
    storage.delete_storage_paths(orphan_paths)
  orphans_deleted = len(orphan_paths)

  return StorageCleanupResponse(
    pending_deleted=pending_deleted,
    saved_media_pruned=saved_media_pruned,
    exports_deleted=exports_deleted,
    orphans_deleted=orphans_deleted,
    bytes_deleted=bytes_deleted,
  )


def _is_missing_retention_migration_error(error: Exception) -> bool:
  error_text = str(error).lower()
  return (
    "storage_state" in error_text
    or "storage_pruned_at" in error_text
    or "original_size_bytes" in error_text
    or "uploaded_size_bytes" in error_text
  ) and ("does not exist" in error_text or "could not find" in error_text)


@router.post("/videos/cleanup-expired", response_model=CleanupExpiredVideosResponse)
def cleanup_expired_videos() -> CleanupExpiredVideosResponse:
  # Kept for local development; production cleanup uses /internal/storage/cleanup.
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


@router.post("/internal/storage/cleanup", response_model=StorageCleanupResponse)
def cleanup_storage(
  x_cleanup_token: str | None = Header(default=None, alias="X-Cleanup-Token"),
) -> StorageCleanupResponse:
  settings = get_settings()

  if not settings.storage_cleanup_token:
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Storage cleanup token is not configured.",
    )

  if x_cleanup_token != settings.storage_cleanup_token:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Invalid cleanup token.",
    )

  try:
    response = _cleanup_storage_objects(VideoRepository(), StorageService())
  except Exception as error:
    if _is_missing_retention_migration_error(error):
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Apply supabase/migrations/202605270001_storage_retention_metadata.sql before running storage cleanup.",
      ) from error

    raise
  logger.info(
    "Storage cleanup completed at %s: %s",
    datetime.now(timezone.utc).isoformat(),
    response.dict(),
  )
  return response


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
    result_json=annotate_analysis_freshness(result["result_json"], result),
  )
