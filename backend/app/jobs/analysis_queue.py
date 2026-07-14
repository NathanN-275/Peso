from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from postgrest.exceptions import APIError

from ..services.supabase_client import get_supabase_admin_client


class AnalysisJobsMigrationRequired(RuntimeError):
  """The deployed Supabase project does not yet contain the durable-job RPCs."""


@dataclass(frozen=True)
class AnalysisJob:
  id: str
  video_id: str
  status: str
  attempt_count: int

  @classmethod
  def from_record(cls, record: dict[str, Any]) -> "AnalysisJob":
    return cls(
      id=str(record["id"]),
      video_id=str(record["video_id"]),
      status=str(record["status"]),
      attempt_count=int(record["attempt_count"]),
    )


class AnalysisJobQueue:
  """Durable backend-only queue for video analysis work.

  Its small interface hides Postgres RPC details, job leases, retry state, and
  the atomic video-status updates needed by API routes and worker processes.
  """

  def __init__(self) -> None:
    self.client = get_supabase_admin_client()

  def enqueue(self, video_id: str, *, reanalyze: bool = False) -> AnalysisJob:
    response = self.client.rpc(
      "enqueue_video_analysis_job",
      {
        "p_video_id": video_id,
        "p_allow_completed": reanalyze,
      },
    ).execute()
    return AnalysisJob.from_record(self._require_single_row(response.data, "enqueue"))

  def claim(self, worker_id: str, lease_seconds: int) -> AnalysisJob | None:
    response = self.client.rpc(
      "claim_video_analysis_job",
      {
        "p_worker_id": worker_id,
        "p_lease_seconds": lease_seconds,
      },
    ).execute()
    rows = response.data or []
    return AnalysisJob.from_record(rows[0]) if rows else None

  def renew(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
    response = self.client.rpc(
      "renew_video_analysis_job_lease",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_lease_seconds": lease_seconds,
      },
    ).execute()
    return bool(response.data)

  def complete(self, job_id: str, worker_id: str) -> bool:
    response = self.client.rpc(
      "complete_video_analysis_job",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
      },
    ).execute()
    return bool(response.data)

  def fail(self, job_id: str, worker_id: str, error: str) -> str | None:
    response = self.client.rpc(
      "fail_video_analysis_job",
      {
        "p_job_id": job_id,
        "p_worker_id": worker_id,
        "p_error": error[:2000],
      },
    ).execute()
    return str(response.data) if response.data else None

  def recover_expired(self) -> None:
    try:
      self.client.rpc("recover_expired_video_analysis_jobs").execute()
    except APIError as error:
      if self._is_missing_analysis_jobs_function(error):
        raise AnalysisJobsMigrationRequired(
          "The connected Supabase project is missing the durable analysis-jobs schema. "
          "Apply supabase/migrations/20260713233319_durable_analysis_jobs.sql to this project, "
          "then restart the analysis worker."
        ) from error
      raise

  def cancel_for_video(self, video_id: str) -> int:
    response = self.client.rpc(
      "cancel_video_analysis_jobs",
      {"p_video_id": video_id},
    ).execute()
    return int(response.data or 0)

  @staticmethod
  def _require_single_row(data: Any, operation: str) -> dict[str, Any]:
    rows = data or []

    if not rows:
      raise RuntimeError(f"Analysis job {operation} returned no job row.")

    return rows[0]

  @staticmethod
  def _is_missing_analysis_jobs_function(error: APIError) -> bool:
    message = str(getattr(error, "message", "") or error).lower()
    return (
      getattr(error, "code", "") == "PGRST202"
      and "recover_expired_video_analysis_jobs" in message
    )
