#!/usr/bin/env python3
"""Prepare byte-pinned MVP SQL locally. No provider calls, linkage or application."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


PROJECT = 'jfgiydtrskpqxyorvvbc'
AZURE_FILE = '202608300001_azure_analysis_queue_scaler.sql'
AZURE_SHA256 = '9f6064153d7efbd4a305b6595aa79742b7c5732f5a73744c93e275b9657a1c44'
MANIFEST_FIELDS = {'schemaVersion', 'evidenceBaseCommit', 'projectRef', 'catalog',
                   'selectedMigrations', 'excludedMigrations', 'observedHistory',
                   'expectedPendingMigrations', 'sourceConfig'}


class PreparationError(ValueError):
  pass


def require(condition, message):
  if not condition:
    raise PreparationError(message)


def digest(data):
  return hashlib.sha256(data).hexdigest()


def read_regular(path, maximum=2 * 1024 * 1024):
  require(not path.is_symlink(), 'Symlink input is not permitted.')
  require(stat.S_ISREG(path.lstat().st_mode), 'Input must be a regular file.')
  with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
    info = os.fstat(stream.fileno())
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= maximum,
            'Input must be a bounded regular file.')
    data = stream.read(maximum + 1)
  require(len(data) <= maximum, 'Input exceeds its size limit.')
  return data


def load_json(data):
  def unique(pairs):
    result = {}
    for key, value in pairs:
      require(key not in result, 'Duplicate JSON keys are not permitted.')
      result[key] = value
    return result
  try:
    return json.loads(data, object_pairs_hook=unique)
  except (ValueError, UnicodeError) as error:
    if isinstance(error, PreparationError):
      raise
    raise PreparationError('Input JSON is invalid.') from None


def migration_name(file):
  require(type(file) is str and re.fullmatch(r'(\d{12}|\d{14})_[a-z0-9_]+\.sql', file),
          'Migration filename is invalid.')
  version, name = file[:-4].split('_', 1)
  return {'version': version, 'name': name}


def validate_history_rows(rows):
  require(type(rows) is list and len(rows) == 21, 'Hosted history differs from the reviewed baseline.')
  files = []
  for row in rows:
    require(type(row) is dict and set(row) == {'version', 'name'}
            and type(row['version']) is str and type(row['name']) is str,
            'Hosted history row is invalid.')
    file = f"{row['version']}_{row['name']}.sql"
    require(migration_name(file) == row, 'Hosted history identity is invalid.')
    files.append(file)
  require(files == sorted(set(files)), 'Hosted history must be unique and ordered.')
  return files


def validate_manifest(manifest):
  require(type(manifest) is dict and set(manifest) == MANIFEST_FIELDS,
          'Migration manifest shape is invalid.')
  require(type(manifest['schemaVersion']) is int and manifest['schemaVersion'] == 1,
          'Migration manifest version is unsupported.')
  require(manifest['projectRef'] == PROJECT, 'Migration manifest targets another project.')
  require(type(manifest['evidenceBaseCommit']) is str
          and re.fullmatch(r'[a-f0-9]{40}', manifest['evidenceBaseCommit']),
          'Migration evidence base is invalid.')
  catalog = manifest['catalog']
  require(type(catalog) is list and len(catalog) == 52, 'Migration catalog differs from the reviewed scope.')
  names = []
  for row in catalog:
    require(type(row) is dict and set(row) == {'file', 'sha256'}, 'Catalog row is invalid.')
    migration_name(row['file'])
    require(type(row['sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', row['sha256']),
            'Catalog hash is invalid.')
    names.append(row['file'])
  require(names == sorted(set(names))
          and len({migration_name(name)['version'] for name in names}) == 52,
          'Migration catalog must be ordered with unique versions.')
  excluded = manifest['excludedMigrations']
  require(type(excluded) is list and len(excluded) == 1 and type(excluded[0]) is dict
          and set(excluded[0]) == {'file', 'sha256', 'reason'}
          and excluded[0]['file'] == AZURE_FILE and excluded[0]['sha256'] == AZURE_SHA256
          and type(excluded[0]['reason']) is str and bool(excluded[0]['reason'].strip()),
          'Only the reviewed Azure scaler exclusion is permitted.')
  require({'file': AZURE_FILE, 'sha256': AZURE_SHA256} in catalog,
          'Excluded migration does not match its catalog pin.')
  selected = manifest['selectedMigrations']
  require(selected == [name for name in names if name != AZURE_FILE],
          'Selected migrations must contain the complete reviewed MVP chain.')
  applied = validate_history_rows(manifest['observedHistory'])
  require(applied == selected[:21] and manifest['expectedPendingMigrations'] == selected[21:]
          and len(manifest['expectedPendingMigrations']) == 30,
          'Reviewed applied and pending migration boundaries are inconsistent.')
  config = manifest['sourceConfig']
  require(config is None or (type(config) is dict and set(config) == {'file', 'sha256'}
          and config['file'] == 'config.toml' and type(config['sha256']) is str
          and re.fullmatch(r'[a-f0-9]{64}', config['sha256'])), 'Source config pin is invalid.')


def prepare(source_root: Path, history_path: Path, destination: Path, manifest_path: Path | None = None):
  source_root = source_root.absolute()
  destination = destination.absolute()
  require(source_root.is_dir() and not source_root.is_symlink(), 'Source root must be a real directory.')
  supabase = source_root / 'supabase'
  migrations = supabase / 'migrations'
  require(supabase.is_dir() and migrations.is_dir()
          and not supabase.is_symlink() and not migrations.is_symlink(),
          'Source migration directories must be real directories.')
  require(not destination.exists() and not destination.is_symlink(), 'Destination already exists.')
  require(destination.parent.is_dir() and not destination.parent.is_symlink(),
          'Destination parent must be an existing real directory.')
  require(not destination.resolve().is_relative_to(source_root.resolve()),
          'Destination must be outside the source checkout.')
  manifest_path = manifest_path or source_root / 'config/web-mvp-migrations.json'
  manifest_bytes = read_regular(manifest_path)
  manifest = load_json(manifest_bytes)
  validate_manifest(manifest)
  catalog = manifest['catalog']
  require(sorted(path.name for path in migrations.iterdir()) == [row['file'] for row in catalog],
          'Source migration catalog has missing or unknown entries.')
  source_bytes = {}
  for row in catalog:
    data = read_regular(migrations / row['file'])
    require(digest(data) == row['sha256'], 'Source migration bytes differ from the reviewed catalog.')
    source_bytes[row['file']] = data
  config_path = supabase / 'config.toml'
  config = manifest['sourceConfig']
  config_bytes = None
  if config is None:
    require(not config_path.exists() and not config_path.is_symlink(), 'Unreviewed source config is present.')
  else:
    config_bytes = read_regular(config_path)
    require(digest(config_bytes) == config['sha256'], 'Source config differs from its reviewed pin.')
  history_bytes = read_regular(history_path)
  history = load_json(history_bytes)
  require(type(history) is dict and type(history.get('project')) is dict
          and history['project'].get('id') == PROJECT and history['project'].get('ref') == PROJECT,
          'History snapshot targets another project.')
  validate_history_rows(history.get('hostedMigrations'))
  require(history['hostedMigrations'] == manifest['observedHistory'],
          'Hosted history differs from the reviewed version and name pairs.')
  observed = history.get('observedAtUtc')
  require(type(observed) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', observed),
          'History observation timestamp is invalid.')
  try:
    datetime.fromisoformat(observed.replace('Z', '+00:00'))
  except ValueError:
    raise PreparationError('History observation timestamp is invalid.') from None
  receipt = {
    'schemaVersion': 1, 'authorization': 'local-preparation-only', 'projectRef': PROJECT,
    'evidenceBaseCommit': manifest['evidenceBaseCommit'],
    'manifestSha256': digest(manifest_bytes), 'historySnapshotSha256': digest(history_bytes),
    'historyObservedAtUtc': observed, 'observedHistory': history['hostedMigrations'],
    'sourceCatalog': catalog,
    'sourceCatalogSha256': digest(json.dumps(catalog, sort_keys=True, separators=(',', ':')).encode()),
    'sourceConfigSha256': digest(config_bytes) if config_bytes is not None else None,
    'selectedMigrations': [row for row in catalog if row['file'] in manifest['selectedMigrations']],
    'pendingMigrations': manifest['expectedPendingMigrations'], 'excludedMigrations': manifest['excludedMigrations'],
    'providerMutation': False, 'migrationHistoryModified': False,
    'liveHistoryVerified': False, 'dryRunVerified': False, 'restoreRehearsalVerified': False,
    'migrationsApplied': False, 'launchComplete': False,
  }
  # Exclusive creation prevents overwriting even if a destination appears after validation.
  # A failed write leaves an incomplete directory without a completed receipt.
  destination.mkdir(mode=0o700)
  target = destination / 'supabase/migrations'
  target.mkdir(parents=True, mode=0o700)
  for name in manifest['selectedMigrations']:
    with (target / name).open('xb') as output:
      output.write(source_bytes[name])
  if config_bytes is not None:
    with (destination / 'supabase/config.toml').open('xb') as output:
      output.write(config_bytes)
  for row in receipt['selectedMigrations']:
    require(digest(read_regular(target / row['file'])) == row['sha256'],
            'Prepared migration readback differs from its reviewed pin.')
  if config_bytes is not None:
    require(read_regular(destination / 'supabase/config.toml') == config_bytes,
            'Prepared config readback differs from its reviewed pin.')
  with (destination / 'preparation-receipt.json').open('x') as output:
    json.dump(receipt, output, indent=2)
    output.write('\n')
  return receipt


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
  parser.add_argument('--history', type=Path, required=True, help='Read-only hosted-history JSON snapshot.')
  parser.add_argument('--destination', type=Path, required=True, help='New directory outside the source checkout.')
  parser.add_argument('--manifest', type=Path)
  args = parser.parse_args(argv)
  try:
    receipt = prepare(args.source_root, args.history, args.destination, args.manifest)
  except (PreparationError, OSError) as error:
    message = str(error) if isinstance(error, PreparationError) else 'Cannot read or exclusively create the preparation files.'
    print('Migration preparation failed: ' + message, file=sys.stderr)
    return 1
  print(json.dumps({'prepared': True, 'selectedMigrations': len(receipt['selectedMigrations']),
                    'pendingMigrations': len(receipt['pendingMigrations']), 'providerMutation': False}))
  return 0


if __name__ == '__main__':
  sys.exit(main())
