from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..analysis.side_squat.quality_preflight import (
  QUALITY_PREFLIGHT_MODEL_VERSION,
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  SideSquatQualityPreflight,
)
from ..analysis.coaching_history import technique_trend_cue
from ..analysis.manual_tracking import validate_tracking_setup
from ..analysis.versioning import annotate_analysis_freshness, analysis_is_current
from ..services.analyzed_video_exports import (
  analysis_export_options,
  ensure_analyzed_video_artifact,
  export_variant,
  playback_storage_path,
)
from ..services.analysis_trace import get_analysis_trace_service
from ..services.analysis_job_repository import AnalysisJobRepository
from ..services.auth import get_current_user_id
from ..services.config import get_settings
from ..services.saved_lift_exports import ARCHIVE_BUCKET, SavedLiftExportService
from ..services.supabase_client import get_supabase_admin_client
from ..services.storage_cleanup import StorageCleanupService, cleanup_requires_token
from ..services.storage_quota import StorageQuotaService
from ..services.storage_service import StorageService
from ..services.video_repository import VideoRepository
from ..services.config import DEFAULT_MAX_VIDEO_DURATION_MS
from ..services.video_storage_paths import (
  require_user_storage_path,
  storage_path_belongs_to_user,
)
from ..services.video_work_limits import (
  acquire_video_work_slot_or_429,
  release_video_work_slot,
)


logger = logging.getLogger(__name__)
router = APIRouter()
QUEUEABLE_ANALYSIS_STATUSES = ("uploaded", "failed")
IDEMPOTENT_ANALYSIS_STATUSES = {"queued", "processing", "completed"}
ALLOWED_EXERCISE_TYPES = {
  "squat",
  "front squat",
  "zercher squat",
  "box squat",
  "goblet squat",
  "bench press",
  "incline bench press",
  "deadlift",
  "romanian deadlift",
  "overhead press",
  "barbell row",
}
ALLOWED_VIEW_TYPES = {"side", "front"}
ALLOWED_SOURCE_TYPES = {"camera", "camera_roll"}
DEFAULT_SAVED_PAGE_LIMIT = 20
MAX_SAVED_PAGE_LIMIT = 50
SAVED_OVERVIEW_PREVIEW_LIMIT = 4


class StrictRequestModel(BaseModel):
  model_config = ConfigDict(extra="forbid")


class AnalyzeResponse(BaseModel):
  video_id: UUID
  status: str
  job_id: UUID | None = None
  stage: Literal["queued", "downloading", "pose", "barbell_tracking", "saving", "ready", "failed"]


class AnalysisActivityItemResponse(BaseModel):
  job_id: UUID
  video_id: UUID
  status: Literal["queued", "processing", "ready", "failed"]
  stage: Literal["queued", "downloading", "pose", "barbell_tracking", "saving", "ready", "failed"]
  exercise_type: str
  view_type: str
  created_at: str
  updated_at: str
  expires_at: str | None = None
  thumbnail_url: str | None = None
  stage_started_at: str | None = None
  stage_timestamps: dict[str, str] = Field(default_factory=dict)
  last_heartbeat_at: str | None = None
  failure_class: str | None = None
  recovery_action: Literal["retry", "replace_upload"] | None = None


class AnalysisActivityResponse(BaseModel):
  items: list[AnalysisActivityItemResponse]
  active_count: int = Field(ge=0)
  active_limit: int = Field(ge=1)


class VideoStatusResponse(BaseModel):
  video_id: UUID
  status: str
  exercise_type: str
  view_type: str
  updated_at: str


class RegisterVideoRequest(StrictRequestModel):
  storage_path: str
  source_type: str = "camera_roll"
  exercise_type: str
  view_type: str
  duration_ms: int | None = None
  tracking_setup: dict | None = None


class RegisterVideoResponse(BaseModel):
  video_id: UUID
  status: str
  storage_path: str
  uploaded_size_bytes: int


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
  performed_reps: int | None = None
  load_value: float | None = None
  load_unit: Literal["lb", "kg"] | None = None
  storage_path: str | None = None
  thumbnail_path: str | None = None
  video_url: str | None = None
  thumbnail_url: str | None = None
  save_state: str
  storage_state: Literal["available", "pruned"] = "available"
  saved_at: str | None = None
  created_at: str
  weight: float | None = None
  weight_unit: str | None = None
  corrected_rep_count: int | None = None
  user_notes: str | None = None
  analysis: SavedVideoAnalysisResponse | None = None
  export_options: SavedVideoExportOptionsResponse | None = None


class SavedVideosPageResponse(BaseModel):
  items: list[SavedVideoResponse]
  next_cursor: str | None = None


class SavedVideoOverviewGroupResponse(BaseModel):
  exercise_type: str
  count: int
  preview_items: list[SavedVideoResponse]


class SavedVideoOverviewStatsResponse(BaseModel):
  total_saved: int
  exercise_count: int
  total_reps: int
  latest_exercise_type: str | None = None
  latest_saved_at: str | None = None
  most_trained_exercise_type: str | None = None
  most_trained_count: int = 0


class SavedVideoOverviewResponse(BaseModel):
  stats: SavedVideoOverviewStatsResponse
  groups: list[SavedVideoOverviewGroupResponse]


class SaveVideoResponse(BaseModel):
  video_id: UUID
  save_state: str
  performed_reps: int | None = None
  load_value: float | None = None
  load_unit: Literal["lb", "kg"] | None = None
  user_notes: str | None = None


class SaveVideoRequest(StrictRequestModel):
  performed_reps: int | None = Field(default=None, ge=1)
  load_value: float | None = Field(default=None, ge=0)
  load_unit: Literal["lb", "kg"] | None = None
  # Legacy coaching clients used these names before tracking-rework became
  # the canonical save contract. Accept them while keeping one persistence
  # path and one official workout-fact representation.
  weight: float | None = Field(default=None, ge=0)
  weight_unit: Literal["lb", "kg"] | None = None
  corrected_rep_count: int | None = Field(default=None, ge=1)
  user_notes: str | None = None

  @model_validator(mode="after")
  def weight_requires_unit(self) -> "SaveVideoRequest":
    if (self.load_value is None) != (self.load_unit is None):
      raise ValueError("Weight and its unit must be provided together.")
    if (self.weight is None) != (self.weight_unit is None):
      raise ValueError("Weight and its unit must be provided together.")
    if self.load_value is not None and self.weight is not None:
      if self.load_value != self.weight or self.load_unit != self.weight_unit:
        raise ValueError("Use one consistent weight value and unit.")
    if self.performed_reps is not None and self.corrected_rep_count is not None:
      if self.performed_reps != self.corrected_rep_count:
        raise ValueError("Use one consistent rep count.")
    return self

class DiscardVideoResponse(BaseModel):
  video_id: UUID
  discarded: bool


class DeleteSavedLiftsRequest(StrictRequestModel):
  lift_ids: list[UUID] = Field(min_length=1, max_length=50)


class DeleteSavedLiftsResponse(BaseModel):
  deleted_lift_ids: list[UUID]
  deleted_count: int


class UploadFailedResponse(BaseModel):
  video_id: UUID
  status: str


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


class AnalyzedVideoExportRequest(StrictRequestModel):
  pose: bool = True
  barbell: bool = False


class CleanupDetailsResponse(BaseModel):
  expired_pending_videos: int
  stale_pending_videos: int
  old_export_objects: int
  expired_saved_lift_exports: int = 0
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
  side_squat_quality_preflight: bool = False
  quality_preflight_versions: list[str] = Field(default_factory=list)
  reason: str | None = None


class QualityPreflightResponse(BaseModel):
  video_id: UUID
  status: Literal["pass", "warning", "blocked"]
  overallConfidence: float
  checks: dict[str, dict]
  userMessages: list[str]
  recordingTips: list[str]
  modelVersion: str
  thresholdVersion: str
  thresholds: dict
  sampledFrameMetadata: dict
  processingDurationMs: int


class AccountDeleteResponse(BaseModel):
  deleted: bool


def _authorize_cleanup(cleanup_token: str | None) -> None:
  settings = get_settings()

  if not cleanup_requires_token(settings):
    return

  if not settings.cleanup_job_token:
    logger.error("Rejected cleanup request because cleanup token is not configured.")
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="CLEANUP_JOB_TOKEN must be configured before running cleanup outside development.",
    )

  if cleanup_token != settings.cleanup_job_token:
    logger.warning("Rejected cleanup request with invalid cleanup token.")
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid cleanup token.",
    )


def _video_is_saved(video: dict) -> bool:
  return video.get("save_state") == "saved" or video.get("is_saved") is True


def _normalize_label(value: str) -> str:
  return " ".join(value.strip().lower().replace("_", " ").split())


def _is_side_view_squat(exercise_type: str, view_type: str) -> bool:
  return view_type == "side" and exercise_type.endswith("squat")


def _quality_preflight_is_current(preflight: object) -> bool:
  return (
    isinstance(preflight, dict)
    and preflight.get("modelVersion") == QUALITY_PREFLIGHT_MODEL_VERSION
    and preflight.get("thresholdVersion") == QUALITY_PREFLIGHT_THRESHOLD_VERSION
  )


def _require_current_quality_preflight(video: dict) -> None:
  if video.get("quality_preflight_required") is not True:
    return

  preflight = video.get("quality_preflight")
  if not _quality_preflight_is_current(preflight):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Run the current side-view squat quality preflight before starting analysis.",
    )


def _record_quality_preflight_trace(video: dict, preflight: dict) -> None:
  # Record the advisory immediately so evidence survives even when a client
  # chooses not to queue the full pipeline.
  try:
    trace = get_analysis_trace_service().start(
      video_id=str(video.get("id") or ""),
      user_id=str(video.get("user_id") or ""),
      exercise_type=str(video.get("exercise_type") or "unknown"),
      view_type=str(video.get("view_type") or "unknown"),
      model_version=str(preflight.get("modelVersion") or QUALITY_PREFLIGHT_MODEL_VERSION),
    )
    trace.snapshot("quality_preflight", quality_preflight=preflight)
    trace.complete(
      {"quality_preflight": preflight},
      {"quality_preflight": int(preflight.get("processingDurationMs") or 0)},
    )
  except Exception as trace_error:
    logger.warning(
      "Unable to record quality preflight trace for video %s: %s",
      video.get("id"),
      trace_error,
    )

def _public_storage_usage_payload(report) -> dict:
  payload = report.to_dict()

  if get_settings().expose_storage_quota_details:
    return payload

  for key in (
    "storage_limit_bytes",
    "database_limit_bytes",
    "monthly_egress_limit_bytes",
    "current_storage_bytes",
    "projected_peak_bytes",
    "warning_threshold_bytes",
    "block_threshold_bytes",
  ):
    payload[key] = 0

  return payload


def _enforce_video_registration_limits(repository: VideoRepository, user_id: str) -> None:
  settings = get_settings()
  in_progress_count = repository.count_user_in_progress_videos(user_id)
  recent_upload_count = repository.count_recent_user_uploads(
    user_id,
    (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
  )

  if not isinstance(in_progress_count, int):
    in_progress_count = 0

  if not isinstance(recent_upload_count, int):
    recent_upload_count = 0

  if in_progress_count >= settings.max_user_in_progress_videos:
    logger.warning(
      "Rejected video registration because per-user in-progress limit is saturated user_id=%s limit=%s",
      user_id,
      settings.max_user_in_progress_videos,
    )
    raise HTTPException(
      status_code=status.HTTP_429_TOO_MANY_REQUESTS,
      detail="Too many videos are already queued or processing. Wait for one to finish before uploading another.",
    )

  if recent_upload_count >= settings.max_user_uploads_per_hour:
    logger.warning(
      "Rejected video registration because per-user upload frequency is saturated user_id=%s limit=%s",
      user_id,
      settings.max_user_uploads_per_hour,
    )
    raise HTTPException(
      status_code=status.HTTP_429_TOO_MANY_REQUESTS,
      detail="Too many uploads were started recently. Try again later.",
    )


def _enforce_analysis_queue_limit(repository: VideoRepository, user_id: str) -> None:
  settings = get_settings()
  in_progress_count = repository.count_user_in_progress_videos(user_id)

  if not isinstance(in_progress_count, int):
    in_progress_count = 0

  if in_progress_count >= settings.max_user_in_progress_videos:
    logger.warning(
      "Rejected analysis queue because per-user in-progress limit is saturated user_id=%s limit=%s",
      user_id,
      settings.max_user_in_progress_videos,
    )
    raise HTTPException(
      status_code=status.HTTP_429_TOO_MANY_REQUESTS,
      detail="Too many videos are already queued or processing. Wait for one to finish before starting another.",
    )


def _setting_int(settings, name: str, default: int) -> int:
  value = getattr(settings, name, default)
  return value if isinstance(value, int) else default


def _validate_video_duration(duration_ms: int | None, settings) -> None:
  if duration_ms is None:
    return

  if duration_ms < 0:
    logger.warning("Rejected video registration with negative duration duration_ms=%s", duration_ms)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video duration must be non-negative.")

  max_duration_ms = _setting_int(settings, "max_video_duration_ms", DEFAULT_MAX_VIDEO_DURATION_MS)
  if duration_ms > max_duration_ms:
    logger.warning(
      "Rejected video registration because duration exceeds limit duration_ms=%s max_duration_ms=%s",
      duration_ms,
      max_duration_ms,
    )
    raise HTTPException(
      status_code=status.HTTP_413_CONTENT_TOO_LARGE,
      detail="Uploaded video exceeds the configured duration limit.",
    )


def _signed_url_ttl_seconds() -> int:
  settings = get_settings()
  return _setting_int(settings, "signed_url_ttl_seconds", 300)


def _create_owned_signed_url(
  storage: StorageService,
  path: str | None,
  user_id: str,
  label: str,
) -> tuple[str, str, int]:
  owned_path = require_user_storage_path(path, user_id, label)
  expires_in = _signed_url_ttl_seconds()
  return owned_path, storage.create_signed_url(owned_path, expires_in=expires_in), expires_in


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
    "analysisMode": result_json.get("analysisMode"),
    "analysisCapabilities": result_json.get("analysisCapabilities"),
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
    "confidence": rep.get("confidence"),
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
  return analysis_export_options(result_json)


def _analysis_rep_count(analysis: dict | None) -> int:
  result_json = analysis.get("result_json") if analysis else None
  if not isinstance(result_json, dict):
    return 0

  rep_count = result_json.get("rep_count") or result_json.get("repCount")
  if isinstance(rep_count, int):
    return max(0, rep_count)

  reps = result_json.get("reps")
  return len(reps) if isinstance(reps, list) else 0


def _official_rep_count(video: dict, analysis: dict | None) -> int:
  performed_reps = video.get("performed_reps")
  if isinstance(performed_reps, int) and performed_reps >= 1:
    return performed_reps
  return _analysis_rep_count(analysis)


def _load_latest_analyses(
  repository: VideoRepository,
  videos: list[dict],
) -> dict[str, dict]:
  video_ids = [str(video["id"]) for video in videos]

  if not video_ids:
    return {}

  analyses = repository.get_latest_analysis_results(video_ids)

  if isinstance(analyses, dict):
    return analyses

  return {
    video_id: analysis
    for video_id in video_ids
    if (analysis := repository.get_analysis_result(video_id))
  }


def _saved_video_response(
  *,
  video: dict,
  analysis: dict | None,
  storage: StorageService,
  user_id: str,
) -> SavedVideoResponse:
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
  thumbnail_url = None
  if thumbnail_path:
    _, thumbnail_url, _ = _create_owned_signed_url(storage, thumbnail_path, user_id, "thumbnail_path")

  return SavedVideoResponse(
    id=video["id"],
    exercise_type=video["exercise_type"],
    view_type=video["view_type"],
    performed_reps=video.get("performed_reps"),
    load_value=video.get("load_value"),
    load_unit=video.get("load_unit"),
    storage_path=None,
    thumbnail_path=thumbnail_path,
    video_url=None,
    thumbnail_url=thumbnail_url,
    save_state=video.get("save_state") or ("saved" if video.get("is_saved") else "pending"),
    storage_state=video.get("storage_state") or "available",
    saved_at=video.get("saved_at"),
    created_at=video["created_at"],
    weight=video.get("weight"),
    weight_unit=video.get("weight_unit"),
    corrected_rep_count=video.get("corrected_rep_count"),
    user_notes=video.get("user_notes"),
    analysis=normalized_analysis,
    export_options=(
      SavedVideoExportOptionsResponse(**export_options)
      if export_options
      else None
    ),
  )


def _saved_video_responses(
  *,
  videos: list[dict],
  analyses_by_video_id: dict[str, dict],
  storage: StorageService,
  user_id: str,
) -> list[SavedVideoResponse]:
  return [
    _saved_video_response(
      video=video,
      analysis=analyses_by_video_id.get(str(video["id"])),
      storage=storage,
      user_id=user_id,
    )
    for video in videos
  ]


def _encode_saved_page_cursor(offset: int) -> str:
  payload = json.dumps({"offset": max(0, offset)}, separators=(",", ":")).encode("utf-8")
  return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_saved_page_cursor(cursor: str | None) -> int:
  if not cursor:
    return 0

  try:
    padding = "=" * (-len(cursor) % 4)
    decoded = base64.urlsafe_b64decode(f"{cursor}{padding}".encode("ascii"))
    payload = json.loads(decoded.decode("utf-8"))
    offset = payload.get("offset")
  except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid saved-video cursor.") from error

  if not isinstance(offset, int) or offset < 0:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid saved-video cursor.")

  return offset


def _export_variant(*, pose: bool, barbell: bool) -> str:
  return export_variant(pose=pose, barbell=barbell)


def _playback_storage_path(video: dict) -> str:
  return playback_storage_path(video)


def _path_belongs_to_user(path: str, user_id: str) -> bool:
  return storage_path_belongs_to_user(path, user_id)


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


def _delete_saved_lift_assets(storage: StorageService, video: dict, user_id: str) -> None:
  video_id = str(video["id"])
  for path in [path for path in dict.fromkeys(_video_storage_paths(video)) if path]:
    _delete_owned_storage_path(storage, path, user_id, "Saved Lift")

  for path in storage.list_storage_prefix(f"{user_id}/exports/{video_id}-"):
    _delete_owned_storage_path(storage, path, user_id, "Saved Lift export")


@router.post("/videos", response_model=RegisterVideoResponse, status_code=status.HTTP_201_CREATED)
def register_video(
  request: RegisterVideoRequest,
  user_id: str = Depends(get_current_user_id),
) -> RegisterVideoResponse:
  storage_path = require_user_storage_path(request.storage_path, user_id, "storage_path")
  exercise_type = _normalize_label(request.exercise_type)
  view_type = _normalize_label(request.view_type)
  source_type = request.source_type.strip().lower()

  if exercise_type not in ALLOWED_EXERCISE_TYPES:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported exercise type.")

  if view_type not in ALLOWED_VIEW_TYPES:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported camera view.")

  if source_type not in ALLOWED_SOURCE_TYPES:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported video source type.")

  settings = get_settings()
  _validate_video_duration(request.duration_ms, settings)
  if settings.backend_env in {"production", "prod"} or settings.upload_reservations_enabled is True:
    raise HTTPException(
      status_code=status.HTTP_410_GONE,
      detail="Direct upload registration is retired. Update the app to use upload reservations.",
    )

  repository = VideoRepository()
  storage = StorageService()
  _enforce_video_registration_limits(repository, user_id)

  object_info = storage.validate_video_object(storage_path)
  actual_uploaded_size = storage.storage_object_size_bytes(object_info)
  if actual_uploaded_size <= 0:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to verify uploaded video size.")

  normalized_tracking_setup = None
  if request.tracking_setup is not None:
    tracking_duration_ms = request.duration_ms if request.duration_ms and request.duration_ms > 0 else None
    normalized_tracking_setup, tracking_error = validate_tracking_setup(
      request.tracking_setup,
      duration_ms=tracking_duration_ms,
    )

    if tracking_error:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid tracking setup: {tracking_error}.")

  video_id = str(uuid4())
  original_size = actual_uploaded_size
  expires_at = (
    datetime.now(timezone.utc) + timedelta(hours=settings.saved_video_storage_ttl_hours)
  ).isoformat()
  fields = {
    "id": video_id,
    "user_id": user_id,
    "storage_path": storage_path,
    "source_type": source_type,
    "exercise_type": exercise_type,
    "view_type": view_type,
    "status": "uploaded",
    "duration_ms": request.duration_ms,
    "save_state": "pending",
    "expires_at": expires_at,
    "original_size_bytes": original_size,
    "uploaded_size_bytes": actual_uploaded_size,
    "was_compressed": False,
    "storage_state": "available",
    "quality_preflight_required": _is_side_view_squat(exercise_type, view_type),
  }

  if normalized_tracking_setup is not None:
    fields["tracking_setup"] = normalized_tracking_setup

  video = repository.create_uploaded_video(fields)
  return RegisterVideoResponse(
    video_id=video["id"],
    status=video["status"],
    storage_path=video["storage_path"],
    uploaded_size_bytes=actual_uploaded_size,
  )


@router.delete("/account", response_model=AccountDeleteResponse)
def delete_account(
  user_id: str = Depends(get_current_user_id),
) -> AccountDeleteResponse:
  repository = VideoRepository()
  client = get_supabase_admin_client()

  try:
    _delete_account_storage(user_id, repository)
    StorageService(bucket=ARCHIVE_BUCKET).delete_storage_prefix(f"{user_id}/")
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
  return StorageUsageResponse(**_public_storage_usage_payload(report))


@router.get("/videos/capabilities", response_model=VideoCapabilitiesResponse)
def get_video_capabilities(
  _user_id: str = Depends(get_current_user_id),
) -> VideoCapabilitiesResponse:
  try:
    repository = VideoRepository()
    pin_assisted_tracking = repository.supports_tracking_setup()
    side_squat_quality_preflight = repository.supports_quality_preflight()
  except Exception as error:
    logger.exception("Unable to verify video tracking capabilities: %s", error)
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Unable to verify pin-assisted tracking database support.",
    ) from error

  return VideoCapabilitiesResponse(
    pin_assisted_tracking=pin_assisted_tracking,
    tracking_setup_versions=[1, 2] if pin_assisted_tracking else [],
    side_squat_quality_preflight=side_squat_quality_preflight,
    quality_preflight_versions=(
      [QUALITY_PREFLIGHT_THRESHOLD_VERSION]
      if side_squat_quality_preflight
      else []
    ),
    reason=(
      "tracking_setup_migration_missing"
      if not pin_assisted_tracking
      else "quality_preflight_migration_missing"
      if not side_squat_quality_preflight
      else None
    ),
  )


@router.post("/videos/{video_id}/quality-preflight", response_model=QualityPreflightResponse)
def run_quality_preflight(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> QualityPreflightResponse:
  repository = VideoRepository()
  video_id_str = str(video_id)
  video = repository.require_owned_video(video_id_str, user_id)
  exercise_type = str(video.get("exercise_type") or "")
  view_type = str(video.get("view_type") or "")

  if not _is_side_view_squat(exercise_type, view_type):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="Quality preflight is available only for side-view squat submissions.",
    )

  if video.get("status") != "uploaded":
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=f"Quality preflight cannot run from status '{video.get('status')}'.",
    )

  cached_preflight = video.get("quality_preflight")
  if _quality_preflight_is_current(cached_preflight):
    return QualityPreflightResponse(video_id=video_id, **cached_preflight)

  playback_path = require_user_storage_path(_playback_storage_path(video), user_id, "playback_path")
  video_work_slot = acquire_video_work_slot_or_429(
    "quality_preflight",
    user_id=user_id,
    video_id=video_id_str,
  )
  storage = StorageService()
  temp_file = None

  try:
    temp_file = storage.download_to_tempfile(playback_path)
    preflight = SideSquatQualityPreflight().evaluate_file(
      temp_file,
      exercise_type=exercise_type,
    )
    repository.update_video(video_id_str, {"quality_preflight": preflight})
    _record_quality_preflight_trace(video, preflight)
  except RuntimeError as error:
    raise HTTPException(
      status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
      detail=str(error),
    ) from error
  finally:
    if temp_file is not None:
      storage.remove_tempfile(temp_file)
    release_video_work_slot(video_work_slot)

  return QualityPreflightResponse(video_id=video_id, **preflight)


@router.post("/analyze/{video_id}", response_model=AnalyzeResponse)
def queue_analysis(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> AnalyzeResponse:
  # The durable queue owns work after this request returns.
  repository = VideoRepository()
  video_id_str = str(video_id)
  video = repository.require_owned_video(video_id_str, user_id)
  current_status = video["status"]
  allow_completed = False

  if current_status == "completed":
    analysis = repository.get_analysis_result(video_id_str)

    if analysis_is_current(analysis):
      return AnalyzeResponse(video_id=video_id, status="completed", stage="ready")
    allow_completed = True

  if current_status not in IDEMPOTENT_ANALYSIS_STATUSES and current_status not in QUEUEABLE_ANALYSIS_STATUSES:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=f"Video cannot be queued for analysis from status '{current_status}'.",
    )

  is_existing_job = current_status in {"queued", "processing"}
  if not is_existing_job:
    _require_current_quality_preflight(video)

    playback_path = require_user_storage_path(_playback_storage_path(video), user_id, "playback_path")
    StorageService().validate_video_object(playback_path)
    _enforce_analysis_queue_limit(repository, user_id)

  try:
    jobs = AnalysisJobRepository()
    job = jobs.enqueue(video_id_str, allow_completed=allow_completed)
  except Exception as error:
    if str(getattr(error, "code", "")) == "P0001":
      message = str(error).lower()
      if "capacity" in message:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Analysis queue capacity is currently full.") from error
      if "verified" in message:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This video must be uploaded and verified before analysis.") from error
    logger.exception("Durable analysis queue is unavailable for video %s.", video_id_str)
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Analysis queue is unavailable. Apply the durable analysis jobs migration and start the worker.",
    ) from error

  public_status = str(job.get("status") or "queued")
  if public_status == "retry_wait":
    public_status = "queued"
  return AnalyzeResponse(
    video_id=video_id,
    job_id=job.get("id"),
    status=public_status,
    stage=(
      str(job.get("stage"))
      if str(job.get("stage") or "") in {
        "queued", "downloading", "pose", "barbell_tracking", "saving", "ready", "failed"
      }
      else "queued"
    ),
  )


def _analysis_activity_status(video: dict, job: dict) -> str | None:
  video_status = str(video.get("status") or "")
  job_status = str(job.get("status") or "")
  if video_status == "completed" or job_status == "completed":
    return "ready"
  if video_status == "failed" or job_status == "failed":
    return "failed"
  if job_status in {"queued", "retry_wait"}:
    return "queued"
  if job_status == "processing":
    return "processing"
  return None


def _analysis_activity_stage(video: dict, job: dict) -> str:
  public_status = _analysis_activity_status(video, job)
  if public_status == "ready":
    return "ready"
  if public_status == "failed":
    return "failed"
  if public_status == "queued":
    return "queued"
  persisted = str(job.get("stage") or "")
  if persisted in {"downloading", "pose", "barbell_tracking", "saving"}:
    return persisted
  return "downloading"


def _public_analysis_failure_class(job: dict) -> str | None:
  raw_failure = str(job.get("failure_class") or "")
  normalized_error = str(job.get("last_error") or "").lower()
  if any(
    marker in normalized_error
    for marker in (
      "unable to open uploaded video",
      "invalid video",
      "unsupported video",
      "valid video stream",
      "contents do not match the selected video format",
      "unable to validate uploaded video contents",
    )
  ):
    return "invalid_video"

  allowed_failures = {
    "analysis_timeout",
    "analysis_runtime",
    "invalid_video",
    "transient_infrastructure",
    "worker_lease_expired",
    "worker_process_exit",
  }
  if raw_failure in allowed_failures:
    return raw_failure
  return "unknown" if raw_failure else None


def _analysis_recovery_action(video: dict, job: dict) -> str | None:
  if _analysis_activity_status(video, job) != "failed":
    return None

  retryable_failures = {
    "analysis_timeout",
    "transient_infrastructure",
    "worker_lease_expired",
    "worker_process_exit",
  }
  if _public_analysis_failure_class(job) in retryable_failures:
    return "retry"
  return "replace_upload"


@router.get("/videos/analysis-activity", response_model=AnalysisActivityResponse)
def get_analysis_activity(
  user_id: str = Depends(get_current_user_id),
) -> AnalysisActivityResponse:
  """Return the durable, owner-scoped work that still needs user attention."""
  repository = VideoRepository()
  jobs = AnalysisJobRepository()
  storage = StorageService()
  settings = get_settings()

  try:
    videos = repository.list_analysis_activity_videos(user_id)
    jobs_by_video_id = jobs.latest_for_videos([str(video["id"]) for video in videos])
    active_count = repository.count_user_in_progress_videos(user_id)
  except Exception as error:
    logger.exception("Analysis activity queue schema is unavailable for user %s.", user_id)
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Analysis activity is temporarily unavailable. The queue schema is not ready.",
    ) from error

  if not isinstance(active_count, int):
    active_count = 0
  items: list[AnalysisActivityItemResponse] = []

  for video in videos:
    video_id = str(video["id"])
    job = jobs_by_video_id.get(video_id)
    if not job:
      continue
    public_status = _analysis_activity_status(video, job)
    if public_status is None:
      continue

    thumbnail_url = None
    if video.get("thumbnail_path"):
      try:
        _, thumbnail_url, _ = _create_owned_signed_url(
          storage,
          str(video["thumbnail_path"]),
          user_id,
          "thumbnail_path",
        )
      except Exception as error:
        logger.warning("Unable to sign analysis activity thumbnail for video %s: %s", video_id, error)

    items.append(
      AnalysisActivityItemResponse(
        job_id=job["id"],
        video_id=video_id,
        status=public_status,
        stage=_analysis_activity_stage(video, job),
        exercise_type=str(video.get("exercise_type") or "unknown"),
        view_type=str(video.get("view_type") or "unknown"),
        created_at=str(job.get("created_at") or video.get("created_at") or ""),
        updated_at=str(job.get("updated_at") or video.get("updated_at") or ""),
        expires_at=video.get("expires_at"),
        thumbnail_url=thumbnail_url,
        stage_started_at=(str(job["stage_started_at"]) if job.get("stage_started_at") else None),
        stage_timestamps={
          str(stage): str(timestamp)
          for stage, timestamp in (job.get("stage_timestamps") or {}).items()
        },
        last_heartbeat_at=(
          str(job["last_heartbeat_at"]) if job.get("last_heartbeat_at") else None
        ),
        failure_class=_public_analysis_failure_class(job),
        recovery_action=_analysis_recovery_action(video, job),
      )
    )

  return AnalysisActivityResponse(
    items=items,
    active_count=active_count,
    active_limit=settings.max_user_in_progress_videos,
  )


@router.post("/videos/{video_id}/save", response_model=SaveVideoResponse)
def save_video(
  video_id: UUID,
  request: SaveVideoRequest | None = None,
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
  performed_reps = request.performed_reps if request else None
  corrected_rep_count = request.corrected_rep_count if request else None
  if performed_reps is None:
    performed_reps = corrected_rep_count
  load_value = request.load_value if request else None
  load_unit = request.load_unit if request else None
  if load_value is None and request:
    load_value = request.weight
    load_unit = request.weight_unit

  extra_metadata = {}
  if request and request.user_notes is not None:
    extra_metadata["user_notes"] = request.user_notes
  if request and request.weight is not None:
    extra_metadata["weight"] = request.weight
    extra_metadata["weight_unit"] = request.weight_unit
  if corrected_rep_count is not None:
    extra_metadata["corrected_rep_count"] = corrected_rep_count

  save_kwargs = {
    "performed_reps": performed_reps,
    "load_value": load_value,
    "load_unit": load_unit,
  }
  if extra_metadata:
    save_kwargs["metadata"] = extra_metadata
  saved_video = repository.mark_saved(str(video_id), **save_kwargs)
  return SaveVideoResponse(
    video_id=video_id,
    save_state=saved_video["save_state"],
    performed_reps=saved_video.get("performed_reps"),
    load_value=saved_video.get("load_value"),
    load_unit=saved_video.get("load_unit"),
    user_notes=saved_video.get("user_notes"),
  )


@router.get("/videos/saved", response_model=list[SavedVideoResponse])
def list_saved_videos(
  user_id: str = Depends(get_current_user_id),
) -> list[SavedVideoResponse]:
  repository = VideoRepository()
  storage = StorageService()
  videos = repository.list_saved_videos(user_id)
  analyses_by_video_id = _load_latest_analyses(repository, videos)

  responses = _saved_video_responses(
    videos=videos,
    analyses_by_video_id=analyses_by_video_id,
    storage=storage,
    user_id=user_id,
  )
  for response in responses:
    analysis = response.analysis
    if not analysis:
      continue
    cue = technique_trend_cue(
      video=next(video for video in videos if str(video["id"]) == str(response.id)),
      analysis=analyses_by_video_id.get(str(response.id)),
      saved_videos=videos,
      analyses_by_video_id=analyses_by_video_id,
    )
    if cue:
      response.coaching_feedback.append(cue)
      response.result_json["coach_feedback"] = response.coaching_feedback
      response.result_json["coachingFeedback"] = response.coaching_feedback
  return responses


@router.get("/videos/saved-page", response_model=SavedVideosPageResponse)
def list_saved_videos_page(
  exercise_type: str | None = Query(default=None),
  limit: int = Query(default=DEFAULT_SAVED_PAGE_LIMIT, ge=1, le=MAX_SAVED_PAGE_LIMIT),
  cursor: str | None = Query(default=None),
  user_id: str = Depends(get_current_user_id),
) -> SavedVideosPageResponse:
  repository = VideoRepository()
  storage = StorageService()
  offset = _decode_saved_page_cursor(cursor)
  normalized_exercise_type = exercise_type.strip() if exercise_type else None
  videos = repository.list_saved_videos_page(
    user_id,
    exercise_type=normalized_exercise_type,
    offset=offset,
    limit=limit + 1,
  )
  page_videos = videos[:limit]
  analyses_by_video_id = _load_latest_analyses(repository, page_videos)
  next_cursor = (
    _encode_saved_page_cursor(offset + limit)
    if len(videos) > limit
    else None
  )

  return SavedVideosPageResponse(
    items=_saved_video_responses(
      videos=page_videos,
      analyses_by_video_id=analyses_by_video_id,
      storage=storage,
      user_id=user_id,
    ),
    next_cursor=next_cursor,
  )


@router.get("/videos/saved-overview", response_model=SavedVideoOverviewResponse)
def get_saved_video_overview(
  user_id: str = Depends(get_current_user_id),
) -> SavedVideoOverviewResponse:
  repository = VideoRepository()
  storage = StorageService()
  videos = repository.list_saved_videos(user_id)
  analyses_by_video_id = _load_latest_analyses(repository, videos)
  groups_by_exercise: dict[str, dict] = {}

  for video in videos:
    exercise_type = str(video["exercise_type"])
    group = groups_by_exercise.setdefault(
      exercise_type,
      {
        "exercise_type": exercise_type,
        "count": 0,
        "preview_videos": [],
      },
    )
    group["count"] += 1

    if len(group["preview_videos"]) < SAVED_OVERVIEW_PREVIEW_LIMIT:
      group["preview_videos"].append(video)

  latest_video = videos[0] if videos else None
  most_trained = sorted(
    groups_by_exercise.values(),
    key=lambda group: group["count"],
    reverse=True,
  )[0] if groups_by_exercise else None
  total_reps = sum(
    _official_rep_count(video, analyses_by_video_id.get(str(video["id"])))
    for video in videos
  )
  response_groups: list[SavedVideoOverviewGroupResponse] = []

  for group in groups_by_exercise.values():
    preview_videos = group["preview_videos"]
    response_groups.append(
      SavedVideoOverviewGroupResponse(
        exercise_type=group["exercise_type"],
        count=group["count"],
        preview_items=_saved_video_responses(
          videos=preview_videos,
          analyses_by_video_id=analyses_by_video_id,
          storage=storage,
          user_id=user_id,
        ),
      )
    )

  return SavedVideoOverviewResponse(
    stats=SavedVideoOverviewStatsResponse(
      total_saved=len(videos),
      exercise_count=len(groups_by_exercise),
      total_reps=total_reps,
      latest_exercise_type=latest_video.get("exercise_type") if latest_video else None,
      latest_saved_at=(
        latest_video.get("saved_at") or latest_video.get("created_at")
        if latest_video
        else None
      ),
      most_trained_exercise_type=most_trained.get("exercise_type") if most_trained else None,
      most_trained_count=most_trained.get("count") if most_trained else 0,
    ),
    groups=response_groups,
  )


@router.post("/saved-lifts/delete", response_model=DeleteSavedLiftsResponse)
def delete_saved_lifts(
  request: DeleteSavedLiftsRequest,
  user_id: str = Depends(get_current_user_id),
) -> DeleteSavedLiftsResponse:
  lift_ids = list(dict.fromkeys(str(lift_id) for lift_id in request.lift_ids))
  repository = VideoRepository()
  videos = repository.get_owned_videos(lift_ids, user_id)
  videos_by_id = {str(video["id"]): video for video in videos}

  if set(videos_by_id) != set(lift_ids):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more Saved Lifts were not found.")

  if any(not repository.video_is_saved(videos_by_id[lift_id]) for lift_id in lift_ids):
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail="Only Saved Lifts can be permanently deleted.",
    )

  storage = StorageService()
  for lift_id in lift_ids:
    _delete_saved_lift_assets(storage, videos_by_id[lift_id], user_id)
    repository.delete_video_with_analysis(lift_id)

  return DeleteSavedLiftsResponse(
    deleted_lift_ids=lift_ids,
    deleted_count=len(lift_ids),
  )


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

  expires_in = _signed_url_ttl_seconds()
  playback_candidate = video.get("playback_path")
  original_candidate = video.get("storage_path") or video.get("original_storage_path")
  original_label = "storage_path" if video.get("storage_path") else "original_storage_path"

  if playback_candidate:
    playback_path = require_user_storage_path(playback_candidate, user_id, "playback_path")

    try:
      playback_url = storage.create_signed_url(playback_path, expires_in=expires_in)
    except Exception as optimized_error:
      logger.warning(
        "Unable to sign optimized playback URL for video_id=%s path=%s; falling back to original.",
        video_id,
        playback_path,
      )
      playback_path = require_user_storage_path(original_candidate, user_id, original_label)

      try:
        playback_url = storage.create_signed_url(playback_path, expires_in=expires_in)
      except Exception as fallback_error:
        raise optimized_error from fallback_error
  else:
    playback_path = require_user_storage_path(original_candidate, user_id, original_label)
    playback_url = storage.create_signed_url(playback_path, expires_in=expires_in)

  logger.info("Signing playback URL for video_id=%s path=%s expires_in=%s", video_id, playback_path, expires_in)
  return VideoPlaybackUrlResponse(
    video_id=video_id,
    video_url=playback_url,
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

  requested = export_request or AnalyzedVideoExportRequest()
  artifact = ensure_analyzed_video_artifact(
    video=video,
    analysis=analysis,
    user_id=user_id,
    storage=storage,
    pose=requested.pose,
    barbell=requested.barbell,
  )
  export_path, export_url, _ = _create_owned_signed_url(
    storage,
    artifact.storage_path,
    user_id,
    "export_path",
  )
  return AnalyzedVideoExportResponse(
    video_id=video_id,
    analysis_id=analysis["id"],
    storage_path=export_path,
    export_url=export_url,
    variant=artifact.variant,
  )


@router.post("/videos/{video_id}/discard", response_model=DiscardVideoResponse)
def discard_video(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> DiscardVideoResponse:
  # Discard removes storage objects and keeps a discarded metadata row.
  repository = VideoRepository()
  jobs = AnalysisJobRepository()
  storage = StorageService()
  video = repository.require_owned_video(str(video_id), user_id)

  try:
    jobs.cancel_for_video(str(video_id))
  except Exception as error:
    logger.exception("Unable to cancel analysis job before discarding video %s.", video_id)
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Unable to stop analysis safely. Please try again.",
    ) from error

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


@router.post("/videos/{video_id}/upload-failed", response_model=UploadFailedResponse)
def mark_upload_failed(
  video_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> UploadFailedResponse:
  repository = VideoRepository()
  storage = StorageService()
  video = repository.require_owned_video(str(video_id), user_id)

  for path in [path for path in dict.fromkeys(_video_storage_paths(video)) if path]:
    _delete_owned_storage_path(storage, path, user_id, "failed upload")

  failed_video = repository.update_video(
    str(video_id),
    {
      "status": "failed",
      "save_state": "pending",
      "is_saved": False,
      "discarded_at": datetime.now(timezone.utc).isoformat(),
      "expires_at": None,
    },
  )
  return UploadFailedResponse(video_id=video_id, status=failed_video["status"])


@router.post("/videos/cleanup-expired", response_model=CleanupExpiredVideosResponse)
def cleanup_expired_videos(
  confirm: bool = False,
  dry_run: bool | None = None,
  cleanup_token: Annotated[str | None, Header(alias="X-Cleanup-Token")] = None,
) -> CleanupExpiredVideosResponse:
  _authorize_cleanup(cleanup_token)
  effective_dry_run = not confirm if dry_run is None else dry_run
  report = StorageCleanupService().run(dry_run=effective_dry_run)
  saved_lift_exports = SavedLiftExportService().cleanup_expired_archives(
    dry_run=effective_dry_run,
  )

  logger.info(
    "Storage cleanup completed: deleted_videos=%s dry_run=%s storage_objects=%s bytes_reclaimable=%s",
    report.deleted_count,
    report.dry_run,
    report.storage_objects,
    report.bytes_reclaimable,
  )
  candidate_count = (
    report.expired_pending_videos
    + report.stale_pending_videos
    + saved_lift_exports.candidates
  )
  return CleanupExpiredVideosResponse(
    deleted_count=report.deleted_count,
    candidate_count=candidate_count,
    dry_run=report.dry_run,
    details=CleanupDetailsResponse(
      expired_pending_videos=report.expired_pending_videos,
      stale_pending_videos=report.stale_pending_videos,
      old_export_objects=report.old_export_objects,
      expired_saved_lift_exports=saved_lift_exports.candidates,
      orphan_objects=report.orphan_objects,
      storage_objects=report.storage_objects + saved_lift_exports.candidates,
      bytes_reclaimable=report.bytes_reclaimable + saved_lift_exports.bytes_reclaimable,
      errors=[*report.errors, *saved_lift_exports.errors],
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
