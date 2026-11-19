#!/usr/bin/env python3
"""Check local migration preview evidence after a successful Supabase CLI 2.98.2 dry run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from prepare_web_mvp_migrations import (
  PROJECT, PreparationError, digest, load_json, read_regular, require,
  validate_manifest,
)


MANIFEST = Path(__file__).resolve().parents[1] / 'config/web-mvp-migrations.json'
DRY_RUN_BANNER = 'DRY RUN: migrations will *not* be pushed to the database.'
UPGRADE_NOTICE = (
  r'A new version of Supabase CLI is available: v[0-9]+\.[0-9]+\.[0-9]+ '
  r'\(currently installed v2\.98\.2\)'
)
UPGRADE_GUIDE = ('We recommend updating regularly for new features and bug fixes: '
                 'https://supabase.com/docs/guides/cli/getting-started#updating-the-supabase-cli')


def verify(workspace: Path, dry_run_log: Path):
  manifest_bytes = read_regular(MANIFEST)
  manifest = load_json(manifest_bytes)
  validate_manifest(manifest)
  selected_names = manifest['selectedMigrations']
  selected_rows = [row for row in manifest['catalog'] if row['file'] in selected_names]
  pending_names = manifest['expectedPendingMigrations']

  supabase = workspace / 'supabase'
  migrations = supabase / 'migrations'
  link = supabase / '.temp'
  for directory in (workspace, supabase, migrations, link):
    require(directory.is_dir() and not directory.is_symlink(),
            'Migration workspace must use real directories.')

  receipt = load_json(read_regular(workspace / 'preparation-receipt.json'))
  require(type(receipt) is dict and type(receipt.get('schemaVersion')) is int
          and receipt['schemaVersion'] == 1
          and receipt.get('authorization') == 'local-preparation-only'
          and receipt.get('projectRef') == PROJECT
          and receipt.get('manifestSha256') == digest(manifest_bytes)
          and receipt.get('selectedMigrations') == selected_rows
          and receipt.get('pendingMigrations') == pending_names,
          'Preparation receipt differs from the reviewed production manifest.')
  require(sorted(path.name for path in migrations.iterdir()) == selected_names,
          'Prepared migration directory differs from the reviewed selection.')
  for row in selected_rows:
    require(digest(read_regular(migrations / row['file'])) == row['sha256'],
            'Prepared migration bytes differ from the reviewed selection.')
  require(read_regular(link / 'project-ref', maximum=128).strip() == PROJECT.encode('ascii'),
          'Local link marker does not match the reviewed production project.')

  log_bytes = read_regular(dry_run_log, maximum=65536)
  lines = [line.strip() for line in log_bytes.decode('utf-8').splitlines() if line.strip()]
  if len(lines) >= 2 and lines[-1] == UPGRADE_GUIDE and re.fullmatch(UPGRADE_NOTICE, lines[-2]):
    lines = lines[:-2]
  expected_plan = [DRY_RUN_BANNER, 'Connecting to remote database...', 'Would push these migrations:',
                   *(f'• {name}' for name in pending_names),
                   'Finished supabase db push.']
  require(lines == expected_plan,
          'Dry-run log differs from the reviewed production preview.')
  return {'dryRunLogSha256': digest(log_bytes), 'pendingMigrations': len(pending_names)}


def main(argv=None):
  parser = argparse.ArgumentParser(
    description=__doc__,
    epilog='Verify the CLI exit status, live target and evidence freshness separately.',
  )
  parser.add_argument('--workspace', type=Path, required=True)
  parser.add_argument('--dry-run-log', type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    result = verify(args.workspace, args.dry_run_log)
  except PreparationError as error:
    print('Migration preview check failed: ' + str(error), file=sys.stderr)
    return 1
  except (OSError, UnicodeError, RecursionError):
    print('Migration preview check failed: could not read valid local evidence.', file=sys.stderr)
    return 1
  print(json.dumps(result))
  return 0


if __name__ == '__main__':
  sys.exit(main())
