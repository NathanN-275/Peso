from __future__ import annotations

from typing import Any
from uuid import UUID

from .supabase_client import get_supabase_admin_client
from .config import get_settings
from .security_logging import redact_sensitive_text


ANALYSIS_JOB_COLUMNS = (
  "id,video_id,status,attempt_count,max_attempts,available_at,lease_owner,"
  "lease_expires_at,last_error,created_at,updated_at,completed_at,stage,"
  "stage_started_at,stage_timestamps,last_heartbeat_at,failure_class"
)


class AnalysisJobRepository:
  """Service-role access to the durable video analysis queue."""

  def __init__(self) -> None:
    self.client = get_supabase_admin_client()

  def check_readiness(self) -> None:
    """Fail when the deployed queue schema is older than this API contract."""
    self.client.table("video_deletion_outbox").select("video_id,user_id,storage_paths,archive_paths,export_prefixes,delete_metadata").limit(1).execute()
    self.client.table("saved_lift_deletion_receipts").select("video_id,user_id,created_at,completed_at").limit(1).execute()
    (
      self.client.table("analysis_jobs")
      .select(ANALYSIS_JOB_COLUMNS)
      .limit(1)
      .execute()
    )
    if get_settings().upload_reservations_enabled:
      self.client.table("upload_reservations").select("id,state,validation_owner,cleanup_confirmed_at").limit(1).execute()
      self.client.table("upload_admission_control").select("id,enabled").eq("id", 1).single().execute()

  def enqueue(self, video_id: str, *, allow_completed: bool = False) -> dict[str, Any]:
    settings = get_settings()
    response = self.client.rpc(
      "enqueue_video_analysis_job",
      {
        "p_video_id": video_id,
        "p_allow_completed": allow_completed,
        "p_max_user_jobs": settings.max_user_in_progress_videos,
        "p_max_global_jobs": settings.max_global_active_upload_reservations,
      },
    ).execute()
    return self._require_row(response.data, "Unable to enqueue video analysis.")

  def claim(self, worker_id: str, *, lease_seconds: int) -> dict[str, Any] | None:
    response = self.client.rpc(
      "claim_video_analysis_job",
      {
        "p_worker_id": worker_id,
        "p_lease_seconds": lease_seconds,
      },
    ).execute()
    if response.data is None or response.data == []:
      return None
    if isinstance(response.data, list) and len(response.data) != 1:
      raise RuntimeError("Invalid claimed analysis attempt.")
    return self.validate_claim(self._first_row(response.data))

  @staticmethod
  def validate_claim(row: Any) -> dict[str, Any]:
    try:
      if not isinstance(row, dict) or row.get("status") != "processing":
        raise ValueError()
      for field in ("id", "video_id"):
        value = row[field]
        if not isinstance(value, str) or str(UUID(value)) != value or UUID(value).int == 0:
          raise ValueError()
      if type(row.get("attempt_count")) is not int or row["attempt_count"] < 1:
        raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError) as error:
      raise RuntimeError("Invalid claimed analysis attempt.") from error
    return row

  @staticmethod
  def _lease_scalar(data: Any, rpc_name: str) -> Any:
    if isinstance(data, list):
      if len(data) != 1:
        raise RuntimeError("Invalid analysis lease response.")
      data = data[0]
    if isinstance(data, dict):
      if set(data) != {rpc_name}:
        raise RuntimeError("Invalid analysis lease response.")
      data = data[rpc_name]
    return data

  @classmethod
  def _boolean(cls, data: Any, rpc_name: str) -> bool:
    value = cls._lease_scalar(data, rpc_name)
    if type(value) is not bool:
      raise RuntimeError("Invalid analysis lease response.")
    return value

  def renew(self, job_id: str, worker_id: str, *, attempt_count: int, lease_seconds: int) -> bool:
    response = self.client.rpc(
      "renew_video_analysis_job_lease",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_attempt_count": attempt_count,
        "p_lease_seconds": lease_seconds,
      },
    ).execute()
    return self._boolean(response.data, "renew_video_analysis_job_lease")

  def complete(self, job_id: str, worker_id: str, *, attempt_count: int) -> bool:
    response = self.client.rpc(
      "complete_video_analysis_job",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_attempt_count": attempt_count,
      },
    ).execute()
    return self._boolean(response.data, "complete_video_analysis_job")

  def progress(self, job_id: str, worker_id: str, stage: str, *, attempt_count: int) -> bool:
    response = self.client.rpc(
      "report_video_analysis_job_progress",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_attempt_count": attempt_count,
        "p_stage": stage,
      },
    ).execute()
    return self._boolean(response.data, "report_video_analysis_job_progress")

  def fail(
    self,
    job_id: str,
    worker_id: str,
    error: str,
    *,
    attempt_count: int,
    failure_class: str,
    retryable: bool,
  ) -> str | None:
    response = self.client.rpc(
      "record_video_analysis_job_failure",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_attempt_count": attempt_count,
        "p_error": redact_sensitive_text(error),
        "p_failure_class": failure_class,
        "p_retryable": retryable,
      },
    ).execute()
    value = self._lease_scalar(response.data, "record_video_analysis_job_failure")
    if value is not None and (not isinstance(value, str) or value not in {"failed", "retry_wait"}):
      raise RuntimeError("Invalid analysis failure response.")
    return value

  def recover_expired(self) -> dict[str, int]:
    response = self.client.rpc("recover_expired_video_analysis_jobs", {}).execute()
    row = self._first_row(response.data) or {}
    return {
      "retried_count": int(row.get("retried_count") or 0),
      "failed_count": int(row.get("failed_count") or 0),
    }

  def cancel_for_video(self, video_id: str) -> int:
    response = self.client.rpc(
      "cancel_video_analysis_jobs",
      {"p_video_id": video_id},
    ).execute()
    value = self._scalar(response.data)
    return int(value) if isinstance(value, (int, float)) else 0

  def latest_for_videos(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
      return {}

    response = (
      self.client.table("analysis_jobs")
      .select(ANALYSIS_JOB_COLUMNS)
      .in_("video_id", video_ids)
      .order("created_at", desc=True)
      .execute()
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in response.data or []:
      video_id = str(row.get("video_id") or "")
      if video_id and video_id not in latest:
        latest[video_id] = row
    return latest

  def video_duration_ms(self, video_id: str) -> int | None:
    response = (
      self.client.table("videos")
      .select("duration_ms")
      .eq("id", video_id)
      .maybe_single()
      .execute()
    )
    row = response.data if isinstance(response.data, dict) else None
    value = row.get("duration_ms") if row else None
    return int(value) if isinstance(value, (int, float)) and value > 0 else None

  @staticmethod
  def _first_row(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
      return data[0] if data and isinstance(data[0], dict) else None
    if isinstance(data, dict):
      return data
    return None

  @classmethod
  def _require_row(cls, data: Any, message: str) -> dict[str, Any]:
    row = cls._first_row(data)
    if not row:
      raise RuntimeError(message)
    return row

  @staticmethod
  def _scalar(data: Any) -> Any:
    if isinstance(data, list):
      if not data:
        return None
      value = data[0]
      if isinstance(value, dict) and len(value) == 1:
        return next(iter(value.values()))
      return value
    if isinstance(data, dict) and len(data) == 1:
      return next(iter(data.values()))
    return data
