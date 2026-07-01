from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from ..analysis.pipeline import analyze_video
from ..analysis.versioning import annotate_analysis_freshness, analysis_is_current
from ..services.analyzed_video_renderer import render_analyzed_video
from ..services.auth import get_current_user_id
from ..services.config import get_settings
from ..services.supabase_client import get_supabase_admin_client
from ..services.storage_cleanup import StorageCleanupService, cleanup_requires_token
from ..services.storage_quota import StorageQuotaService
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


class SavedVideoAnalysisResponse(BaseModel):
  id: UUID
  model_version: str
  created_at: str
  result_json: dict
  summary: list[str]
  coaching_feedback: list[str]
  rep_data: list[dict]


class SavedVideoExportOptionsResponse(BaseModel):
  pose: bool
  barbell: bool


class SavedVideoResponse(BaseModel):
  id: UUID
  exercise_type: str
  view_type: str
  storage_path: str | None = None
  thumbnail_path: str | None = None
  video_url: str | None = None
  thumbnail_url: str | None = None
  save_state: str
  saved_at: str | None = None
  created_at: str
  analysis: SavedVideoAnalysisResponse | None = None
  export_options: SavedVideoExportOptionsResponse | None = None


class SaveVideoResponse(BaseModel):
  video_id: UUID
  save_state: str


class DiscardVideoResponse(BaseModel):
  video_id: UUID
  discarded: bool


class VideoPlaybackUrlResponse(BaseModel):
  video_id: UUID
  video_url: str
  expires_in: int


class AnalyzedVideoExportResponse(BaseModel):
  video_id: UUID
  analysis_id: UUID
  storage_path: str
  export_url: str
  variant: str


class AnalyzedVideoExportRequest(BaseModel):
  pose: bool = True
  barbell: bool = False


class CleanupDetailsResponse(BaseModel):
  expired_pending_videos: int
  stale_pending_videos: int
  old_export_objects: int
  orphan_objects: int
  storage_objects: int
  bytes_reclaimable: int
  errors: list[str]


class CleanupExpiredVideosResponse(BaseModel):
  deleted_count: int
  candidate_count: int = 0
  dry_run: bool = True
  details: CleanupDetailsResponse


class StorageUsageResponse(BaseModel):
  storage_limit_bytes: int
  database_limit_bytes: int
  monthly_egress_limit_bytes: int
  current_storage_bytes: int
  upload_size_bytes: int
  playback_allowance_bytes: int
  thumbnail_allowance_bytes: int
  projected_peak_bytes: int
  warning_threshold_bytes: int
  block_threshold_bytes: int
  status: str
  blocked: bool
  message: str


class VideoCapabilitiesResponse(BaseModel):
  pin_assisted_tracking: bool
  tracking_setup_versions: list[int]
  reason: str | None = None


class AccountDeleteResponse(BaseModel):
  deleted: bool


def _authorize_cleanup(cleanup_token: str | None) -> None:
  settings = get_settings()

  if not cleanup_requires_token(settings):
    return

  if not settings.cleanup_job_token:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="CLEANUP_JOB_TOKEN must be configured before running cleanup outside development.",
    )

  if cleanup_token != settings.cleanup_job_token:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid cleanup token.",
    )


def _video_is_saved(video: dict) -> bool:
  return video.get("save_state") == "saved" or video.get("is_saved") is True


def _summary_analysis_payload(result_json: dict) -> dict:
  summary = result_json.get("summary_flags") or result_json.get("summaryFlags") or []
  coaching_feedback = result_json.get("coach_feedback") or result_json.get("coachingFeedback") or []
  reps = [_summary_rep_payload(rep) for rep in result_json.get("reps") or [] if isinstance(rep, dict)]
  rep_count = int(result_json.get("rep_count") or len(reps))
  analysis_stale = result_json.get("analysis_stale") or result_json.get("diagnostics", {}).get("analysis_stale") or False
  analysis_incomplete = (
    result_json.get("analysis_incomplete")
    or result_json.get("diagnostics", {}).get("analysis_incomplete")
    or False
  )
  diagnostics: dict[str, bool] = {}

  if analysis_stale:
    diagnostics["analysis_stale"] = True

  if analysis_incomplete:
    diagnostics["analysis_incomplete"] = True

  return {
    "summary_flags": summary,
    "summaryFlags": summary,
    "coach_feedback": coaching_feedback,
    "coachingFeedback": coaching_feedback,
    "rep_count": rep_count,
    "reps": reps,
    "analysis_stale": analysis_stale,
    "analysis_incomplete": analysis_incomplete,
    "diagnostics": diagnostics,
  }


def _summary_rep_payload(rep: dict) -> dict:
  velocity = rep.get("estimated_body_velocity") or {}

  return {
    "rep_index": rep.get("rep_index"),
    "repIndex": rep.get("repIndex"),
    "duration": rep.get("duration"),
    "repSpeed": rep.get("repSpeed"),
    "avgVelocity": rep.get("avgVelocity"),
    "peakVelocity": rep.get("peakVelocity"),
    "estimated_body_velocity": {
      "avg_velocity": velocity.get("avg_velocity"),
      "peak_velocity": velocity.get("peak_velocity"),
    },
    "depthScore": rep.get("depthScore"),
    "depth_score": rep.get("depth_score"),
    "depthStatus": rep.get("depthStatus"),
    "depth_status": rep.get("depth_status"),
    "flags": rep.get("flags") or [],
    "timestamps_ms": rep.get("timestamps_ms"),
  }


def _analysis_export_options(result_json: dict) -> dict[str, bool]:
  pose_frames = result_json.get("poseFrames")
  barbell_path = result_json.get("barbellPath") or {}
  barbell_points = barbell_path.get("points") if isinstance(barbell_path, dict) else None

  return {
    "pose": isinstance(pose_frames, list) and len(pose_frames) > 0,
    "barbell": (
      isinstance(barbell_path, dict)
      and barbell_path.get("available") is True
      and isinstance(barbell_points, list)
      and len(barbell_points) >= 2
    ),
  }


def _export_variant(*, pose: bool, barbell: bool) -> str:
  if pose and barbell:
    return "pose-barbell"
  if pose:
    return "pose"
  if barbell:
    return "barbell"
  return "clean"


def _playback_storage_path(video: dict) -> str:
  return str(video.get("playback_path") or video["storage_path"])


def _path_belongs_to_user(path: str, user_id: str) -> bool:
  return bool(path) and path.startswith(f"{user_id}/")


def _delete_owned_storage_path(storage: StorageService, path: str, user_id: str, label: str) -> bool:
  if not path:
    return False

  if not _path_belongs_to_user(path, user_id):
    logger.warning("Skipping %s deletion outside user folder user_id=%s path=%s", label, user_id, path)
    return False

  try:
    logger.info("Deleting %s storage object path=%s", label, path)
    storage.delete_storage_path(path)
    return True
  except Exception as error:
    logger.warning("Unable to delete %s storage object path=%s: %s", label, path, error)
    return False


def _run_analysis_job(video_id: str) -> None:
  # Background tasks run analysis outside the request lifecycle.
  try:
    analyze_video(video_id)
  except Exception:
    logger.exception("Background analysis failed for video %s", video_id)


def _video_storage_paths(video: dict) -> list[str]:
  return [
    str(video.get("storage_path") or ""),
    str(video.get("original_storage_path") or ""),
    str(video.get("playback_path") or ""),
    str(video.get("thumbnail_path") or ""),
  ]


def _delete_account_storage(user_id: str, repository: VideoRepository) -> None:
  storage = StorageService()
  owned_paths: list[str] = []

  for video in repository.list_user_videos(user_id):
    owned_paths.extend(
      path for path in _video_storage_paths(video) if _path_belongs_to_user(path, user_id)
    )
    owned_paths.extend(storage.list_storage_prefix(f"{user_id}/exports/{video['id']}-"))

  storage.delete_storage_paths(owned_paths)
  StorageService(bucket="profile-avatars").delete_storage_prefix(f"{user_id}/")


@router.delete("/account", response_model=AccountDeleteResponse)
def delete_account(
  user_id: str = Depends(get_current_user_id),
) -> AccountDeleteResponse:
  repository = VideoRepository()
  client = get_supabase_admin_client()

  try:
    _delete_account_storage(user_id, repository)
    client.table("profiles").delete().eq("id", user_id).execute()
    client.auth.admin.delete_user(user_id)
  except Exception as error:
    logger.exception("Unable to delete account user_id=%s", user_id)
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="Unable to delete account. Please try again.",
    ) from error

  return AccountDeleteResponse(deleted=True)


@router.get("/videos/storage-usage", response_model=StorageUsageResponse)
def get_storage_usage(
  upload_size_bytes: int = Query(default=0, ge=0),
  _user_id: str = Depends(get_current_user_id),
) -> StorageUsageResponse:
  report = StorageQuotaService().get_usage(upload_size_bytes)
  return StorageUsageResponse(**report.to_dict())


@router.get("/videos/capabilities", response_model=VideoCapabilitiesResponse)
def get_video_capabilities(
  _user_id: str = Depends(get_current_user_id),
) -> VideoCapabilitiesResponse:
  try:
    pin_assisted_tracking = VideoRepository().supports_tracking_setup()
  except Exception as error:
    logger.exception("Unable to verify video tracking capabilities: %s", error)
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Unable to verify pin-assisted tracking database support.",
    ) from error

  return VideoCapabilitiesResponse(
    pin_assisted_tracking=pin_assisted_tracking,
    tracking_setup_versions=[1] if pin_assisted_tracking else [],
    reason=None if pin_assisted_tracking else "tracking_setup_migration_missing",
  )


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
      StorageService().validate_video_object(_playback_storage_path(video))
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

  StorageService().validate_video_object(_playback_storage_path(video))
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
  video = repository.require_owned_video(str(video_id), user_id)
  if video.get("discarded_at"):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Discarded videos cannot be saved.",
    )
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
    export_options = None

    if analysis:
      summary_payload = _summary_analysis_payload(result_json)
      export_options = _analysis_export_options(result_json)
      normalized_analysis = SavedVideoAnalysisResponse(
        id=analysis["id"],
        model_version=analysis["model_version"],
        created_at=analysis["created_at"],
        result_json=summary_payload,
        summary=summary_payload["summary_flags"],
        coaching_feedback=summary_payload["coach_feedback"],
        rep_data=summary_payload["reps"],
      )

    thumbnail_path = video.get("thumbnail_path")
    saved_videos.append(
      SavedVideoResponse(
        id=video["id"],
        exercise_type=video["exercise_type"],
        view_type=video["view_type"],
        storage_path=None,
        thumbnail_path=thumbnail_path,
        video_url=None,
        thumbnail_url=storage.create_signed_url(thumbnail_path) if thumbnail_path else None,
        save_state=video.get("save_state") or ("saved" if video.get("is_saved") else "pending"),
        saved_at=video.get("saved_at"),
        created_at=video["created_at"],
        analysis=normalized_analysis,
        export_options=(
          SavedVideoExportOptionsResponse(**export_options)
          if export_options
          else None
        ),
      )
    )

  return saved_videos


@router.get("/videos/{video_id}/playback-url", response_model=VideoPlaybackUrlResponse)
def get_video_playback_url(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> VideoPlaybackUrlResponse:
  repository = VideoRepository()
  storage = StorageService()
  video = repository.require_owned_video(str(video_id), user_id)

  if video.get("discarded_at"):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

  expires_in = 300
  playback_path = _playback_storage_path(video)
  logger.info("Signing playback URL for video_id=%s path=%s expires_in=%s", video_id, playback_path, expires_in)
  return VideoPlaybackUrlResponse(
    video_id=video_id,
    video_url=storage.create_signed_url(playback_path, expires_in=expires_in),
    expires_in=expires_in,
  )


@router.post("/videos/{video_id}/analyzed-export", response_model=AnalyzedVideoExportResponse)
def export_analyzed_video(
  video_id: UUID,
  export_request: AnalyzedVideoExportRequest | None = None,
  user_id: str = Depends(get_current_user_id),
) -> AnalyzedVideoExportResponse:
  repository = VideoRepository()
  storage = StorageService()
  video_id_str = str(video_id)
  video = repository.require_owned_video(video_id_str, user_id)

  if not _video_is_saved(video):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Only saved videos can be exported.",
    )

  if video.get("storage_state") == "pruned":
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
  requested = export_request or AnalyzedVideoExportRequest()
  variant = _export_variant(pose=requested.pose, barbell=requested.barbell)

  if variant == "clean":
    playback_path = _playback_storage_path(video)
    return AnalyzedVideoExportResponse(
      video_id=video_id,
      analysis_id=analysis["id"],
      storage_path=playback_path,
      export_url=storage.create_signed_url(playback_path),
      variant=variant,
    )

  export_path = f"{user_id}/exports/{video_id_str}-{analysis_id}-{variant}-h264-v1.mp4"

  if not storage.storage_path_exists(export_path):
    source_file: Path | None = None
    output_file: Path | None = None

    try:
      source_file = storage.download_to_tempfile(_playback_storage_path(video))

      with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_output:
        output_file = Path(temp_output.name)

      render_analyzed_video(
        source_path=source_file,
        output_path=output_file,
        result_json=annotate_analysis_freshness(analysis["result_json"], analysis),
        include_pose=requested.pose,
        include_barbell=requested.barbell,
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
    variant=variant,
  )


@router.post("/videos/{video_id}/discard", response_model=DiscardVideoResponse)
def discard_video(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> DiscardVideoResponse:
  # Discard removes storage objects and keeps a discarded metadata row.
  repository = VideoRepository()
  storage = StorageService()
  video = repository.require_owned_video(str(video_id), user_id)

  paths = [
    str(video.get("storage_path") or ""),
    str(video.get("original_storage_path") or ""),
    str(video.get("playback_path") or ""),
    str(video.get("thumbnail_path") or ""),
  ]

  for path in [path for path in dict.fromkeys(paths) if path]:
    _delete_owned_storage_path(storage, path, user_id, "discard")

  for path in storage.list_storage_prefix(f"{user_id}/exports/{video_id}-"):
    _delete_owned_storage_path(storage, path, user_id, "export")

  repository.mark_discarded(str(video_id))
  return DiscardVideoResponse(video_id=video_id, discarded=True)


@router.post("/videos/cleanup-expired", response_model=CleanupExpiredVideosResponse)
def cleanup_expired_videos(
  confirm: bool = False,
  dry_run: bool | None = None,
  cleanup_token: Annotated[str | None, Header(alias="X-Cleanup-Token")] = None,
) -> CleanupExpiredVideosResponse:
  _authorize_cleanup(cleanup_token)
  effective_dry_run = not confirm if dry_run is None else dry_run
  report = StorageCleanupService().run(dry_run=effective_dry_run)

  logger.info(
    "Storage cleanup completed: deleted_videos=%s dry_run=%s storage_objects=%s bytes_reclaimable=%s",
    report.deleted_count,
    report.dry_run,
    report.storage_objects,
    report.bytes_reclaimable,
  )
  candidate_count = report.expired_pending_videos + report.stale_pending_videos
  return CleanupExpiredVideosResponse(
    deleted_count=report.deleted_count,
    candidate_count=candidate_count,
    dry_run=report.dry_run,
    details=CleanupDetailsResponse(
      expired_pending_videos=report.expired_pending_videos,
      stale_pending_videos=report.stale_pending_videos,
      old_export_objects=report.old_export_objects,
      orphan_objects=report.orphan_objects,
      storage_objects=report.storage_objects,
      bytes_reclaimable=report.bytes_reclaimable,
      errors=report.errors,
    ),
  )


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
