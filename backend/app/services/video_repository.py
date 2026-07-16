from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status

from .supabase_client import get_supabase_admin_client
from .video_storage_paths import VIDEO_STORAGE_PATH_FIELDS, require_user_storage_path


logger = logging.getLogger(__name__)
VIDEO_BASE_COLUMNS = (
  "id,user_id,storage_path,source_type,exercise_type,view_type,status,duration_ms,"
  "save_state,saved_at,expires_at,weight,weight_unit,corrected_rep_count,user_notes,created_at,updated_at"
)
VIDEO_STORAGE_COLUMNS_WITHOUT_TRACKING = (
  f"{VIDEO_BASE_COLUMNS},is_saved,discarded_at,thumbnail_path,playback_path,original_storage_path,"
  "storage_optimized_at,storage_optimization_error"
)
VIDEO_STORAGE_COLUMNS = f"{VIDEO_STORAGE_COLUMNS_WITHOUT_TRACKING},tracking_setup"
ANALYSIS_RESULT_COLUMNS = "id,video_id,model_version,result_json,created_at"
ANALYSIS_RESULT_SAVE_MAX_ATTEMPTS = 3
ANALYSIS_RESULT_SAVE_RETRY_BACKOFF_SECONDS = 0.5


class VideoRepository:
  def __init__(self) -> None:
    # All video persistence goes through the Supabase admin client.
    self.client = get_supabase_admin_client()

  def get_video(self, video_id: str) -> dict[str, Any] | None:
    # Load one uploaded video row by ID.
    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("id", video_id)
        .limit(1)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to video query without tracking setup for video %s: %s", video_id, error)
      try:
        response = (
          self.client.table("videos")
          .select(VIDEO_STORAGE_COLUMNS_WITHOUT_TRACKING)
          .eq("id", video_id)
          .limit(1)
          .execute()
        )
      except Exception as legacy_error:
        logger.warning("Falling back to legacy video query for video %s: %s", video_id, legacy_error)
        response = (
          self.client.table("videos")
          .select(VIDEO_BASE_COLUMNS)
          .eq("id", video_id)
          .limit(1)
          .execute()
        )

    return response.data[0] if response.data else None

  def supports_tracking_setup(self) -> bool:
    # Selecting the nullable column verifies PostgREST schema support without mutating data.
    try:
      (
        self.client.table("videos")
        .select("tracking_setup")
        .limit(1)
        .execute()
      )
      return True
    except Exception as error:
      error_code = str(getattr(error, "code", "") or "")
      error_message = str(error).lower()
      missing_tracking_column = (
        error_code == "42703"
        or (
          "tracking_setup" in error_message
          and ("does not exist" in error_message or "could not find" in error_message)
        )
      )

      if missing_tracking_column:
        return False

      raise

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
    self._validate_storage_path_update(video_id, fields)
    response = (
      self.client.table("videos")
      .update(fields)
      .eq("id", video_id)
      .execute()
    )

    if not response.data:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    return response.data[0]

  def create_video(self, fields: dict[str, Any]) -> dict[str, Any]:
    response = self.client.table("videos").insert(fields).execute()

    if not response.data:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to create video.")

    return response.data[0]

  def create_uploaded_video(self, fields: dict[str, Any]) -> dict[str, Any]:
    try:
      return self.create_video(fields)
    except Exception as error:
      missing_storage_metadata = self._error_mentions_missing_columns(
        error,
        {
          "storage_state",
          "original_size_bytes",
          "uploaded_size_bytes",
          "was_compressed",
        },
      )

      if not missing_storage_metadata:
        raise

      logger.warning("Falling back to upload insert without storage metadata: %s", error)
      legacy_fields = {
        key: value
        for key, value in fields.items()
        if key not in {"storage_state", "original_size_bytes", "uploaded_size_bytes", "was_compressed"}
      }
      return self.create_video(legacy_fields)

  def count_user_in_progress_videos(self, user_id: str) -> int:
    response = (
      self.client.table("videos")
      .select("id", count="exact")
      .eq("user_id", user_id)
      .in_("status", ["queued", "processing"])
      .execute()
    )
    return int(response.count or 0)

  def count_recent_user_uploads(self, user_id: str, since_iso: str) -> int:
    response = (
      self.client.table("videos")
      .select("id", count="exact")
      .eq("user_id", user_id)
      .gte("created_at", since_iso)
      .execute()
    )
    return int(response.count or 0)

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

  def mark_saved(self, video_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    # Saved videos stay visible in the home flow.
    saved_at = datetime.now(timezone.utc).isoformat()
    fields = {
      "save_state": "saved",
      "is_saved": True,
      "saved_at": saved_at,
      "discarded_at": None,
      "expires_at": None,
    }
    if metadata:
      fields.update(metadata)

    try:
      return self.update_video(video_id, fields)
    except Exception as error:
      logger.warning("Falling back to legacy save metadata for video %s: %s", video_id, error)
      return self.update_video(
        video_id,
        {
          "save_state": "saved",
          "saved_at": saved_at,
          "expires_at": None,
        },
      )

  def mark_discarded(self, video_id: str) -> dict[str, Any]:
    # Discarded rows remain as metadata, but they leave the saved library.
    fields = {
      "save_state": "pending",
      "is_saved": False,
      "discarded_at": datetime.now(timezone.utc).isoformat(),
      "expires_at": None,
    }

    try:
      return self.update_video(video_id, fields)
    except Exception as error:
      logger.warning("Falling back to legacy discard metadata for video %s: %s", video_id, error)
      return self.update_video(
        video_id,
        {
          "save_state": "pending",
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
    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("save_state", "pending")
        .lt("expires_at", now)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to legacy expired-video query: %s", error)
      response = (
        self.client.table("videos")
        .select(VIDEO_BASE_COLUMNS)
        .eq("save_state", "pending")
        .lt("expires_at", now)
        .execute()
      )
    return response.data or []

  def list_stale_pending_in_progress_videos(self, cutoff_iso: str) -> list[dict[str, Any]]:
    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("save_state", "pending")
        .in_("status", ["queued", "processing"])
        .lt("updated_at", cutoff_iso)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to legacy stale-pending query: %s", error)
      response = (
        self.client.table("videos")
        .select(VIDEO_BASE_COLUMNS)
        .eq("save_state", "pending")
        .in_("status", ["queued", "processing"])
        .lt("updated_at", cutoff_iso)
        .execute()
      )
    return response.data or []

  def list_storage_referenced_videos(self) -> list[dict[str, Any]]:
    try:
      response = self.client.table("videos").select(VIDEO_STORAGE_COLUMNS).execute()
    except Exception as error:
      logger.warning("Falling back to legacy referenced-video query: %s", error)
      response = self.client.table("videos").select(VIDEO_BASE_COLUMNS).execute()
    return response.data or []

  def list_storage_cleanup_candidates(self, older_than_days: int = 7) -> list[dict[str, Any]]:
    # The video table is small; filter in Python so mixed schema eras stay safe.
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    try:
      response = self.client.table("videos").select(VIDEO_STORAGE_COLUMNS).execute()
    except Exception as error:
      logger.warning("Falling back to legacy storage cleanup query: %s", error)
      response = self.client.table("videos").select(VIDEO_BASE_COLUMNS).execute()
    candidates: dict[str, dict[str, Any]] = {}

    for video in response.data or []:
      if self.video_is_saved(video):
        continue

      created_at = self._parse_timestamp(video.get("created_at"))
      is_discarded = video.get("discarded_at") is not None
      is_failed = video.get("status") == "failed"
      is_old_pending_status = (
        video.get("status") in {"uploaded", "queued", "pending"}
        and created_at is not None
        and created_at < cutoff
      )

      if is_discarded or is_failed or is_old_pending_status:
        candidates[str(video["id"])] = video

    return list(candidates.values())

  def list_saved_videos(self, user_id: str) -> list[dict[str, Any]]:
    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("user_id", user_id)
        .or_("save_state.eq.saved,is_saved.eq.true")
        .filter("discarded_at", "is", "null")
        .order("saved_at", desc=True, nullsfirst=False)
        .order("created_at", desc=True)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to legacy saved-video query for user %s: %s", user_id, error)
      response = (
        self.client.table("videos")
        .select(VIDEO_BASE_COLUMNS)
        .eq("user_id", user_id)
        .eq("save_state", "saved")
        .order("saved_at", desc=True, nullsfirst=False)
        .order("created_at", desc=True)
        .execute()
      )

    return response.data or []

  def list_saved_videos_page(
    self,
    user_id: str,
    *,
    exercise_type: str | None = None,
    offset: int = 0,
    limit: int = 20,
  ) -> list[dict[str, Any]]:
    offset = max(0, offset)
    limit = max(1, limit)
    range_end = offset + limit - 1

    try:
      query = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("user_id", user_id)
        .or_("save_state.eq.saved,is_saved.eq.true")
        .filter("discarded_at", "is", "null")
      )

      if exercise_type:
        query = query.eq("exercise_type", exercise_type)

      response = (
        query
        .order("saved_at", desc=True, nullsfirst=False)
        .order("created_at", desc=True)
        .range(offset, range_end)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to legacy saved-video page query for user %s: %s", user_id, error)
      query = (
        self.client.table("videos")
        .select(VIDEO_BASE_COLUMNS)
        .eq("user_id", user_id)
        .eq("save_state", "saved")
      )

      if exercise_type:
        query = query.eq("exercise_type", exercise_type)

      response = (
        query
        .order("saved_at", desc=True, nullsfirst=False)
        .order("created_at", desc=True)
        .range(offset, range_end)
        .execute()
      )

    return response.data or []

  def list_user_videos(self, user_id: str) -> list[dict[str, Any]]:
    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("user_id", user_id)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to legacy user-video query for user %s: %s", user_id, error)
      response = (
        self.client.table("videos")
        .select(VIDEO_BASE_COLUMNS)
        .eq("user_id", user_id)
        .execute()
      )

    return response.data or []

  @staticmethod
  def video_is_saved(video: dict[str, Any]) -> bool:
    return video.get("save_state") == "saved" or video.get("is_saved") is True

  def _validate_storage_path_update(self, video_id: str, fields: dict[str, Any]) -> None:
    if not any(field in fields and fields[field] is not None for field in VIDEO_STORAGE_PATH_FIELDS):
      return

    video = self.get_video(video_id)
    if not video:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    user_id = str(video.get("user_id") or "")
    for field in VIDEO_STORAGE_PATH_FIELDS:
      path = fields.get(field)

      if path is not None:
        require_user_storage_path(str(path), user_id, field)

  @staticmethod
  def _error_mentions_missing_columns(error: Exception, columns: set[str]) -> bool:
    error_message = str(error).lower()

    if not ("does not exist" in error_message or "could not find" in error_message):
      return False

    return any(column in error_message for column in columns)

  @staticmethod
  def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
      return None

    normalized_value = value.replace("Z", "+00:00")

    try:
      parsed = datetime.fromisoformat(normalized_value)
    except ValueError:
      return None

    if parsed.tzinfo is None:
      return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)

  def save_analysis_result(self, video_id: str, model_version: str, result_json: dict[str, Any]) -> dict[str, Any]:
    # This upsert can be retried safely: the conflict key preserves one result
    # per video/model pair even when the previous request reached PostgREST
    # before its connection was interrupted.
    for attempt in range(ANALYSIS_RESULT_SAVE_MAX_ATTEMPTS):
      try:
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
      except httpx.TransportError as error:
        if attempt == ANALYSIS_RESULT_SAVE_MAX_ATTEMPTS - 1:
          raise

        retry_delay_seconds = ANALYSIS_RESULT_SAVE_RETRY_BACKOFF_SECONDS * (2 ** attempt)
        logger.warning(
          "Supabase transport error while saving analysis video_id=%s attempt=%s/%s; retrying in %.1fs: %s",
          video_id,
          attempt + 1,
          ANALYSIS_RESULT_SAVE_MAX_ATTEMPTS,
          retry_delay_seconds,
          error,
        )
        time.sleep(retry_delay_seconds)

    raise RuntimeError("Analysis result save retry loop exited unexpectedly.")

  def get_analysis_result(self, video_id: str) -> dict[str, Any] | None:
    # Return the newest analysis result for review.
    response = (
      self.client.table("analysis_results")
      .select(ANALYSIS_RESULT_COLUMNS)
      .eq("video_id", video_id)
      .order("created_at", desc=True)
      .limit(1)
      .execute()
    )
    return response.data[0] if response.data else None

  def get_latest_analysis_results(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
      return {}

    response = (
      self.client.table("analysis_results")
      .select(ANALYSIS_RESULT_COLUMNS)
      .in_("video_id", video_ids)
      .order("created_at", desc=True)
      .execute()
    )
    latest_by_video_id: dict[str, dict[str, Any]] = {}

    for row in response.data or []:
      video_id = str(row.get("video_id") or "")
      if video_id and video_id not in latest_by_video_id:
        latest_by_video_id[video_id] = row

    return latest_by_video_id
