from __future__ import annotations

from datetime import datetime, timezone
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
    response = (
      self.client.table("saved_lift_export_jobs")
      .insert(
        {
          "user_id": user_id,
          "video_ids": video_ids,
          "status": "queued",
        }
      )
      .execute()
    )

    if not response.data:
      raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to create Saved Lift export.",
      )

    return response.data[0]

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

  def mark_processing(self, job_id: str) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).isoformat()
    response = (
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
      .eq("status", "queued")
      .execute()
    )
    return response.data[0] if response.data else None

  def mark_completed(
    self,
    job_id: str,
    *,
    archive_path: str,
    completed_at: str,
    expires_at: str,
  ) -> dict[str, Any]:
    return self._update(
      job_id,
      {
        "status": "completed",
        "archive_path": archive_path,
        "failure_code": None,
        "completed_at": completed_at,
        "expires_at": expires_at,
      },
    )

  def mark_failed(self, job_id: str, failure_code: str) -> dict[str, Any]:
    return self._update(
      job_id,
      {
        "status": "failed",
        "archive_path": None,
        "failure_code": failure_code,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
      },
    )

  def mark_expired(self, job_id: str) -> dict[str, Any]:
    return self._update(
      job_id,
      {
        "status": "expired",
        "archive_path": None,
      },
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

  def _update(self, job_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    response = (
      self.client.table("saved_lift_export_jobs")
      .update(fields)
      .eq("id", job_id)
      .execute()
    )

    if not response.data:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved Lift export not found.")

    return response.data[0]
