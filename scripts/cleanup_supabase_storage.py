#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.storage_cleanup import StorageCleanupService  # noqa: E402


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Clean unnecessary Supabase Storage objects using the backend cleanup service."
  )
  parser.add_argument(
    "--confirm",
    action="store_true",
    help="Actually delete storage objects and mark rows discarded. Without this flag, this is a dry run.",
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Report reclaimable storage without deleting anything.",
  )
  return parser.parse_args()


def main() -> int:
  args = parse_args()
  dry_run = args.dry_run or not args.confirm
  report = StorageCleanupService().run(dry_run=dry_run)
  print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
