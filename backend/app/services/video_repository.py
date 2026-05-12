from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from .supabase_client import get_supabase_admin_client


class VideoRepository:
  def __init__(self) -> None:
    self.client = get_supabase_admin_client()

  def get_video(self, video_id: str) -> dict[str, Any] | None:
    response = (
      self.client.table("videos")
      .select("*")
      .eq("id", video_id)
      .limit(1)
      .execute()
    )
    return response.data[0] if response.data else None

  def require_owned_video(self, video_id: str, user_id: str) -> dict[str, Any]:
    video = self.get_video(video_id)

    if not video:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    if video["user_id"] != user_id:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Video does not belong to this user.")

    return video

  def update_video(self, video_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    response = (
      self.client.table("videos")
      .update(fields)
      .eq("id", video_id)
      .execute()
    )

    if not response.data:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    return response.data[0]

  def mark_saved(self, video_id: str) -> dict[str, Any]:
    return self.update_video(
      video_id,
      {
        "is_saved": True,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "discarded_at": None,
      },
    )

  def delete_video(self, video_id: str) -> None:
    self.client.table("videos").delete().eq("id", video_id).execute()

  def save_analysis_result(self, video_id: str, model_version: str, result_json: dict[str, Any]) -> dict[str, Any]:
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
    response = (
      self.client.table("analysis_results")
      .select("*")
      .eq("video_id", video_id)
      .order("created_at", desc=True)
      .limit(1)
      .execute()
    )
    return response.data[0] if response.data else None
