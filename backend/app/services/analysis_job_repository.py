from __future__ import annotations

from typing import Any

from .supabase_client import get_supabase_admin_client


ANALYSIS_JOB_COLUMNS = (
  "id,video_id,status,attempt_count,max_attempts,available_at,lease_owner,"
  "lease_expires_at,last_error,created_at,updated_at,completed_at,stage,"
  "stage_started_at,stage_timestamps,last_heartbeat_at,failure_class"
)


class AnalysisJobRepository:
  """Service-role access to the durable video analysis queue."""

  def __init__(self) -> None:
    self.client = get_supabase_admin_client()

  def enqueue(self, video_id: str, *, allow_completed: bool = False) -> dict[str, Any]:
    response = self.client.rpc(
      "enqueue_video_analysis_job",
      {
        "p_video_id": video_id,
        "p_allow_completed": allow_completed,
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
    return self._first_row(response.data)

  def renew(self, job_id: str, worker_id: str, *, lease_seconds: int) -> bool:
    response = self.client.rpc(
      "renew_video_analysis_job_lease",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_lease_seconds": lease_seconds,
      },
    ).execute()
    return bool(self._scalar(response.data))

  def complete(self, job_id: str, worker_id: str) -> bool:
    response = self.client.rpc(
      "complete_video_analysis_job",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
      },
    ).execute()
    return bool(self._scalar(response.data))

  def progress(self, job_id: str, worker_id: str, stage: str) -> bool:
    response = self.client.rpc(
      "report_video_analysis_job_progress",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_stage": stage,
      },
    ).execute()
    return bool(self._scalar(response.data))

  def fail(
    self,
    job_id: str,
    worker_id: str,
    error: str,
    *,
    failure_class: str,
    retryable: bool,
  ) -> str | None:
    response = self.client.rpc(
      "record_video_analysis_job_failure",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_error": error,
        "p_failure_class": failure_class,
        "p_retryable": retryable,
      },
    ).execute()
    value = self._scalar(response.data)
    return str(value) if value is not None else None

  def recover_expired(self) -> dict[str, int]:
    response = self.client.rpc("recover_expired_video_analysis_jobs", {}).execute()
    row = self._first_row(response.data) or {}
    return {
      "retried_count": int(row.get("retried_count") or 0),
      "failed_count": int(row.get("failed_count") or 0),
    }

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
