"""Standard-library fixtures only. No hosted calls, credentials or SQL execution."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('prepare_web_mvp_migrations', Path(__file__).with_name('prepare_web_mvp_migrations.py'))
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
ROOT = Path(__file__).resolve().parents[1]


class PrepareWebMvpMigrationsTest(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(prefix='peso-mvp-migrations-')
    self.addCleanup(self.temp.cleanup)
    self.base = Path(self.temp.name)
    self.source = self.base / 'source'
    self.source.mkdir()
    shutil.copytree(ROOT / 'supabase/migrations', self.source / 'supabase/migrations')
    (self.source / 'config').mkdir()
    self.manifest_path = self.source / 'config/web-mvp-migrations.json'
    shutil.copy2(ROOT / 'config/web-mvp-migrations.json', self.manifest_path)
    self.manifest = json.loads(self.manifest_path.read_text())
    self.history = {'observedAtUtc': '2026-11-05T17:29:28Z',
                    'project': {'id': PREPARE.PROJECT, 'ref': PREPARE.PROJECT},
                    'hostedMigrations': copy.deepcopy(self.manifest['observedHistory'])}
    self.history_path = self.base / 'hosted-history.json'
    self.history_path.write_text(json.dumps(self.history))
    self.destination = self.base / 'prepared'

  def prepare(self):
    return PREPARE.prepare(self.source, self.history_path, self.destination)

  def save_history(self):
    self.history_path.write_text(json.dumps(self.history))

  def save_manifest(self):
    self.manifest_path.write_text(json.dumps(self.manifest))

  def denied(self):
    with self.assertRaises((PREPARE.PreparationError, OSError)):
      self.prepare()
    self.assertFalse(self.destination.exists())

  def test_prepares_all_selected_bytes_and_exact_order_without_azure_or_linkage(self):
    receipt = self.prepare()
    paths = self.destination / 'supabase/migrations'
    self.assertEqual(sorted(p.name for p in paths.iterdir()), self.manifest['selectedMigrations'])
    self.assertEqual(len(list(paths.iterdir())), 51)
    self.assertFalse((paths / PREPARE.AZURE_FILE).exists())
    for row in receipt['selectedMigrations']:
      self.assertEqual((paths / row['file']).read_bytes(),
                       (self.source / 'supabase/migrations' / row['file']).read_bytes())
      self.assertEqual(PREPARE.digest((paths / row['file']).read_bytes()), row['sha256'])
    self.assertEqual(receipt['pendingMigrations'], self.manifest['expectedPendingMigrations'])
    self.assertEqual(len(receipt['pendingMigrations']), 30)
    self.assertEqual(receipt['observedHistory'], self.manifest['observedHistory'])
    self.assertEqual(receipt['manifestSha256'], PREPARE.digest(self.manifest_path.read_bytes()))
    self.assertEqual(receipt['historySnapshotSha256'], PREPARE.digest(self.history_path.read_bytes()))
    self.assertEqual(receipt['evidenceBaseCommit'], self.manifest['evidenceBaseCommit'])
    self.assertIsNone(receipt['sourceConfigSha256'])
    self.assertEqual(sorted(str(p.relative_to(self.destination)) for p in self.destination.rglob('*') if p.is_file()),
                     sorted(['preparation-receipt.json'] + ['supabase/migrations/' + f for f in self.manifest['selectedMigrations']]))
    for key in ('providerMutation', 'migrationHistoryModified', 'liveHistoryVerified', 'dryRunVerified',
                'restoreRehearsalVerified', 'migrationsApplied', 'launchComplete'):
      self.assertIs(receipt[key], False)
    self.assertEqual(json.loads((self.destination / 'preparation-receipt.json').read_text()), receipt)

  def test_superseded_azure_draft_and_source_linkage_are_never_staged(self):
    (self.source / 'supabase/.temp').mkdir()
    (self.source / 'supabase/.temp/project-ref').write_text('untrusted-project')
    (self.source / 'supabase/security-cutover.sql').write_text('select false;')
    self.prepare()
    self.assertFalse((self.destination / 'supabase/.temp').exists())
    self.assertFalse((self.destination / 'supabase/security-cutover.sql').exists())

  def test_wrong_project_id_or_ref_is_denied(self):
    for field in ('id', 'ref'):
      with self.subTest(field=field):
        self.history['project'] = {'id': PREPARE.PROJECT, 'ref': PREPARE.PROJECT}
        self.history['project'][field] = 'another-project'
        self.save_history(); self.denied()

  def test_missing_history_file_or_rows_is_denied(self):
    self.history_path.unlink(); self.denied()
    self.history.pop('hostedMigrations'); self.save_history(); self.denied()

  def test_unknown_or_excluded_applied_version_is_denied(self):
    for row in ({'version': '202699990001', 'name': 'unreviewed'}, PREPARE.migration_name(PREPARE.AZURE_FILE)):
      with self.subTest(row=row):
        self.history['hostedMigrations'] = copy.deepcopy(self.manifest['observedHistory']) + [row]
        self.save_history(); self.denied()
        self.history['hostedMigrations'] = copy.deepcopy(self.manifest['observedHistory'])
        self.history['hostedMigrations'][-1] = row
        self.save_history(); self.denied()

  def test_changed_names_partial_duplicate_or_reordered_history_is_denied(self):
    original = copy.deepcopy(self.manifest['observedHistory'])
    changed = copy.deepcopy(original); changed[0]['name'] += '_changed'
    cases = [changed, original[:-1], original[::-1], original[:-1] + [original[0]],
             [dict(row, unexpected=True) for row in original]]
    for rows in cases:
      with self.subTest(rows=rows):
        self.history['hostedMigrations'] = rows; self.save_history(); self.denied()

  def test_history_timestamp_is_required_and_is_not_claimed_fresh(self):
    for observed in (None, '', 'yesterday', '2026-11-99T17:29:28Z', '2026-11-05T17:29:28'):
      with self.subTest(observed=observed):
        self.history['observedAtUtc'] = observed; self.save_history(); self.denied()
    self.history['observedAtUtc'] = '2020-01-01T00:00:00Z'; self.save_history()
    receipt = self.prepare()
    self.assertEqual(receipt['historyObservedAtUtc'], '2020-01-01T00:00:00Z')
    self.assertIs(receipt['liveHistoryVerified'], False)

  def test_modified_selected_or_excluded_source_is_denied(self):
    for file in (self.manifest['selectedMigrations'][-1], PREPARE.AZURE_FILE):
      with self.subTest(file=file):
        path = self.source / 'supabase/migrations' / file; original = path.read_bytes()
        path.write_bytes(original + b'\n-- unreviewed\n'); self.denied(); path.write_bytes(original)

  def test_missing_source_or_unknown_sql_or_subdirectory_is_denied(self):
    path = self.source / 'supabase/migrations' / self.manifest['selectedMigrations'][0]
    original = path.read_bytes(); path.unlink(); self.denied(); path.write_bytes(original)
    extra = self.source / 'supabase/migrations/20261105000000_unreviewed.sql'
    extra.write_text('select true;'); self.denied(); extra.unlink()
    extra.mkdir(); self.denied()

  def test_symlink_source_file_directory_history_and_manifest_are_denied(self):
    path = self.source / 'supabase/migrations' / self.manifest['selectedMigrations'][0]
    copy_path = self.base / 'copy.sql'; original = path.read_bytes(); copy_path.write_bytes(original)
    path.unlink(); path.symlink_to(copy_path); self.denied(); path.unlink(); path.write_bytes(original)
    for path in (self.history_path, self.manifest_path):
      original = path.read_bytes(); copy_path.write_bytes(original)
      path.unlink(); path.symlink_to(copy_path); self.denied(); path.unlink(); path.write_bytes(original)
    migrations = self.source / 'supabase/migrations'
    moved = self.base / 'migrations'; migrations.rename(moved); migrations.symlink_to(moved, target_is_directory=True)
    self.denied()

  def test_named_pipe_source_or_history_is_rejected_without_opening_it(self):
    paths = [self.source / 'supabase/migrations' / self.manifest['selectedMigrations'][0], self.history_path]
    for path in paths:
      with self.subTest(path=path):
        original = path.read_bytes(); path.unlink(); os.mkfifo(path)
        self.denied(); path.unlink(); path.write_bytes(original)

  def test_existing_destination_is_preserved_and_never_overwritten(self):
    self.destination.mkdir(); marker = self.destination / 'marker'; marker.write_text('keep')
    with self.assertRaises(PREPARE.PreparationError): self.prepare()
    self.assertEqual(marker.read_text(), 'keep')
    self.assertEqual(list(self.destination.iterdir()), [marker])

  def test_destination_symlink_or_inside_source_is_denied(self):
    target = self.base / 'untouched'; target.mkdir()
    self.destination.symlink_to(target, target_is_directory=True)
    with self.assertRaises(PREPARE.PreparationError): self.prepare()
    self.assertEqual(list(target.iterdir()), [])
    self.destination.unlink(); self.destination = self.source / 'generated'
    self.denied()

  def test_late_destination_creation_does_not_overwrite(self):
    original_mkdir = Path.mkdir
    def race(path, *args, **kwargs):
      if path == self.destination:
        original_mkdir(path)
        (path / 'marker').write_text('keep')
      return original_mkdir(path, *args, **kwargs)
    with patch.object(Path, 'mkdir', race), self.assertRaises(FileExistsError): self.prepare()
    self.assertEqual((self.destination / 'marker').read_text(), 'keep')
    self.assertFalse((self.destination / 'preparation-receipt.json').exists())

  def test_manifest_cannot_omit_shared_sql_or_select_azure_or_change_baseline(self):
    original = copy.deepcopy(self.manifest)
    cases = []
    changed = copy.deepcopy(original); changed['selectedMigrations'] = changed['selectedMigrations'][:-1]; cases.append(changed)
    changed = copy.deepcopy(original); changed['selectedMigrations'] = [r['file'] for r in changed['catalog']]; cases.append(changed)
    changed = copy.deepcopy(original); changed['excludedMigrations'][0]['file'] = changed['selectedMigrations'][-1]; cases.append(changed)
    changed = copy.deepcopy(original); changed['expectedPendingMigrations'] = changed['expectedPendingMigrations'][::-1]; cases.append(changed)
    changed = copy.deepcopy(original); changed['observedHistory'][0]['name'] += '_changed'; cases.append(changed)
    changed = copy.deepcopy(original); changed['projectRef'] = 'another-project'; cases.append(changed)
    for manifest in cases:
      with self.subTest(manifest=manifest):
        self.manifest = manifest; self.save_manifest(); self.denied()

  def test_duplicate_json_keys_and_boolean_schema_version_are_denied(self):
    original = self.manifest_path.read_bytes()
    self.manifest_path.write_bytes(b'{"schemaVersion":1,' + original[1:]); self.denied()
    self.manifest_path.write_bytes(original)
    self.manifest['schemaVersion'] = True; self.save_manifest(); self.denied()
    self.manifest_path.write_bytes(original)
    original_history = self.history_path.read_bytes()
    self.history_path.write_bytes(b'{"project":{},' + original_history[1:]); self.denied()

  def test_unreviewed_source_config_or_config_symlink_is_denied(self):
    path = self.source / 'supabase/config.toml'; path.write_text('project_id = "unreviewed"\n')
    self.denied(); path.unlink(); path.symlink_to(self.history_path); self.denied()

  def test_explicitly_pinned_source_config_is_copied_byte_exactly(self):
    path = self.source / 'supabase/config.toml'; data = b'project_id = "synthetic-local-config"\n'; path.write_bytes(data)
    self.manifest['sourceConfig'] = {'file': 'config.toml', 'sha256': PREPARE.digest(data)}; self.save_manifest()
    receipt = self.prepare()
    self.assertEqual((self.destination / 'supabase/config.toml').read_bytes(), data)
    self.assertEqual(receipt['sourceConfigSha256'], PREPARE.digest(data))

  def test_pinned_config_modification_is_denied(self):
    path = self.source / 'supabase/config.toml'; path.write_text('project_id = "changed"\n')
    self.manifest['sourceConfig'] = {'file': 'config.toml', 'sha256': PREPARE.digest(b'original')}; self.save_manifest()
    self.denied()

  def test_failed_prepared_file_readback_cannot_write_a_completion_receipt(self):
    original_read = PREPARE.read_regular
    def corrupt_readback(path, *args, **kwargs):
      if path.is_relative_to(self.destination):
        return b'unexpected bytes'
      return original_read(path, *args, **kwargs)
    with patch.object(PREPARE, 'read_regular', corrupt_readback), self.assertRaises(PREPARE.PreparationError):
      self.prepare()
    self.assertTrue(self.destination.is_dir())
    self.assertFalse((self.destination / 'preparation-receipt.json').exists())

  def test_cli_outputs_only_counts_and_ignores_unneeded_snapshot_metadata(self):
    self.history['privateMetadata'] = 'PRIVATE_SENTINEL_NOT_FOR_RECEIPT'
    self.save_history(); output = io.StringIO()
    with contextlib.redirect_stdout(output):
      result = PREPARE.main(['--source-root', str(self.source), '--history', str(self.history_path),
                             '--destination', str(self.destination)])
    self.assertEqual(result, 0)
    self.assertEqual(json.loads(output.getvalue()), {'prepared': True, 'selectedMigrations': 51,
                     'pendingMigrations': 30, 'providerMutation': False})
    self.assertNotIn('PRIVATE_SENTINEL', (self.destination / 'preparation-receipt.json').read_text())

  def test_cli_rejection_creates_no_destination_and_no_traceback(self):
    self.history['project']['id'] = 'PRIVATE_SENTINEL'; self.save_history(); output = io.StringIO()
    with contextlib.redirect_stderr(output):
      result = PREPARE.main(['--source-root', str(self.source), '--history', str(self.history_path),
                             '--destination', str(self.destination)])
    self.assertEqual(result, 1)
    self.assertNotIn('PRIVATE_SENTINEL', output.getvalue())
    self.assertNotIn('Traceback', output.getvalue())
    self.assertFalse(self.destination.exists())


if __name__ == '__main__':
  unittest.main()
