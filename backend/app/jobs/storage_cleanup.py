from __future__ import annotations

import argparse
import json

from ..services.storage_cleanup import StorageCleanupService


def main() -> None:
  parser = argparse.ArgumentParser(description="Clean unnecessary Supabase Storage objects.")
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Report objects and rows that would be cleaned without deleting anything.",
  )
  args = parser.parse_args()

  report = StorageCleanupService().run(dry_run=args.dry_run)
  print(json.dumps(report.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
  main()
