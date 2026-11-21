#!/usr/bin/env python3
"""Verify the local production recovery archive and its downloaded copy."""
import argparse
import gzip
from hashlib import file_digest
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import zlib

from prepare_web_mvp_migrations import PROJECT, PreparationError, digest, load_json, require


SQL_FILES = {
  'roles.sql', 'schema.sql', 'auth_storage_schema.sql', 'data.sql',
  'history_schema.sql', 'history_data.sql',
}
SQL_MANIFEST = 'sql/SHA256SUMS'
INVENTORY_FILE = 'storage-inventory.json'
METADATA_FILES = {'snapshot.json', 'source-catalog.private.json'}
OPTIONAL_FILE = 'verification-receipt.json'


def storage_inventory(data):
  inventory = load_json(data)
  require(type(inventory) is dict and set(inventory) == {'projectRef', 'objects'}
          and inventory['projectRef'] == PROJECT and type(inventory['objects']) is list,
          'Storage inventory has the wrong format or production project.')
  objects = {}
  identities = set()
  for row in inventory['objects']:
    require(type(row) is dict and set(row) == {'bucket', 'key', 'archiveFile', 'sizeBytes', 'sha256'}
            and all(type(row[field]) is str and row[field] for field in ('bucket', 'key', 'archiveFile', 'sha256'))
            and re.fullmatch(r'storage/[0-9]{8}\.bin', row['archiveFile'])
            and type(row['sizeBytes']) is int and row['sizeBytes'] >= 0
            and re.fullmatch(r'[0-9a-f]{64}', row['sha256']),
            'Storage inventory contains an invalid object entry.')
    identity = (row['bucket'], row['key'])
    require(identity not in identities and row['archiveFile'] not in objects,
            'Storage inventory contains a repeated object or archive member.')
    identities.add(identity)
    objects[row['archiveFile']] = (row['sizeBytes'], row['sha256'])
  return objects


def sql_manifest(data):
  expected = {}
  for line in data.decode('ascii').splitlines():
    match = re.fullmatch(r'([0-9a-f]{64})  ([a-z_]+\.sql)', line)
    require(match is not None, 'SQL checksum manifest has an invalid line.')
    checksum, filename = match.groups()
    require(filename not in expected, 'SQL checksum manifest repeats a filename.')
    expected[filename] = checksum
  require(set(expected) == SQL_FILES, 'SQL checksum manifest must cover all six reviewed dumps.')
  return expected


def verify_members(downloaded, inventory_bytes, objects):
  expected = METADATA_FILES | {SQL_MANIFEST, INVENTORY_FILE} | {
    'sql/' + filename for filename in SQL_FILES
  } | objects.keys()
  seen = set()
  files = {}
  manifest_bytes = b''
  with gzip.GzipFile(fileobj=downloaded) as compressed:
    with tarfile.open(fileobj=compressed, mode='r:') as archive:
      for member in archive:
        name = member.name.removeprefix('./')
        require(name not in seen, 'Archive contains a repeated member.')
        seen.add(name)
        if member.isdir() and name in {'.', 'sql', 'storage'}:
          require(member.size == 0, 'Archive directory contains unexpected data.')
          continue
        require((name in expected or name == OPTIONAL_FILE)
                and member.type in (tarfile.REGTYPE, tarfile.AREGTYPE) and member.sparse is None,
                'Archive contains an unexpected or non-regular member.')
        if name in objects:
          require(member.size == objects[name][0], 'Archived object size differs from the inventory.')
        else:
          require(member.size > 0, 'Archive contains an empty required evidence file.')
        with archive.extractfile(member) as payload:
          if name == SQL_MANIFEST:
            require(member.size <= 4096, 'SQL checksum manifest is too large.')
            manifest_bytes = payload.read()
            files[name] = (member.size, digest(manifest_bytes))
          else:
            files[name] = (member.size, file_digest(payload, 'sha256').hexdigest())
      # TAR iteration stops at the first zero header. Read through the gzip trailer
      # to verify it and reject any additional data after the expected members.
      compressed.seek(archive.offset)
      padding = 0
      while block := compressed.read(1024 * 1024):
        require(not block.strip(b'\0'), 'Archive contains data after the final member.')
        padding += len(block)
      require(padding >= 1024 and padding % 512 == 0, 'Archive is missing valid end padding.')

  require(expected <= files.keys(), 'Archive is missing a required member.')
  require(files[INVENTORY_FILE] == (len(inventory_bytes), digest(inventory_bytes)),
          'Archived Storage inventory differs from the independent copy.')
  require(all(files[name] == checksum for name, checksum in objects.items()),
          'Archived object checksum differs from the inventory.')
  require(all(files['sql/' + name][1] == checksum for name, checksum in sql_manifest(manifest_bytes).items()),
          'Archived SQL checksum differs from the manifest.')
  return files[SQL_MANIFEST][1]


def open_local_file(path):
  return os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb')


def verify(original_path, downloaded_path, inventory_path):
  with open_local_file(inventory_path) as inventory:
    require(stat.S_ISREG(os.fstat(inventory.fileno()).st_mode), 'Storage inventory must be a regular file.')
    inventory_bytes = inventory.read()
  objects = storage_inventory(inventory_bytes)
  with open_local_file(original_path) as original, open_local_file(downloaded_path) as downloaded:
    first = os.fstat(original.fileno())
    second = os.fstat(downloaded.fileno())
    require(stat.S_ISREG(first.st_mode) and stat.S_ISREG(second.st_mode)
            and not os.path.samestat(first, second),
            'Original and downloaded archives must be distinct regular files.')
    require(first.st_size > 0 and first.st_size == second.st_size, 'Archive sizes differ or are empty.')
    archive_hash = file_digest(original, 'sha256').hexdigest()
    require(file_digest(downloaded, 'sha256').hexdigest() == archive_hash, 'Archive checksums differ.')
    downloaded.seek(0)
    manifest_hash = verify_members(downloaded, inventory_bytes, objects)
    for stream, before in ((original, first), (downloaded, second)):
      after = os.fstat(stream.fileno())
      require((before.st_size, before.st_mtime_ns, before.st_ctime_ns)
              == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
              'An archive changed during verification.')
  return {
    'archiveBytes': first.st_size,
    'archiveSha256': archive_hash,
    'sqlFiles': len(SQL_FILES),
    'sqlManifestSha256': manifest_hash,
    'storageObjects': len(objects),
    'storageBytes': sum(size for size, _ in objects.values()),
    'storageInventorySha256': digest(inventory_bytes),
  }


def main(argv=None):
  parser = argparse.ArgumentParser(
    description=__doc__,
    epilog='Verify production target, writer freeze, and protected download provenance independently.',
  )
  parser.add_argument('--original', type=Path, required=True)
  parser.add_argument('--downloaded', type=Path, required=True)
  parser.add_argument('--inventory', type=Path, required=True)
  args = parser.parse_args(argv)
  try:
    result = verify(args.original, args.downloaded, args.inventory)
  except PreparationError as error:
    print('Backup copy check failed. ' + str(error), file=sys.stderr)
    return 1
  except (OSError, ValueError, EOFError, OverflowError, RecursionError, tarfile.TarError, zlib.error):
    print('Backup copy check failed. Could not read valid local evidence.', file=sys.stderr)
    return 1
  print(json.dumps(result))
  return 0


if __name__ == '__main__':
  sys.exit(main())
