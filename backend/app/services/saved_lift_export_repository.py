from __future__ import annotations

from datetime import datetime, timezone
import time
from uuid import UUID
from typing import Any

from fastapi import HTTPException, status

from .supabase_client import get_supabase_admin_client


SAVED_LIFT_EXPORT_JOB_COLUMNS = (
  "id,user_id,video_ids,status,archive_path,failure_code,attempts,created_at,updated_at,"
  "started_at,completed_at,expires_at"
)


class SavedLiftExportRepository:
  def __init__(self) -> None:
    self.client = get_supabase_admin_client()

  def create(self, user_id: str, video_ids: list[str]) -> dict[str, Any]:
    response = self._execute_transition(
      self.client.table("saved_lift_export_jobs")
      .insert(
        {
          "user_id": user_id,
          "video_ids": video_ids,
          "status": "queued",
        }
      )
    )
    row = self._transition_row(response.data, status="queued", user_id=user_id)
    if not row:
      raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to create Saved Lift export.",
      )

    if row.get("video_ids") != video_ids:
      raise RuntimeError("Unexpected Saved Lift export admission response.")
    return row

  def get_owned(self, job_id: str, user_id: str) -> dict[str, Any] | None:
    response = (
      self.client.table("saved_lift_export_jobs")
      .select(SAVED_LIFT_EXPORT_JOB_COLUMNS)
      .eq("id", job_id)
      .eq("user_id", user_id)
      .limit(1)
      .execute()
    )
    return response.data[0] if response.data else None

  def require_owned(self, job_id: str, user_id: str) -> dict[str, Any]:
    job = self.get_owned(job_id, user_id)

    if not job:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved Lift export not found.")

    return job

  def mark_processing(self, job_id: str, user_id: str) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).isoformat()
    response = self._execute_transition(
      self.client.table("saved_lift_export_jobs")
      .update(
        {
          "status": "processing",
          "started_at": now,
          "attempts": 1,
          "failure_code": None,
        }
      )
      .eq("id", job_id)
      .eq("user_id", user_id)
      .eq("status", "queued")
    )
    return self._transition_row(response.data, job_id=job_id, user_id=user_id, status="processing")

  def mark_completed(
    self,
    job_id: str,
    user_id: str,
    *,
    archive_path: str,
    completed_at: str,
    expires_at: str,
  ) -> dict[str, Any] | None:
    return self._update(
      job_id,
      user_id,
      {
        "status": "completed",
        "archive_path": archive_path,
        "failure_code": None,
        "completed_at": completed_at,
        "expires_at": expires_at,
      },
      from_statuses=["processing"],
    )

  def mark_failed(self, job_id: str, user_id: str, failure_code: str) -> dict[str, Any] | None:
    return self._update(
      job_id,
      user_id,
      {
        "status": "failed",
        "archive_path": None,
        "failure_code": failure_code,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
      },
      from_statuses=(["completed"] if failure_code == "archive_missing" else ["queued", "processing"]),
    )

  def mark_expired(self, job_id: str, user_id: str) -> dict[str, Any] | None:
    return self._update(
      job_id,
      user_id,
      {
        "status": "expired",
        "archive_path": None,
      },
      from_statuses=["queued", "processing", "completed", "failed"],
    )

  def list_expired(self, cutoff_iso: str) -> list[dict[str, Any]]:
    response = (
      self.client.table("saved_lift_export_jobs")
      .select(SAVED_LIFT_EXPORT_JOB_COLUMNS)
      .eq("status", "completed")
      .lt("expires_at", cutoff_iso)
      .execute()
    )
    return response.data or []

  def _update(
    self, job_id: str, user_id: str, fields: dict[str, Any], *, from_statuses: list[str],
  ) -> dict[str, Any] | None:
    response = self._execute_transition(
      self.client.table("saved_lift_export_jobs")
      .update(fields)
      .eq("id", job_id)
      .eq("user_id", user_id)
      .in_("status", from_statuses)
    )
    row = self._transition_row(response.data, job_id=job_id, user_id=user_id, status=fields["status"])
    if row and fields["status"] == "completed" and row.get("archive_path") != fields["archive_path"]:
      raise RuntimeError("Unexpected Saved Lift export artifact response.")
    return row

  @staticmethod
  def _execute_transition(query: Any) -> Any:
    for attempt in range(3):
      try:
        return query.execute()
      except Exception as error:
        # These SQL errors guarantee rollback; transport uncertainty cannot be retried here.
        if str(getattr(error, "code", "")) not in {"55P03", "40P01", "40001"} or attempt == 2:
          raise
        time.sleep(0.1 * (2 ** attempt))
    raise RuntimeError("Archive transition retry loop exited unexpectedly.")

  @staticmethod
  def _transition_row(data: Any, *, status: str, user_id: str, job_id: str | None = None) -> dict[str, Any] | None:
    if data is None or data == []:
      return None
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
      raise RuntimeError("Unexpected Saved Lift export transition response.")
    row = data[0]
    identity = row.get("id")
    try:
      valid_id = isinstance(identity, str) and str(UUID(identity)) == identity and UUID(identity).int != 0
    except ValueError:
      valid_id = False
    if not valid_id or (job_id is not None and identity != job_id) or row.get("status") != status or row.get("user_id") != user_id:
      raise RuntimeError("Unexpected Saved Lift export transition identity or state.")
    return row
