from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from .supabase_client import get_supabase_admin_client


class UploadReservationRepository:
  def __init__(self) -> None:
    self.client = get_supabase_admin_client()

  def reserve(self, fields: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]:
    response = self.client.rpc(
      "reserve_video_upload",
      {
        "p_reservation_id": fields["id"],
        "p_user_id": fields["user_id"],
        "p_blob_path": fields["blob_path"],
        "p_file_name": fields["file_name"],
        "p_content_type": fields["content_type"],
        "p_requested_bytes": fields["requested_bytes"],
        "p_expires_at": fields["expires_at"],
        "p_source_type": fields["source_type"],
        "p_exercise_type": fields["exercise_type"],
        "p_view_type": fields["view_type"],
        "p_client_duration_ms": fields.get("client_duration_ms"),
        "p_tracking_setup": fields.get("tracking_setup"),
        "p_max_user_active": limits["max_user_active"],
        "p_max_user_bytes": limits["max_user_bytes"],
        "p_max_global_active": limits["max_global_active"],
        "p_max_global_bytes": limits["max_global_bytes"],
        "p_max_user_hourly": limits["max_user_hourly"],
      },
    ).execute()
    return self._require_row(response.data, "Unable to reserve upload capacity.")

  def require_owned(self, reservation_id: str, user_id: str) -> dict[str, Any]:
    response = (
      self.client.table("upload_reservations")
      .select("*")
      .eq("id", reservation_id)
      .eq("user_id", user_id)
      .limit(1)
      .execute()
    )
    row = self._first_row(response.data)
    if not row:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload reservation not found.")
    return row

  def mark_uploaded(self, reservation_id: str, user_id: str, validation_owner: str) -> dict[str, Any]:
    response = self.client.rpc(
      "mark_video_upload_received",
      {"p_reservation_id": reservation_id, "p_user_id": user_id, "p_validation_owner": validation_owner},
    ).execute()
    row = self._first_row(response.data)
    if not row:
      raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload verification is already running or expired.")
    return row

  def verify_and_create_video(
    self,
    reservation_id: str,
    user_id: str,
    *,
    actual_bytes: int,
    metadata: dict[str, Any],
    video_expires_at: datetime,
    validation_owner: str,
  ) -> dict[str, Any]:
    response = self.client.rpc(
      "verify_video_upload",
      {
        "p_reservation_id": reservation_id,
        "p_user_id": user_id,
        "p_actual_bytes": actual_bytes,
        "p_media_metadata": metadata,
        "p_video_expires_at": video_expires_at.isoformat(),
        "p_validation_owner": validation_owner,
      },
    ).execute()
    return self._require_row(response.data, "Unable to verify uploaded video.")

  def reject(self, reservation_id: str, user_id: str, reason: str) -> None:
    self.client.rpc(
      "reject_video_upload",
      {"p_reservation_id": reservation_id, "p_user_id": user_id, "p_reason": reason},
    ).execute()

  def expire_due(self, *, limit: int = 100) -> list[dict[str, Any]]:
    response = self.client.rpc("expire_video_upload_reservations", {"p_limit": limit}).execute()
    return response.data if isinstance(response.data, list) else []

  def mark_blob_deleted(self, blob_path: str, *, confirmed_after_expiry: bool = False) -> None:
    from datetime import timezone

    timestamp = datetime.now(timezone.utc).isoformat()
    fields = {"blob_deleted_at": timestamp}
    if confirmed_after_expiry:
      fields["cleanup_confirmed_at"] = timestamp
    self.client.table("upload_reservations").update(fields).eq("blob_path", blob_path).execute()

  def purge_cleaned_tombstones(self) -> None:
    from datetime import timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    (
      self.client.table("upload_reservations").delete()
      .filter("video_id", "is", "null")
      .lt("cleanup_confirmed_at", cutoff)
      .execute()
    )

  @staticmethod
  def _first_row(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
      return data[0] if data and isinstance(data[0], dict) else None
    return data if isinstance(data, dict) else None

  @classmethod
  def _require_row(cls, data: Any, message: str) -> dict[str, Any]:
    row = cls._first_row(data)
    if not row:
      raise RuntimeError(message)
    return row
