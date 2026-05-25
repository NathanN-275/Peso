#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.storage_service import StorageService  # noqa: E402
from app.services.video_repository import VideoRepository  # noqa: E402


logger = logging.getLogger("cleanup_supabase_storage")


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Clean explicit Supabase Storage video objects for discarded, failed, and stale unsaved videos."
  )
  parser.add_argument(
    "--confirm",
    action="store_true",
    help="Actually delete storage objects and mark rows discarded. Without this flag, this is a dry run.",
  )
  parser.add_argument(
    "--older-than-days",
    type=int,
    default=7,
    help="Treat uploaded/queued/pending unsaved videos older than this many days as stale.",
  )
  return parser.parse_args()


def cleanup_reason(video: dict[str, Any]) -> str:
  if video.get("discarded_at") is not None:
    return "discarded_unsaved"

  if video.get("status") == "failed":
    return "failed"

  return "stale_pending"


def path_belongs_to_user(path: str, user_id: str) -> bool:
  return bool(path) and path.startswith(f"{user_id}/")


def storage_paths_for_video(storage: StorageService, video: dict[str, Any]) -> list[str]:
  user_id = str(video.get("user_id") or "")
  paths = [
    str(video.get("storage_path") or ""),
    str(video.get("original_storage_path") or ""),
    str(video.get("playback_path") or ""),
    str(video.get("thumbnail_path") or ""),
  ]
  video_id = str(video.get("id") or "")

  if user_id and video_id:
    export_prefix = f"{user_id}/exports/{video_id}-"
    paths.extend(storage.list_storage_prefix(export_prefix))

  owned_paths: list[str] = []
  for path in [path for path in dict.fromkeys(paths) if path]:
    if path_belongs_to_user(path, user_id):
      owned_paths.append(path)
    else:
      logger.warning("Skipping cleanup path outside user folder user_id=%s path=%s", user_id, path)

  return owned_paths


def main() -> int:
  args = parse_args()
  logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
  repository = VideoRepository()
  storage = StorageService()
  candidates = repository.list_storage_cleanup_candidates(older_than_days=args.older_than_days)
  mode = "CONFIRM" if args.confirm else "DRY RUN"

  logger.info("%s: found %s cleanup candidate rows.", mode, len(candidates))

  deleted_paths = 0
  touched_rows = 0

  for video in candidates:
    video_id = str(video["id"])
    reason = cleanup_reason(video)
    paths = storage_paths_for_video(storage, video)

    logger.info("Candidate video_id=%s reason=%s path_count=%s", video_id, reason, len(paths))

    for path in paths:
      if args.confirm:
        logger.info("Deleting storage object: %s", path)
        storage.delete_storage_path(path)
        deleted_paths += 1
      else:
        logger.info("Dry run would delete storage object: %s", path)

    if args.confirm:
      repository.mark_discarded(video_id)
      touched_rows += 1

  if args.confirm:
    logger.info("Deleted %s storage objects and marked %s rows discarded.", deleted_paths, touched_rows)
  else:
    logger.info("Dry run complete. Re-run with --confirm to delete the listed storage objects.")

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
