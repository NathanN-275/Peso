from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings, get_settings
from .storage_service import StorageService
from .video_repository import VideoRepository


logger = logging.getLogger(__name__)

IN_PROGRESS_STATUSES = {"queued", "processing"}
LOCAL_DEVELOPMENT_ENVS = {"development", "dev", "local", "test"}
UUID_PATH_SEGMENT = re.compile(
  r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass
class StorageCleanupReport:
  dry_run: bool
  deleted_count: int = 0
  expired_pending_videos: int = 0
  stale_pending_videos: int = 0
  old_export_objects: int = 0
  orphan_objects: int = 0
  storage_objects: int = 0
  bytes_reclaimable: int = 0
  errors: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)


def cleanup_requires_token(settings: Settings) -> bool:
  return settings.backend_env not in LOCAL_DEVELOPMENT_ENVS


def _parse_datetime(value: Any) -> datetime | None:
  if isinstance(value, datetime):
    parsed_value = value
  elif isinstance(value, str) and value:
    try:
      parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
      return None
  else:
    return None

  if parsed_value.tzinfo is None:
    return parsed_value.replace(tzinfo=timezone.utc)

  return parsed_value.astimezone(timezone.utc)


def _metadata_value(object_info: dict[str, Any], *keys: str) -> Any:
  metadata = object_info.get("metadata")

  for key in keys:
    if key in object_info:
      return object_info[key]

    if isinstance(metadata, dict) and key in metadata:
      return metadata[key]

  return None


def _parse_size_bytes(value: Any) -> int:
  if isinstance(value, int):
    return value

  if isinstance(value, float) and value >= 0:
    return int(value)

  if isinstance(value, str) and value.isdigit():
    return int(value)

  return 0


def _object_size_bytes(storage_object: dict[str, Any]) -> int:
  return _parse_size_bytes(_metadata_value(storage_object, "size", "contentLength", "content_length"))


def _object_timestamp(storage_object: dict[str, Any]) -> datetime | None:
  return (
    _parse_datetime(storage_object.get("updated_at"))
    or _parse_datetime(storage_object.get("created_at"))
    or _parse_datetime(storage_object.get("last_accessed_at"))
  )


def _video_updated_at(video: dict[str, Any]) -> datetime | None:
  return _parse_datetime(video.get("updated_at")) or _parse_datetime(video.get("created_at"))


def _is_older_than(timestamp: datetime | None, cutoff: datetime) -> bool:
  return timestamp is not None and timestamp < cutoff


def _path_parts(path: str) -> list[str]:
  return [part for part in path.strip("/").split("/") if part]


def is_app_storage_path(path: str) -> bool:
  parts = _path_parts(path)
  return len(parts) >= 2 and bool(UUID_PATH_SEGMENT.fullmatch(parts[0]))


def is_export_storage_path(path: str) -> bool:
  parts = _path_parts(path)
  return len(parts) >= 3 and bool(UUID_PATH_SEGMENT.fullmatch(parts[0])) and parts[1] == "exports"


class StorageCleanupService:
  def __init__(
    self,
    repository: VideoRepository | None = None,
    storage: StorageService | None = None,
    settings: Settings | None = None,
  ) -> None:
    self.repository = repository or VideoRepository()
    self.storage = storage or StorageService()
    self.settings = settings or get_settings()

  def run(self, *, dry_run: bool = False, now: datetime | None = None) -> StorageCleanupReport:
    cleanup_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    report = StorageCleanupReport(dry_run=dry_run)
    storage_objects = self._list_storage_objects(report)
    object_by_path = {
      storage_object["path"]: storage_object
      for storage_object in storage_objects
      if isinstance(storage_object.get("path"), str)
    }
    referenced_paths = self._list_referenced_storage_paths(report)
    scheduled_storage_paths: set[str] = set()

    self._cleanup_pending_videos(
      report=report,
      object_by_path=object_by_path,
      scheduled_storage_paths=scheduled_storage_paths,
      dry_run=dry_run,
      now=cleanup_now,
    )
    self._cleanup_old_exports(
      report=report,
      storage_objects=storage_objects,
      object_by_path=object_by_path,
      scheduled_storage_paths=scheduled_storage_paths,
      dry_run=dry_run,
      now=cleanup_now,
    )
    if referenced_paths is not None:
      self._cleanup_orphan_uploads(
        report=report,
        storage_objects=storage_objects,
        object_by_path=object_by_path,
        referenced_paths=referenced_paths,
        scheduled_storage_paths=scheduled_storage_paths,
        dry_run=dry_run,
        now=cleanup_now,
      )

    return report

  def _list_storage_objects(self, report: StorageCleanupReport) -> list[dict[str, Any]]:
    try:
      return self.storage.list_storage_objects_recursive()
    except Exception as error:
      message = f"Unable to list storage objects: {error}"
      logger.warning(message)
      report.errors.append(message)
      return []

  def _list_referenced_storage_paths(self, report: StorageCleanupReport) -> set[str] | None:
    try:
      videos = self.repository.list_storage_referenced_videos()
    except Exception as error:
      message = f"Unable to list referenced videos: {error}"
      logger.warning(message)
      report.errors.append(message)
      return None

    referenced_paths: set[str] = set()

    for video in videos:
      for key in ("storage_path", "thumbnail_path"):
        path = video.get(key)

        if isinstance(path, str) and path:
          referenced_paths.add(path)

    return referenced_paths

  def _cleanup_pending_videos(
    self,
    *,
    report: StorageCleanupReport,
    object_by_path: dict[str, dict[str, Any]],
    scheduled_storage_paths: set[str],
    dry_run: bool,
    now: datetime,
  ) -> None:
    stale_cutoff = now - timedelta(hours=self.settings.stale_processing_hours)
    candidates: dict[str, tuple[dict[str, Any], str]] = {}

    try:
      expired_videos = self.repository.list_expired_pending_videos()
    except Exception as error:
      message = f"Unable to list expired pending videos: {error}"
      logger.warning(message)
      report.errors.append(message)
      expired_videos = []

    for video in expired_videos:
      if not self._video_can_be_deleted(video, stale_cutoff=stale_cutoff):
        continue

      video_id = str(video.get("id") or "")

      if video_id:
        candidates[video_id] = (video, "expired")

    try:
      stale_videos = self.repository.list_stale_pending_in_progress_videos(stale_cutoff.isoformat())
    except Exception as error:
      message = f"Unable to list stale pending videos: {error}"
      logger.warning(message)
      report.errors.append(message)
      stale_videos = []

    for video in stale_videos:
      if video.get("save_state") == "saved":
        continue

      video_id = str(video.get("id") or "")

      if video_id and video_id not in candidates:
        candidates[video_id] = (video, "stale")

    for video_id, (video, reason) in candidates.items():
      source_path = video.get("storage_path")

      if not isinstance(source_path, str) or not is_app_storage_path(source_path):
        report.errors.append(f"Skipped video {video_id} because its storage path is outside the app layout.")
        continue

      if reason == "expired":
        report.expired_pending_videos += 1
      else:
        report.stale_pending_videos += 1

      storage_paths = self._video_storage_paths(video)
      storage_paths.extend(self._export_paths_for_video(video, video_id, object_by_path.values()))

      storage_deleted = self._delete_storage_paths(
        storage_paths,
        report=report,
        object_by_path=object_by_path,
        scheduled_storage_paths=scheduled_storage_paths,
        dry_run=dry_run,
      )

      if dry_run:
        continue

      if not storage_deleted:
        report.errors.append(f"Skipped deleting video row {video_id} because storage cleanup failed.")
        continue

      try:
        self.repository.delete_video_with_analysis(video_id)
        report.deleted_count += 1
      except Exception as error:
        message = f"Unable to delete video row {video_id}: {error}"
        logger.warning(message)
        report.errors.append(message)

  def _video_can_be_deleted(self, video: dict[str, Any], *, stale_cutoff: datetime) -> bool:
    if video.get("save_state") == "saved":
      return False

    status = str(video.get("status") or "")

    if status not in IN_PROGRESS_STATUSES:
      return True

    return _is_older_than(_video_updated_at(video), stale_cutoff)

  def _video_storage_paths(self, video: dict[str, Any]) -> list[str]:
    storage_paths: list[str] = []

    for key in ("storage_path", "thumbnail_path"):
      path = video.get(key)

      if isinstance(path, str) and is_app_storage_path(path):
        storage_paths.append(path)

    return storage_paths

  def _export_paths_for_video(
    self,
    video: dict[str, Any],
    video_id: str,
    storage_objects: Any,
  ) -> list[str]:
    user_id = str(video.get("user_id") or "")

    if not user_id:
      return []

    export_prefix = f"{user_id}/exports/{video_id}-"
    return [
      storage_object["path"]
      for storage_object in storage_objects
      if isinstance(storage_object.get("path"), str)
      and storage_object["path"].startswith(export_prefix)
      and is_export_storage_path(storage_object["path"])
    ]

  def _cleanup_old_exports(
    self,
    *,
    report: StorageCleanupReport,
    storage_objects: list[dict[str, Any]],
    object_by_path: dict[str, dict[str, Any]],
    scheduled_storage_paths: set[str],
    dry_run: bool,
    now: datetime,
  ) -> None:
    export_cutoff = now - timedelta(hours=self.settings.export_cache_ttl_hours)

    for storage_object in storage_objects:
      path = storage_object.get("path")

      if not isinstance(path, str) or path in scheduled_storage_paths:
        continue

      if not is_export_storage_path(path):
        continue

      if not _is_older_than(_object_timestamp(storage_object), export_cutoff):
        continue

      report.old_export_objects += 1
      self._delete_storage_paths(
        [path],
        report=report,
        object_by_path=object_by_path,
        scheduled_storage_paths=scheduled_storage_paths,
        dry_run=dry_run,
      )

  def _cleanup_orphan_uploads(
    self,
    *,
    report: StorageCleanupReport,
    storage_objects: list[dict[str, Any]],
    object_by_path: dict[str, dict[str, Any]],
    referenced_paths: set[str],
    scheduled_storage_paths: set[str],
    dry_run: bool,
    now: datetime,
  ) -> None:
    orphan_cutoff = now - timedelta(hours=self.settings.orphan_storage_min_age_hours)

    for storage_object in storage_objects:
      path = storage_object.get("path")

      if not isinstance(path, str) or path in scheduled_storage_paths:
        continue

      if not is_app_storage_path(path) or is_export_storage_path(path):
        continue

      if path in referenced_paths:
        continue

      if not _is_older_than(_object_timestamp(storage_object), orphan_cutoff):
        continue

      report.orphan_objects += 1
      self._delete_storage_paths(
        [path],
        report=report,
        object_by_path=object_by_path,
        scheduled_storage_paths=scheduled_storage_paths,
        dry_run=dry_run,
      )

  def _delete_storage_paths(
    self,
    paths: list[str],
    *,
    report: StorageCleanupReport,
    object_by_path: dict[str, dict[str, Any]],
    scheduled_storage_paths: set[str],
    dry_run: bool,
  ) -> bool:
    deleted_all_paths = True

    for path in dict.fromkeys(paths):
      if not is_app_storage_path(path):
        report.errors.append(f"Skipped non-app storage path: {path}")
        deleted_all_paths = False
        continue

      if path in scheduled_storage_paths:
        continue

      scheduled_storage_paths.add(path)
      report.storage_objects += 1
      report.bytes_reclaimable += _object_size_bytes(object_by_path.get(path, {}))

      if dry_run:
        continue

      try:
        self.storage.delete_storage_path(path)
      except Exception as error:
        deleted_all_paths = False
        message = f"Unable to delete storage object {path}: {error}"
        logger.warning(message)
        report.errors.append(message)

    return deleted_all_paths
