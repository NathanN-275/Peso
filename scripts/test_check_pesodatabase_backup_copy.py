import contextlib
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory
import unittest

from check_pesodatabase_backup_copy import PROJECT, SQL_FILES, main


class BackupCopyTests(unittest.TestCase):
  def setUp(self):
    cleanup = TemporaryDirectory()
    self.addCleanup(cleanup.cleanup)
    directory = Path(cleanup.name)
    self.original = directory / 'original.tar.gz'
    self.downloaded = directory / 'downloaded.tar.gz'
    self.inventory = directory / 'inventory.json'

  def prepare(self, objects=None, changes=None, extra=None):
    objects = objects or {}
    rows = [{
      'bucket': 'videos', 'key': f'private-object-{index}', 'archiveFile': name,
      'sizeBytes': len(data), 'sha256': sha256(data).hexdigest(),
    } for index, (name, data) in enumerate(objects.items())]
    inventory = json.dumps({'projectRef': PROJECT, 'objects': rows}).encode()
    self.inventory.write_bytes(inventory)
    sql = {name: ('-- export ' + name).encode() for name in sorted(SQL_FILES)}
    manifest = ''.join(f'{sha256(content).hexdigest()}  {name}\n' for name, content in sql.items()).encode()
    files = {
      'snapshot.json': b'{}', 'source-catalog.private.json': b'{}',
      'sql/SHA256SUMS': manifest, 'storage-inventory.json': inventory,
      **{f'sql/{name}': content for name, content in sql.items()}, **objects,
    }
    for name, data in (changes or {}).items():
      if data is None:
        del files[name]
      else:
        files[name] = data
    with tarfile.open(self.original, 'w:gz') as archive:
      for name, data in files.items():
        member = tarfile.TarInfo(name)
        member.size = len(data)
        archive.addfile(member, BytesIO(data))
      if extra is not None:
        archive.addfile(extra)
    shutil.copyfile(self.original, self.downloaded)

  def run_check(self, downloaded=None):
    stdout, stderr = StringIO(), StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
      code = main(['--original', str(self.original), '--downloaded', str(downloaded or self.downloaded),
                   '--inventory', str(self.inventory)])
    return code, stdout.getvalue(), stderr.getvalue()

  def test_verifies_empty_inventory_and_zero_byte_legacy_object(self):
    for objects in ({}, {'storage/00000001.bin': b'', 'storage/00000002.bin': b'abc'}):
      with self.subTest(count=len(objects)):
        self.prepare(objects)
        code, stdout, stderr = self.run_check()
        self.assertEqual((code, stderr), (0, ''))
        result = json.loads(stdout)
        self.assertEqual(result['archiveSha256'], sha256(self.downloaded.read_bytes()).hexdigest())
        self.assertEqual(result['storageInventorySha256'], sha256(self.inventory.read_bytes()).hexdigest())
        self.assertEqual(result['storageObjects'], len(objects))
        self.assertEqual(result['storageBytes'], sum(map(len, objects.values())))
        self.assertEqual(result['sqlFiles'], 6)
        self.assertNotIn('private-object', stdout)

  def test_rejects_wrong_sql_or_incomplete_or_changed_storage(self):
    name = 'storage/00000001.bin'
    for changes in ({'sql/data.sql': b'bad dump'}, {name: b'xyz'}, {name: None},
                    {'storage/00000002.bin': b'uninventoried'}, {'storage-inventory.json': b'{}'}):
      with self.subTest(changes=tuple(changes)):
        self.prepare({name: b'abc'}, changes)
        code, stdout, stderr = self.run_check()
        self.assertEqual((code, stdout), (1, ''))
        self.assertNotIn(name, stderr)

  def test_rejects_duplicate_path_and_links(self):
    duplicate = tarfile.TarInfo('./sql/data.sql')
    link = tarfile.TarInfo('verification-receipt.json')
    link.type = tarfile.SYMTYPE
    link.linkname = '/private-target'
    for member in (duplicate, link, tarfile.TarInfo('../unexpected')):
      with self.subTest(member=member.name):
        self.prepare(extra=member)
        self.assertEqual(self.run_check()[0], 1)

  def test_rejects_same_file_wrong_download_and_invalid_gzip_trailer(self):
    self.prepare()
    self.assertEqual(self.run_check(self.original)[0], 1)
    content = self.original.read_bytes()
    altered = content[:-1] + bytes([content[-1] ^ 1])
    self.downloaded.write_bytes(altered)
    self.assertEqual(self.run_check()[0], 1)
    self.original.write_bytes(altered)
    self.assertEqual(self.run_check()[0], 1)
