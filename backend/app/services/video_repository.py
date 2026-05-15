from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from .supabase_client import get_supabase_admin_client


class VideoRepository:
  def __init__(self) -> None:
    # All video persistence goes through the Supabase admin client.
    self.client = get_supabase_admin_client()

  def get_video(self, video_id: str) -> dict[str, Any] | None:
    # Load one uploaded video row by ID.
    response = (
      self.client.table("videos")
      .select("*")
      .eq("id", video_id)
      .limit(1)
      .execute()
    )
    return response.data[0] if response.data else None

  def require_owned_video(self, video_id: str, user_id: str) -> dict[str, Any]:
    # Ownership checks keep user data isolated.
    video = self.get_video(video_id)

    if not video:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    if video["user_id"] != user_id:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Video does not belong to this user.")

    return video

  def update_video(self, video_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    # Update any video metadata in place.
    response = (
      self.client.table("videos")
      .update(fields)
      .eq("id", video_id)
      .execute()
    )

    if not response.data:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    return response.data[0]

  def queue_owned_video_if_status(
    self,
    video_id: str,
    user_id: str,
    allowed_statuses: tuple[str, ...],
  ) -> dict[str, Any] | None:
    # Only queue videos that are still in a queueable state.
    response = (
      self.client.table("videos")
      .update({"status": "queued"})
      .eq("id", video_id)
      .eq("user_id", user_id)
      .in_("status", list(allowed_statuses))
      .execute()
    )

    return response.data[0] if response.data else None

  def mark_saved(self, video_id: str) -> dict[str, Any]:
    # Saved videos stay visible in the home flow.
    return self.update_video(
      video_id,
      {
        "save_state": "saved",
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
      },
    )

  def delete_video(self, video_id: str) -> None:
    # Deleted videos are removed entirely from the table.
    self.client.table("videos").delete().eq("id", video_id).execute()

  def delete_video_with_analysis(self, video_id: str) -> None:
    # Keep deletion safe for environments where the analysis FK cascade is not present yet.
    self.client.table("analysis_results").delete().eq("video_id", video_id).execute()
    self.delete_video(video_id)

  def list_expired_pending_videos(self) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    response = (
      self.client.table("videos")
      .select("*")
      .eq("save_state", "pending")
      .lt("expires_at", now)
      .execute()
    )
    return response.data or []

  def list_saved_videos(self, user_id: str) -> list[dict[str, Any]]:
    response = (
      self.client.table("videos")
      .select("*")
      .eq("user_id", user_id)
      .eq("save_state", "saved")
      .order("saved_at", desc=True, nullsfirst=False)
      .order("created_at", desc=True)
      .execute()
    )
    return response.data or []

  def save_analysis_result(self, video_id: str, model_version: str, result_json: dict[str, Any]) -> dict[str, Any]:
    # Store the latest analysis result for this model version.
    response = (
      self.client.table("analysis_results")
      .upsert(
        {
          "video_id": video_id,
          "model_version": model_version,
          "result_json": result_json,
        },
        on_conflict="video_id,model_version",
      )
      .execute()
    )
    return response.data[0]

  def get_analysis_result(self, video_id: str) -> dict[str, Any] | None:
    # Return the newest analysis result for review.
    response = (
      self.client.table("analysis_results")
      .select("*")
      .eq("video_id", video_id)
      .order("created_at", desc=True)
      .limit(1)
      .execute()
    )
    return response.data[0] if response.data else None
