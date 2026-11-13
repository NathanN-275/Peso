from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from .supabase_client import get_supabase_admin_client
from .video_storage_paths import VIDEO_STORAGE_PATH_FIELDS, require_user_storage_path, storage_path_belongs_to_user


logger = logging.getLogger(__name__)
VIDEO_LEGACY_BASE_COLUMNS = (
  "id,user_id,storage_path,source_type,exercise_type,view_type,status,duration_ms,"
  "save_state,saved_at,expires_at,created_at,updated_at"
)
VIDEO_BASE_COLUMNS = (
  f"{VIDEO_LEGACY_BASE_COLUMNS},performed_reps,load_value,load_unit,"
  "weight,weight_unit,corrected_rep_count,user_notes"
)
VIDEO_STORAGE_COLUMNS_WITHOUT_TRACKING = (
  f"{VIDEO_BASE_COLUMNS},is_saved,discarded_at,thumbnail_path,playback_path,original_storage_path,"
  "storage_optimized_at,storage_optimization_error,storage_state,original_size_bytes,"
  "uploaded_size_bytes,was_compressed"
)
VIDEO_STORAGE_COLUMNS = f"{VIDEO_STORAGE_COLUMNS_WITHOUT_TRACKING},tracking_setup"
VIDEO_STORAGE_COLUMNS_WITH_PREFLIGHT = (
  f"{VIDEO_STORAGE_COLUMNS},quality_preflight,quality_preflight_required"
)
ANALYSIS_RESULT_COLUMNS = "id,video_id,model_version,result_json,created_at"
ANALYSIS_RESULT_METADATA_COLUMNS = "id,video_id,model_version,created_at"
ANALYSIS_RESULT_SAVE_MAX_ATTEMPTS = 3
ANALYSIS_RESULT_SAVE_RETRY_BACKOFF_SECONDS = 0.5


def validate_media_deletion_task(task: dict[str, Any]) -> None:
  # Treat database response shape and cleanup paths as a boundary before Storage I/O.
  if not isinstance(task, dict):
    raise ValueError("Unsafe cleanup snapshot")
  video_id, user_id = task["video_id"], task["user_id"]
  for value in (video_id, user_id):
    if not isinstance(value, str) or str(UUID(value)) != value or UUID(value).int == 0:
      raise ValueError("Unsafe cleanup identity")
  paths, archives, prefixes = task["storage_paths"], task["archive_paths"], task["export_prefixes"]
  if (type(task["delete_metadata"]) is not bool
      or not all(isinstance(items, list) for items in (paths, archives, prefixes))
      or any(not storage_path_belongs_to_user(path, user_id) for path in paths + archives)
      or any(prefix != f"{user_id}/exports/{video_id}-" for prefix in prefixes)):
    raise ValueError("Unsafe cleanup snapshot")


class VideoRepository:
  def __init__(self) -> None:
    # All video persistence goes through the Supabase admin client.
    self.client = get_supabase_admin_client()

  def bind_analysis_lease(self, job_id: str, worker_id: str, attempt_count: int) -> None:
    if (not isinstance(job_id, str) or str(UUID(job_id)) != job_id or UUID(job_id).int == 0
        or not isinstance(worker_id, str) or not worker_id or worker_id.strip() != worker_id
        or type(attempt_count) is not int or attempt_count < 1):
      raise ValueError("A claimed analysis attempt is required.")
    self._analysis_lease = {"p_job_id": job_id, "p_worker_id": worker_id, "p_attempt_count": attempt_count}

  def analysis_write_binding(self) -> dict[str, Any]:
    lease = getattr(self, "_analysis_lease", None)
    if lease is None:
      raise RuntimeError("A claimed analysis attempt is required for generated media.")
    return dict(lease)

  def _publish_analysis(self, video_id: str, fields: dict[str, Any], *,
                        model_version: str | None = None, result_json: dict[str, Any] | None = None) -> dict[str, Any]:
    lease = getattr(self, "_analysis_lease", None)
    if lease is None:
      raise RuntimeError("A claimed analysis attempt is required for publication.")
    response = self.client.rpc("publish_video_analysis", {
      **lease, "p_video_id": video_id, "p_fields": fields,
      "p_model_version": model_version, "p_result_json": result_json,
    }).execute()
    data = response.data
    if (not isinstance(data, dict) or not isinstance(data.get("video"), dict)
        or data["video"].get("id") != video_id):
      raise RuntimeError("Analysis publication is unavailable.")
    for field, expected in fields.items():
      if field not in data["video"]:
        raise RuntimeError("Analysis publication is unavailable.")
      actual = data["video"][field]
      if field == "fps":
        # The production column is numeric(8,2); Postgres rounds its value.
        matches = (type(actual) in (int, float) and type(expected) in (int, float)
                   and Decimal(str(actual)) == Decimal(str(expected)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
      elif field == "duration_ms":
        matches = type(actual) is int and type(expected) is int and actual == expected
      elif field == "storage_optimized_at" and expected is not None:
        matches = self._parse_timestamp(expected) is not None and self._parse_timestamp(actual) == self._parse_timestamp(expected)
      else:
        matches = actual == expected
      if not matches:
        raise RuntimeError("Analysis publication is unavailable.")
    return data

  def get_video(self, video_id: str) -> dict[str, Any] | None:
    # Load one uploaded video row by ID.
    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS_WITH_PREFLIGHT)
        .eq("id", video_id)
        .limit(1)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to video query without quality preflight for video %s: %s", video_id, error)
      try:
        response = (
          self.client.table("videos")
          .select(VIDEO_STORAGE_COLUMNS)
          .eq("id", video_id)
          .limit(1)
          .execute()
        )
      except Exception as tracking_error:
        logger.warning("Falling back to video query without tracking setup for video %s: %s", video_id, tracking_error)
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
            .select(VIDEO_LEGACY_BASE_COLUMNS)
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

  def supports_quality_preflight(self) -> bool:
    # Both columns are required: one stores the evidence and one limits the
    # gate to new submissions without changing legacy video behavior.
    try:
      (
        self.client.table("videos")
        .select("quality_preflight,quality_preflight_required")
        .limit(1)
        .execute()
      )
      return True
    except Exception as error:
      error_code = str(getattr(error, "code", "") or "")
      error_message = str(error).lower()
      missing_preflight_column = (
        error_code == "42703"
        or (
          ("quality_preflight" in error_message or "quality_preflight_required" in error_message)
          and ("does not exist" in error_message or "could not find" in error_message)
        )
      )

      if missing_preflight_column:
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

  def get_owned_videos(self, video_ids: list[str], user_id: str) -> list[dict[str, Any]]:
    if not video_ids:
      return []

    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("user_id", user_id)
        .in_("id", video_ids)
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to legacy owned-video batch query for user %s: %s", user_id, error)
      response = (
        self.client.table("videos")
        .select(VIDEO_LEGACY_BASE_COLUMNS)
        .eq("user_id", user_id)
        .in_("id", video_ids)
        .execute()
      )

    return response.data or []

  def update_video(self, video_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    if getattr(self, "_analysis_lease", None) is not None:
      return self._publish_analysis(video_id, fields)["video"]
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

  def list_analysis_activity_videos(self, user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """List unfinished or unreviewed analysis uploads owned by one user."""
    try:
      response = (
        self.client.table("videos")
        .select(VIDEO_STORAGE_COLUMNS)
        .eq("user_id", user_id)
        .eq("save_state", "pending")
        .filter("discarded_at", "is", "null")
        .in_("status", ["queued", "processing", "completed", "failed"])
        .order("created_at", desc=True)
        .limit(max(1, min(limit, 50)))
        .execute()
      )
    except Exception as error:
      logger.warning("Falling back to legacy analysis activity query for user %s: %s", user_id, error)
      response = (
        self.client.table("videos")
        .select(VIDEO_LEGACY_BASE_COLUMNS)
        .eq("user_id", user_id)
        .eq("save_state", "pending")
        .in_("status", ["queued", "processing", "completed", "failed"])
        .order("created_at", desc=True)
        .limit(max(1, min(limit, 50)))
        .execute()
      )

    now = datetime.now(timezone.utc)
    visible: list[dict[str, Any]] = []
    for video in response.data or []:
      expires_at = self._parse_timestamp(video.get("expires_at"))
      if expires_at is not None and expires_at <= now:
        continue
      if video.get("discarded_at"):
        continue
      visible.append(video)
    return visible

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

  def mark_saved(
    self,
    video_id: str,
    *,
    performed_reps: int | None,
    load_value: float | None,
    load_unit: str | None,
    metadata: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    # Saved videos stay visible in the home flow.
    saved_at = datetime.now(timezone.utc).isoformat()
    fields = {
      "save_state": "saved",
      "is_saved": True,
      "saved_at": saved_at,
      "expires_at": None,
      "performed_reps": performed_reps,
      "load_value": load_value,
      "load_unit": load_unit,
    }
    if metadata:
      if metadata.keys() - {"user_notes", "weight", "weight_unit", "corrected_rep_count"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported save metadata.")
      fields.update(metadata)

    self._validate_storage_path_update(video_id, fields)
    # Check the tombstone in the write so a concurrent discard cannot be undone.
    response = (
      self.client.table("videos")
      .update(fields)
      .eq("id", video_id)
      .is_("discarded_at", "null")
      .execute()
    )
    if not response.data:
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Video is no longer available to save.",
      )
    return response.data[0]

  def mark_discarded(self, video_id: str) -> dict[str, Any]:
    # Discarded rows remain as metadata, but they leave the saved library.
    fields = {
      "save_state": "pending",
      "is_saved": False,
      "discarded_at": datetime.now(timezone.utc).isoformat(),
      "expires_at": None,
    }

    return self.update_video(video_id, fields)

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
        .select(VIDEO_LEGACY_BASE_COLUMNS)
        .eq("save_state", "pending")
        .lt("expires_at", now)
        .execute()
      )
    return response.data or []

  def claim_expired_deletion(self, video_id: str) -> dict[str, Any] | None:
    response = self.client.rpc("claim_expired_video_deletion", {"p_video_id": video_id}).execute()
    return response.data[0] if response.data else None

  def revoke_for_discard(self, video_id: str, user_id: str) -> dict[str, Any]:
    response = self.client.rpc("revoke_video_media", {
      "p_user_id": user_id, "p_video_ids": [video_id], "p_delete_metadata": False,
    }).execute()
    rows = response.data
    if not isinstance(rows, list) or len(rows) != 1:
      raise ValueError("Missing discard revocation snapshot")
    task = rows[0]
    validate_media_deletion_task(task)
    if (task["video_id"] != video_id or task["user_id"] != user_id
        or task["delete_metadata"] is not False
        or task["export_prefixes"] != [f"{user_id}/exports/{video_id}-"]):
      raise ValueError("Mismatched discard revocation snapshot")
    return task

  def revoke_saved_lifts(self, video_ids: list[str], user_id: str) -> list[dict[str, Any]]:
    response = self.client.rpc("revoke_saved_lifts", {
      "p_user_id": user_id, "p_video_ids": video_ids,
    }).execute()
    return self._saved_deletion_rows(response.data, video_ids, user_id)

  def saved_lift_deletion_complete(self, video_ids: list[str], user_id: str) -> bool:
    response = self.client.rpc("read_saved_lift_deletion_receipts", {
      "p_user_id": user_id, "p_video_ids": video_ids,
    }).execute()
    rows = self._saved_deletion_rows(response.data, video_ids, user_id, readback=True)
    return all(row["completed"] for row in rows)

  @staticmethod
  def _saved_deletion_rows(data: Any, video_ids: list[str], user_id: str, *, readback: bool = False) -> list[dict[str, Any]]:
    if not isinstance(data, list) or len(data) != len(video_ids) or not video_ids:
      raise ValueError("Incomplete Saved Lift deletion proof")
    seen: set[str] = set()
    for row in data:
      if (not isinstance(row, dict) or set(row) != {"video_id", "user_id", "completed", "task"}
          or row["video_id"] not in video_ids or row["video_id"] in seen
          or row["user_id"] != user_id or type(row["completed"]) is not bool):
        raise ValueError("Mismatched Saved Lift deletion proof")
      for identity in (row["video_id"], row["user_id"]):
        if not isinstance(identity, str) or str(UUID(identity)) != identity or UUID(identity).int == 0:
          raise ValueError("Invalid Saved Lift deletion identity")
      seen.add(row["video_id"])
      if row["completed"] or readback:
        if row["task"] is not None:
          raise ValueError("Conflicting Saved Lift deletion proof")
      else:
        task = row["task"]
        validate_media_deletion_task(task)
        if (task["video_id"] != row["video_id"] or task["user_id"] != user_id
            or task["delete_metadata"] is not True
            or task["export_prefixes"] != [f"{user_id}/exports/{row['video_id']}-"]):
          raise ValueError("Mismatched Saved Lift cleanup snapshot")
    if seen != set(video_ids):
      raise ValueError("Incomplete Saved Lift deletion proof")
    return data

  def list_pending_deletions(self) -> list[dict[str, Any]]:
    response = (self.client.table("video_deletion_outbox").select("video_id,user_id,storage_paths,archive_paths,export_prefixes,delete_metadata")
                .order("created_at").limit(200).execute())
    return response.data or []

  def complete_deletion(self, task: dict[str, Any]) -> bool:
    response = self.client.rpc("complete_video_media_deletion", {
      "p_video_id": task["video_id"],
      "p_user_id": task["user_id"],
      "p_storage_paths": task["storage_paths"],
      "p_archive_paths": task["archive_paths"],
      "p_export_prefixes": task["export_prefixes"],
      "p_delete_metadata": task["delete_metadata"],
    }).execute()
    # A stale snapshot is a retry, never permission to drop a newer task.
    return response.data is True

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
        .select(VIDEO_LEGACY_BASE_COLUMNS)
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
      response = self.client.table("videos").select(VIDEO_LEGACY_BASE_COLUMNS).execute()
    return response.data or []

  def list_storage_cleanup_candidates(self, older_than_days: int = 7) -> list[dict[str, Any]]:
    # The video table is small; filter in Python so mixed schema eras stay safe.
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    try:
      response = self.client.table("videos").select(VIDEO_STORAGE_COLUMNS).execute()
    except Exception as error:
      logger.warning("Falling back to legacy storage cleanup query: %s", error)
      response = self.client.table("videos").select(VIDEO_LEGACY_BASE_COLUMNS).execute()
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
        .select(VIDEO_LEGACY_BASE_COLUMNS)
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
        .select(VIDEO_LEGACY_BASE_COLUMNS)
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
        .select(VIDEO_LEGACY_BASE_COLUMNS)
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
        publication = self._publish_analysis(video_id, {}, model_version=model_version, result_json=result_json)
        analysis = publication.get("analysis")
        try:
          analysis_id = analysis["id"]
          valid = (isinstance(analysis_id, str) and str(UUID(analysis_id)) == analysis_id and UUID(analysis_id).int != 0
                   and analysis.get("video_id") == video_id and analysis.get("model_version") == model_version
                   and isinstance(analysis.get("result_json"), dict) and analysis["result_json"] == result_json)
        except (KeyError, TypeError, ValueError, AttributeError):
          valid = False
        if not valid:
          raise RuntimeError("Analysis publication is unavailable.")
        return analysis
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
      .order("id", desc=True)
      .limit(1)
      .execute()
    )
    return response.data[0] if response.data else None

  def get_latest_analysis_results(
    self, video_ids: list[str], *, include_result_json: bool = True,
  ) -> dict[str, dict[str, Any]]:
    if not video_ids:
      return {}

    response = (
      self.client.table("analysis_results")
      .select(ANALYSIS_RESULT_COLUMNS if include_result_json else ANALYSIS_RESULT_METADATA_COLUMNS)
      .in_("video_id", video_ids)
      .order("created_at", desc=True)
      .order("id", desc=True)
      .execute()
    )
    latest_by_video_id: dict[str, dict[str, Any]] = {}

    for row in response.data or []:
      video_id = str(row.get("video_id") or "")
      if video_id and video_id not in latest_by_video_id:
        latest_by_video_id[video_id] = row

    return latest_by_video_id
