from __future__ import annotations

import logging
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from .analyzed_video_exports import ensure_analyzed_video_artifact
from .archive_writes import file_sha256, plan_archive, read_published_archive, unavailable, write_archive
from .analyzed_export_writes import require_cached_export_object
from .config import Settings, get_settings
from .saved_lift_export_repository import SavedLiftExportRepository
from .storage_service import StorageService
from .video_repository import VideoRepository
from .video_storage_paths import require_user_storage_path


logger = logging.getLogger(__name__)
MAX_SAVED_LIFT_EXPORT_ITEMS = 50
ARCHIVE_BUCKET = "saved-lift-exports"


@dataclass(frozen=True)
class SavedLiftExportCleanupResult:
  candidates: int = 0
  deleted: int = 0
  bytes_reclaimable: int = 0
  errors: tuple[str, ...] = ()


def _parse_datetime(value: Any) -> datetime | None:
  if isinstance(value, datetime):
    parsed = value
  elif isinstance(value, str) and value:
    try:
      parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
      return None
  else:
    return None

  if parsed.tzinfo is None:
    return parsed.replace(tzinfo=timezone.utc)
  return parsed.astimezone(timezone.utc)


def _deduplicate_ids(video_ids: list[str]) -> list[str]:
  return list(dict.fromkeys(str(video_id) for video_id in video_ids))


class SavedLiftExportService:
  def __init__(
    self,
    *,
    videos: VideoRepository | None = None,
    jobs: SavedLiftExportRepository | None = None,
    video_storage: StorageService | None = None,
    archive_storage: StorageService | None = None,
    settings: Settings | None = None,
  ) -> None:
    self.videos = videos or VideoRepository()
    self.jobs = jobs or SavedLiftExportRepository()
    self.video_storage = video_storage or StorageService()
    self.archive_storage = archive_storage or StorageService(bucket=ARCHIVE_BUCKET)
    self.settings = settings or get_settings()

  def create_job(self, user_id: str, video_ids: list[str]) -> dict[str, Any]:
    selected_ids = _deduplicate_ids(video_ids)

    if not selected_ids:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one Saved Lift.")

    if len(selected_ids) > MAX_SAVED_LIFT_EXPORT_ITEMS:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Select no more than {MAX_SAVED_LIFT_EXPORT_ITEMS} Saved Lifts per export.",
      )

    self._load_exportable_lifts(user_id, selected_ids)
    return self.jobs.create(user_id, selected_ids)

  def get_job(self, job_id: str, user_id: str) -> dict[str, Any]:
    job = self.jobs.require_owned(job_id, user_id)
    expires_at = _parse_datetime(job.get("expires_at"))

    if job.get("status") == "completed" and expires_at and expires_at <= datetime.now(timezone.utc):
      self._expire_job(job)
      job = {**job, "status": "expired", "archive_path": None}

    return job

  def job_projection(self, job_id: str, user_id: str) -> dict[str, Any]:
    job = self.get_job(job_id, user_id)
    download_url = None
    download_expires_in = None

    if job.get("status") == "completed":
      archive_path = require_user_storage_path(job.get("archive_path"), user_id, "archive_path")
      expires_at = _parse_datetime(job.get("expires_at"))
      remaining_seconds = int((expires_at - datetime.now(timezone.utc)).total_seconds()) if expires_at else 0

      if remaining_seconds <= 0:
        self._expire_job(job)
        job = {**job, "status": "expired", "archive_path": None}
      else:
        published = read_published_archive(self.archive_storage.client, user_id=user_id,
                                           job_id=str(job["id"]), storage_path=archive_path)
        require_cached_export_object(self.archive_storage, published)
        if not self.settings.private_media_enabled:
          download_expires_in = min(self.settings.signed_url_ttl_seconds, remaining_seconds)
          download_url = self.archive_storage.create_signed_url(
            archive_path,
            expires_in=download_expires_in,
          )

    return {
      "id": job["id"],
      "status": job["status"],
      "lift_ids": job.get("video_ids") or [],
      "lift_count": len(job.get("video_ids") or []),
      "created_at": job["created_at"],
      "completed_at": job.get("completed_at"),
      "expires_at": job.get("expires_at"),
      "download_url": download_url,
      "download_expires_in": download_expires_in,
      "failure_code": job.get("failure_code"),
    }

  def process_job(self, job_id: str, user_id: str) -> None:
    archive_file: Path | None = None
    uploaded_archive_path: str | None = None

    try:
      processing = self.jobs.mark_processing(job_id, user_id)
      if not processing:
        return
      if not isinstance(processing, dict) or processing.get("id") != job_id or processing.get("status") != "processing" or processing.get("user_id") != user_id:
        raise RuntimeError("Unexpected Saved Lift export processing response.")

      job = self.jobs.require_owned(job_id, user_id)
      selected_ids = [str(video_id) for video_id in job.get("video_ids") or []]
      videos = self._load_exportable_lifts(user_id, selected_ids)
      plan = plan_archive(self.archive_storage, job)
      members = []

      with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_archive:
        archive_file = Path(temp_archive.name)

      with zipfile.ZipFile(archive_file, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for index, video_id in enumerate(selected_ids, start=1):
          video = videos[video_id]
          member = plan["member_snapshots"][index - 1]
          analysis = self.videos.get_analysis_result(video_id)
          if (not isinstance(analysis, dict) or analysis.get("video_id") != video_id
              or not isinstance(analysis.get("result_json"), dict)
              or analysis.get("id") != member["analysis_id"]
              or analysis.get("model_version") != member["analysis_model_version"]):
            raise HTTPException(
              status_code=status.HTTP_409_CONFLICT,
              detail="A selected Saved Lift analysis is no longer available for export.",
            )
          artifact = ensure_analyzed_video_artifact(
            video=video,
            analysis=analysis,
            user_id=user_id,
            storage=self.video_storage,
            pose=member["variant"] in {"pose", "pose-barbell"},
            barbell=member["variant"] in {"barbell", "pose-barbell"},
          )
          del analysis
          artifact_file = self.video_storage.download_to_tempfile(artifact.storage_path)
          try:
            member_size = artifact_file.stat().st_size
            if member_size <= 0:
              raise unavailable()
            members.append({**member, "artifact_bucket": self.video_storage.bucket,
                            "artifact_path": artifact.storage_path, "artifact_size_bytes": member_size,
                            "artifact_sha256": file_sha256(artifact_file)})
            archive.write(artifact_file, arcname=member["entry_name"])
          finally:
            self.video_storage.remove_tempfile(artifact_file)

          if archive_file.stat().st_size > self.settings.max_saved_lift_export_bytes:
            raise HTTPException(
              status_code=status.HTTP_413_CONTENT_TOO_LARGE,
              detail="The selected Saved Lifts exceed the export bundle size limit.",
            )

      if archive_file.stat().st_size > self.settings.max_saved_lift_export_bytes:
        raise HTTPException(
          status_code=status.HTTP_413_CONTENT_TOO_LARGE,
          detail="The selected Saved Lifts exceed the export bundle size limit.",
        )

      attempt_id = str(uuid4())
      uploaded_archive_path = f"{user_id}/{job_id}-{attempt_id}.zip"
      path = write_archive(plan=plan, members=members, attempt_id=attempt_id,
                           output_path=archive_file, storage=self.archive_storage, settings=self.settings)
      completed = self.jobs.require_owned(job_id, user_id)
      if (path != uploaded_archive_path or not isinstance(completed, dict)
          or completed.get("id") != job_id or completed.get("user_id") != user_id
          or completed.get("status") != "completed" or completed.get("archive_path") != path):
        raise unavailable()
    except Exception as error:
      logger.exception("Saved Lift export job failed job_id=%s user_id=%s", job_id, user_id)
      if uploaded_archive_path:
        try:
          current = self.jobs.require_owned(job_id, user_id)
          if (isinstance(current, dict) and current.get("id") == job_id
              and current.get("user_id") == user_id):
            if current.get("status") == "completed" and current.get("archive_path") == uploaded_archive_path:
              # A lost completion response must not delete the committed artifact.
              return
        except Exception:
          logger.exception("Unable to confirm archive publication job_id=%s; preserving uploaded bytes", job_id)
      try:
        self.jobs.mark_failed(job_id, user_id, self._failure_code(error))
      except Exception:
        logger.exception("Unable to mark Saved Lift export failed job_id=%s", job_id)
    finally:
      if archive_file:
        self.archive_storage.remove_tempfile(archive_file)

  def cleanup_expired_archives(
    self,
    *,
    dry_run: bool,
    now: datetime | None = None,
  ) -> SavedLiftExportCleanupResult:
    cleanup_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors: list[str] = []
    deleted = 0
    bytes_reclaimable = 0
    try:
      jobs = self.jobs.list_expired(cleanup_now.isoformat())
    except Exception as error:
      message = f"Unable to list expired Saved Lift exports: {error}"
      logger.warning(message)
      return SavedLiftExportCleanupResult(errors=(message,))

    for job in jobs:
      archive_path = job.get("archive_path")
      user_id = str(job.get("user_id") or "")

      try:
        owned_path = require_user_storage_path(archive_path, user_id, "archive_path")
        try:
          bytes_reclaimable += self.archive_storage.storage_object_size_bytes(
            self.archive_storage.get_object_info(owned_path)
          )
        except Exception:
          pass

        if dry_run:
          continue

        self.archive_storage.delete_storage_path(owned_path)
        self.jobs.mark_expired(str(job["id"]), user_id)
        deleted += 1
      except Exception as error:
        message = f"Unable to expire Saved Lift export {job.get('id')}: {error}"
        logger.warning(message)
        errors.append(message)

    return SavedLiftExportCleanupResult(
      candidates=len(jobs),
      deleted=deleted,
      bytes_reclaimable=bytes_reclaimable,
      errors=tuple(errors),
    )

  def delete_user_archives(self, user_id: str) -> None:
    self.archive_storage.delete_storage_prefix(f"{user_id}/")

  def _load_exportable_lifts(
    self,
    user_id: str,
    selected_ids: list[str],
  ) -> dict[str, dict]:
    videos = self.videos.get_owned_videos(selected_ids, user_id)
    videos_by_id = {str(video["id"]): video for video in videos}

    if set(videos_by_id) != set(selected_ids):
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="One or more Saved Lifts were not found.",
      )

    for video_id in selected_ids:
      video = videos_by_id[video_id]
      if not self.videos.video_is_saved(video) or video.get("discarded_at"):
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT,
          detail="Every selected video must still be a Saved Lift.",
        )
      if video.get("storage_state") == "pruned":
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT,
          detail="One or more selected Saved Lift videos are no longer available for export.",
        )

    analyses_by_video_id = self.videos.get_latest_analysis_results(selected_ids, include_result_json=False)
    if set(analyses_by_video_id) != set(selected_ids):
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="One or more selected Saved Lifts do not have an analysis available for export.",
      )

    return videos_by_id

  def _expire_job(self, job: dict[str, Any]) -> None:
    archive_path = job.get("archive_path")
    user_id = str(job.get("user_id") or "")
    if archive_path:
      owned_path = require_user_storage_path(archive_path, user_id, "archive_path")
      try:
        self.archive_storage.delete_storage_path(owned_path)
      except Exception:
        logger.warning("Unable to remove expired Saved Lift archive path=%s", owned_path)
    self.jobs.mark_expired(str(job["id"]), user_id)

  @staticmethod
  def _failure_code(error: Exception) -> str:
    if str(getattr(error, "code", "")) in {"55P03", "40P01", "40001"}:
      return "capacity_unavailable"
    if isinstance(error, HTTPException):
      if error.status_code == status.HTTP_413_CONTENT_TOO_LARGE:
        return "archive_too_large"
      if error.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return "capacity_unavailable"
      if error.status_code in {status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT}:
        return "lift_unavailable"
    return "generation_failed"
