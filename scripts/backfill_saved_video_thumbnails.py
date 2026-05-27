#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Backfill one JPEG thumbnail for saved videos missing a current thumbnail path."
  )
  parser.add_argument(
    "--confirm",
    action="store_true",
    help="Generate/upload thumbnails and update rows. Without this flag, this is a dry run.",
  )
  parser.add_argument(
    "--force",
    action="store_true",
    help="Regenerate thumbnails for saved videos even when thumbnail_path is already set.",
  )
  return parser.parse_args()


def load_backend_env() -> None:
  env_path = BACKEND / ".env"
  if not env_path.exists():
    return

  for line in env_path.read_text().splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
      continue

    if stripped.startswith("export "):
      stripped = stripped.removeprefix("export ").strip()

    if "=" not in stripped:
      continue

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")

    if key and key not in os.environ:
      os.environ[key] = value


def load_services():
  try:
    from app.services.saved_thumbnail_backfill import backfill_saved_video_thumbnails
    from app.services.storage_service import StorageService
    from app.services.video_repository import VideoRepository
  except ModuleNotFoundError as error:
    missing_name = error.name or "a backend dependency"
    raise SystemExit(
      f"Missing Python dependency '{missing_name}'. Run this with "
      "`backend/.venv/bin/python scripts/backfill_saved_video_thumbnails.py` "
      "from the repo root, or install the backend dependencies first."
    ) from error

  return backfill_saved_video_thumbnails, StorageService, VideoRepository


def main() -> int:
  args = parse_args()
  load_backend_env()
  backfill_saved_video_thumbnails, StorageService, VideoRepository = load_services()
  logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
  result = backfill_saved_video_thumbnails(
    repository=VideoRepository(),
    storage=StorageService(),
    confirm=args.confirm,
    force=args.force,
  )
  logging.info(
    "Saved thumbnail backfill complete dry_run=%s force=%s candidates=%s generated=%s failed=%s",
    result.dry_run,
    args.force,
    result.candidate_count,
    result.generated_count,
    result.failed_count,
  )
  return 1 if result.failed_count > 0 else 0


if __name__ == "__main__":
  raise SystemExit(main())
