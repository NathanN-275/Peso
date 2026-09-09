from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..analysis.manual_tracking import validate_tracking_setup
from ..services.auth import get_current_user_id
from ..services.azure_blob_storage import AzureBlobConfigurationError, get_azure_blob_storage
from ..services.config import get_settings
from ..services.media_metadata import MediaValidationError, enforce_video_limits, probe_video_metadata
from ..services.storage_service import ALLOWED_VIDEO_EXTENSIONS, ALLOWED_VIDEO_MIME_TYPES, _has_expected_video_signature
from ..services.upload_reservations import UploadReservationRepository


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload-reservations", tags=["upload-reservations"])
ALLOWED_EXERCISE_TYPES = {
  "squat", "front squat", "zercher squat", "box squat", "goblet squat",
  "bench press", "incline bench press", "deadlift", "romanian deadlift",
  "overhead press", "barbell row",
}
ALLOWED_VIEW_TYPES = {"side", "front"}


class StrictRequestModel(BaseModel):
  model_config = ConfigDict(extra="forbid")


class CreateUploadReservationRequest(StrictRequestModel):
  file_name: str = Field(min_length=1, max_length=255)
  content_type: str = Field(min_length=1, max_length=100)
  size_bytes: int = Field(gt=0)
  source_type: Literal["camera", "camera_roll"] = "camera_roll"
  exercise_type: str = Field(min_length=1, max_length=80)
  view_type: str = Field(min_length=1, max_length=20)
  duration_ms: int | None = Field(default=None, gt=0)
  tracking_setup: dict | None = None


class UploadReservationResponse(BaseModel):
  reservation_id: UUID
  state: Literal["issued"]
  blob_path: str
  upload_url: str
  upload_headers: dict[str, str]
  expires_at: str


class CompleteUploadReservationResponse(BaseModel):
  reservation_id: UUID
  state: Literal["verified", "consumed"]
  video_id: UUID
  status: Literal["uploaded", "queued", "processing", "completed"]
  storage_path: str
  uploaded_size_bytes: int
  media_metadata: dict


def _normalize_content_type(value: str) -> str:
  return value.split(";", 1)[0].strip().lower()


def _validate_request(request: CreateUploadReservationRequest) -> tuple[str, str, str, str]:
  settings = get_settings()
  extension = Path(request.file_name).suffix.lower()
  content_type = _normalize_content_type(request.content_type)
  exercise_type = " ".join(request.exercise_type.strip().lower().split())
  view_type = " ".join(request.view_type.strip().lower().split())

  if extension not in ALLOWED_VIDEO_EXTENSIONS or content_type not in ALLOWED_VIDEO_MIME_TYPES:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="Unsupported video format. Upload an MP4, MOV, M4V, or WebM video.",
    )
  if request.size_bytes > settings.max_video_upload_bytes:
    raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Video exceeds the 50 MB limit.")
  if request.duration_ms is not None and request.duration_ms > settings.max_video_duration_ms:
    raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Video exceeds the five-minute limit.")
  if exercise_type not in ALLOWED_EXERCISE_TYPES:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported exercise type.")
  if view_type not in ALLOWED_VIEW_TYPES:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported camera view.")
  return extension, content_type, exercise_type, view_type


@router.post("", response_model=UploadReservationResponse, status_code=status.HTTP_201_CREATED)
def create_upload_reservation(
  request: CreateUploadReservationRequest,
  user_id: str = Depends(get_current_user_id),
) -> UploadReservationResponse:
  settings = get_settings()
  if not settings.upload_reservations_enabled:
    logger.warning("Upload reservation denied event=budget_admission_shutdown user_id=%s", user_id)
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="New uploads are temporarily paused by the beta budget guardrail.",
    )

  extension, content_type, exercise_type, view_type = _validate_request(request)
  normalized_tracking_setup = None
  if request.tracking_setup is not None:
    normalized_tracking_setup, tracking_error = validate_tracking_setup(
      request.tracking_setup,
      duration_ms=request.duration_ms,
    )
    if tracking_error:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid tracking setup: {tracking_error}.")

  reservation_id = uuid4()
  expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.upload_reservation_ttl_seconds)
  blob_path = f"{user_id}/source/{reservation_id}{extension}"
  try:
    storage = get_azure_blob_storage()
  except AzureBlobConfigurationError as error:
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Private upload storage is not configured.") from error
  repository = UploadReservationRepository()
  try:
    row = repository.reserve(
      {
        "id": str(reservation_id),
        "user_id": user_id,
        "blob_path": blob_path,
        "file_name": Path(request.file_name).name,
        "content_type": content_type,
        "requested_bytes": request.size_bytes,
        "expires_at": expires_at.isoformat(),
        "source_type": request.source_type,
        "exercise_type": exercise_type,
        "view_type": view_type,
        "client_duration_ms": request.duration_ms,
        "tracking_setup": normalized_tracking_setup,
      },
      {
        "max_user_active": settings.max_user_active_upload_reservations,
        "max_user_bytes": settings.max_user_reserved_bytes,
        "max_global_active": settings.max_global_active_upload_reservations,
        "max_global_bytes": settings.object_storage_limit_bytes,
        "max_user_hourly": settings.max_user_uploads_per_hour,
      },
    )
  except Exception as error:
    if str(getattr(error, "code", "")) == "P0002":
      logger.warning("Upload reservation denied event=budget_admission_shutdown user_id=%s", user_id)
      raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="New uploads are paused by the beta budget guardrail.") from error
    logger.warning("Upload reservation denied event=reservation_capacity_denial user_id=%s", user_id)
    if str(getattr(error, "code", "")) == "P0001":
      raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Upload capacity is currently full.") from error
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Upload reservation service is unavailable.") from error

  try:
    upload_url = storage.create_write_sas(blob_path, expires_at=expires_at)
  except Exception:
    logger.warning("Upload SAS issuance failed event=reservation_issuance_failure reservation_id=%s", reservation_id)
    repository.reject(str(reservation_id), user_id, "sas_issuance_failed")
    raise
  logger.info(
    "Upload reservation issued event=reservation_issued reservation_id=%s user_id=%s requested_bytes=%s",
    reservation_id,
    user_id,
    request.size_bytes,
  )
  return UploadReservationResponse(
    reservation_id=reservation_id,
    state="issued",
    blob_path=blob_path,
    upload_url=upload_url,
    upload_headers={"x-ms-blob-type": "BlockBlob", "Content-Type": content_type, "If-None-Match": "*"},
    expires_at=str(row.get("expires_at") or expires_at.isoformat()),
  )


@router.post("/{reservation_id}/complete", response_model=CompleteUploadReservationResponse)
def complete_upload_reservation(
  reservation_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> CompleteUploadReservationResponse:
  settings = get_settings()
  repository = UploadReservationRepository()
  reservation = repository.require_owned(str(reservation_id), user_id)

  if reservation.get("state") in {"verified", "consumed"} and reservation.get("video_id"):
    metadata = reservation.get("media_metadata") or {}
    return CompleteUploadReservationResponse(
      reservation_id=reservation_id,
      state=reservation["state"],
      video_id=reservation["video_id"],
      status="uploaded" if reservation["state"] == "verified" else "queued",
      storage_path=reservation["blob_path"],
      uploaded_size_bytes=int(reservation.get("actual_bytes") or 0),
      media_metadata=metadata,
    )

  try:
    expires_at = datetime.fromisoformat(str(reservation["expires_at"]).replace("Z", "+00:00"))
  except (KeyError, ValueError) as error:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload reservation is invalid.") from error
  if expires_at <= datetime.now(timezone.utc):
    repository.reject(str(reservation_id), user_id, "reservation_expired")
    get_azure_blob_storage().delete(str(reservation["blob_path"]))
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Upload reservation has expired.")
  if reservation.get("state") not in {"issued", "uploaded"}:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload reservation cannot be completed.")

  validation_owner = str(uuid4())
  try:
    repository.mark_uploaded(str(reservation_id), user_id, validation_owner)
  except HTTPException:
    raise
  except Exception as error:
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Media verification is busy. Try again shortly.") from error
  storage = get_azure_blob_storage()
  blob_path = str(reservation["blob_path"])
  temp_path: Path | None = None
  try:
    object_info = storage.get_object_info(blob_path)
    actual_bytes = int(object_info.get("size") or 0)
    actual_content_type = _normalize_content_type(str(object_info.get("contentType") or ""))
    if actual_bytes <= 0 or actual_bytes > int(reservation["requested_bytes"]) or actual_bytes > settings.max_video_upload_bytes:
      raise MediaValidationError("byte_limit", "Uploaded bytes do not match the reservation.")
    if actual_content_type != str(reservation["content_type"]):
      raise MediaValidationError("content_type_mismatch", "Uploaded video type does not match the reservation.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(blob_path).suffix) as temporary:
      temp_path = Path(temporary.name)
    downloaded_bytes = storage.download_to_path(blob_path, temp_path, max_bytes=settings.max_video_upload_bytes)
    if downloaded_bytes != actual_bytes:
      raise MediaValidationError("byte_mismatch", "Uploaded video size changed during verification.")
    with temp_path.open("rb") as source:
      if not _has_expected_video_signature(blob_path, source.read(4096)):
        raise MediaValidationError("format_mismatch", "Uploaded file contents do not match the video format.")
    metadata = probe_video_metadata(temp_path, timeout_seconds=settings.ffmpeg_timeout_seconds)
    enforce_video_limits(
      metadata,
      max_duration_ms=settings.max_video_duration_ms,
      max_width=settings.max_video_width,
      max_height=settings.max_video_height,
      max_fps=settings.max_video_fps,
    )
    video_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.saved_video_storage_ttl_hours)
    video = repository.verify_and_create_video(
      str(reservation_id),
      user_id,
      actual_bytes=actual_bytes,
      metadata=metadata.to_dict(),
      video_expires_at=video_expires_at,
      validation_owner=validation_owner,
    )
  except MediaValidationError as error:
    repository.reject(str(reservation_id), user_id, error.code)
    storage.delete(blob_path)
    logger.warning(
      "Upload rejected event=media_validation_rejected reservation_id=%s user_id=%s reason=%s",
      reservation_id,
      user_id,
      error.code,
    )
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
  except HTTPException as error:
    logger.warning("Upload verification failed event=reservation_verification_failure reservation_id=%s status=%s", reservation_id, error.status_code)
    raise
  except Exception as error:
    logger.warning("Upload verification failed event=reservation_verification_failure reservation_id=%s error_type=%s", reservation_id, type(error).__name__)
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Video verification is temporarily unavailable. Please try again.") from error
  finally:
    if temp_path is not None:
      temp_path.unlink(missing_ok=True)

  logger.info(
    "Upload verified event=reservation_verified reservation_id=%s user_id=%s video_id=%s",
    reservation_id,
    user_id,
    video["video_id"],
  )
  return CompleteUploadReservationResponse(
    reservation_id=reservation_id,
    state="verified",
    video_id=video["video_id"],
    status="uploaded",
    storage_path=blob_path,
    uploaded_size_bytes=actual_bytes,
    media_metadata=metadata.to_dict(),
  )


@router.delete("/{reservation_id}")
def cancel_upload_reservation(
  reservation_id: UUID,
  user_id: str = Depends(get_current_user_id),
) -> dict[str, bool]:
  repository = UploadReservationRepository()
  reservation = repository.require_owned(str(reservation_id), user_id)
  if reservation.get("state") in {"verified", "consumed"}:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This reservation already created a video.")
  repository.reject(str(reservation_id), user_id, "client_cancelled")
  get_azure_blob_storage().delete(str(reservation["blob_path"]))
  return {"cancelled": True}
