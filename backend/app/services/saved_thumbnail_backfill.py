from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage_service import IMMUTABLE_CACHE_CONTROL_SECONDS, StorageService
from .video_assets import THUMBNAIL_VERSION, build_thumbnail_storage_path, create_video_thumbnail
from .video_repository import VIDEO_BASE_COLUMNS, VIDEO_STORAGE_COLUMNS, VideoRepository


logger = logging.getLogger(__name__)


@dataclass
class SavedThumbnailBackfillResult:
  candidate_count: int = 0
  generated_count: int = 0
  failed_count: int = 0
  dry_run: bool = True


def video_needs_saved_thumbnail_backfill(video: dict[str, Any], *, force: bool = False) -> bool:
  is_saved = video.get("save_state") == "saved" or video.get("is_saved") is True
  is_discarded = video.get("discarded_at") is not None
  thumbnail_path = str(video.get("thumbnail_path") or "")
  has_current_thumbnail = thumbnail_path.endswith(f"-{THUMBNAIL_VERSION}.jpg")
  return is_saved and not is_discarded and (force or not has_current_thumbnail)


def list_saved_thumbnail_backfill_candidates(
  repository: VideoRepository,
  *,
  force: bool = False,
) -> list[dict[str, Any]]:
  try:
    response = repository.client.table("videos").select(VIDEO_STORAGE_COLUMNS).execute()
  except Exception as error:
    logger.warning("Falling back to legacy saved-thumbnail backfill query: %s", error)
    response = repository.client.table("videos").select(VIDEO_BASE_COLUMNS).execute()

  return [
    video
    for video in response.data or []
    if video_needs_saved_thumbnail_backfill(video, force=force)
  ]


def backfill_saved_video_thumbnails(
  *,
  repository: VideoRepository,
  storage: StorageService,
  confirm: bool = False,
  force: bool = False,
) -> SavedThumbnailBackfillResult:
  candidates = list_saved_thumbnail_backfill_candidates(repository, force=force)
  result = SavedThumbnailBackfillResult(
    candidate_count=len(candidates),
    dry_run=not confirm,
  )

  for video in candidates:
    video_id = str(video["id"])
    user_id = str(video["user_id"])
    storage_path = str(video["storage_path"])
    thumbnail_path = build_thumbnail_storage_path(user_id, video_id)
    logger.info(
      "%s saved thumbnail backfill candidate video_id=%s source_path=%s thumbnail_path=%s force=%s",
      "Dry run:" if not confirm else "Backfilling",
      video_id,
      storage_path,
      thumbnail_path,
      force,
    )

    if not confirm:
      continue

    source_file: Path | None = None
    thumbnail_file: Path | None = None

    try:
      source_file = storage.download_to_tempfile(storage_path)

      with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_thumbnail:
        thumbnail_file = Path(temp_thumbnail.name)

      create_video_thumbnail(source_file, thumbnail_file)
      logger.info("Uploading saved thumbnail path=%s", thumbnail_path)
      storage.upload_file(
        thumbnail_path,
        thumbnail_file,
        "image/jpeg",
        cache_control=IMMUTABLE_CACHE_CONTROL_SECONDS,
      )
      try:
        repository.update_video(video_id, {"thumbnail_path": thumbnail_path})
      except Exception:
        logger.exception(
          "Failed to update saved thumbnail metadata; deleting uploaded thumbnail path=%s",
          thumbnail_path,
        )
        storage.delete_storage_path(thumbnail_path)
        raise
      result.generated_count += 1
    except Exception:
      result.failed_count += 1
      logger.exception(
        "Failed saved thumbnail backfill video_id=%s source_path=%s thumbnail_path=%s",
        video_id,
        storage_path,
        thumbnail_path,
      )
    finally:
      if source_file:
        storage.remove_tempfile(source_file)

      if thumbnail_file:
        storage.remove_tempfile(thumbnail_file)

  return result
