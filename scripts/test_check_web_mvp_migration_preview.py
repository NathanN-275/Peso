"""Local migration workspace and transcript fixtures only."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import check_web_mvp_migration_preview as checker
from prepare_web_mvp_migrations import AZURE_FILE, PROJECT, PreparationError, digest, prepare


ROOT = Path(__file__).resolve().parents[1]
UPGRADE_ADVICE = [
  'A new version of Supabase CLI is available: v3.0.0 (currently installed v2.98.2)',
  'We recommend updating regularly for new features and bug fixes: '
  'https://supabase.com/docs/guides/cli/getting-started#updating-the-supabase-cli',
]


class CheckWebMvpMigrationPreviewTest(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory(prefix='peso-mvp-preview-')
    self.addCleanup(temp.cleanup)
    base = Path(temp.name)
    self.workspace = base / 'workspace'
    manifest = json.loads((ROOT / 'config/web-mvp-migrations.json').read_bytes())
    history = base / 'history.json'
    history.write_text(json.dumps({
      'observedAtUtc': '2026-11-05T17:29:28Z',
      'project': {'id': PROJECT, 'ref': PROJECT},
      'hostedMigrations': manifest['observedHistory'],
    }))
    self.receipt = prepare(ROOT, history, self.workspace)
    self.migrations = self.workspace / 'supabase/migrations'
    self.link = self.workspace / 'supabase/.temp/project-ref'
    self.link.parent.mkdir()
    self.link.write_text(PROJECT)
    self.log = base / 'preview.log'
    self.lines = ['DRY RUN: migrations will *not* be pushed to the database.',
                  'Connecting to remote database...', 'Would push these migrations:',
                  *(f' • {name}' for name in manifest['expectedPendingMigrations']),
                  'Finished supabase db push.']
    self.write_log(self.lines)

  def write_log(self, lines):
    self.log.write_text('\n'.join(lines) + '\n', encoding='utf-8')

  def verify(self):
    return checker.verify(self.workspace, self.log)

  def test_confirms_exact_preview_and_hashes_original_bytes(self):
    self.assertEqual(self.verify(), {
      'dryRunLogSha256': digest(self.log.read_bytes()),
      'pendingMigrations': 30,
    })

  def test_accepts_known_upgrade_advice_as_exact_optional_suffix(self):
    self.write_log(self.lines + UPGRADE_ADVICE)
    self.assertEqual(self.verify()['dryRunLogSha256'], digest(self.log.read_bytes()))

    self.write_log(self.lines + UPGRADE_ADVICE[:-1])
    with self.assertRaisesRegex(PreparationError, 'Dry-run log'):
      self.verify()

  def test_rejects_receipt_drift(self):
    receipt_path = self.workspace / 'preparation-receipt.json'
    for field, changed in (
        ('schemaVersion', True),
        ('projectRef', 'staging-project'),
        ('manifestSha256', '0' * 64),
        ('pendingMigrations', list(reversed(self.receipt['pendingMigrations']))),
        ('selectedMigrations', self.receipt['selectedMigrations'][:-1]),
    ):
      with self.subTest(field=field):
        receipt_path.write_text(json.dumps({**self.receipt, field: changed}))
        with self.assertRaisesRegex(PreparationError, 'Preparation receipt'):
          self.verify()

  def test_rejects_wrong_or_symlinked_link_marker(self):
    self.link.write_text('staging-project')
    with self.assertRaisesRegex(PreparationError, 'Local link marker'):
      self.verify()
    self.link.unlink()
    marker = self.log.parent / 'other-marker'
    marker.write_text(PROJECT)
    self.link.symlink_to(marker)
    with self.assertRaisesRegex(PreparationError, 'Symlink input'):
      self.verify()

  def test_rejects_azure_and_changed_or_missing_migration_bytes(self):
    azure = self.migrations / AZURE_FILE
    azure.write_text('select 1;')
    with self.assertRaisesRegex(PreparationError, 'migration directory'):
      self.verify()
    azure.unlink()
    first = self.migrations / self.receipt['selectedMigrations'][0]['file']
    first.write_text('select 1;')
    with self.assertRaisesRegex(PreparationError, 'migration bytes'):
      self.verify()
    first.unlink()
    with self.assertRaisesRegex(PreparationError, 'migration directory'):
      self.verify()

  def test_rejects_missing_markers_unknown_diagnostics_and_a_different_plan(self):
    for lines in (
        self.lines[1:],
        self.lines[:1] + self.lines[2:],
        self.lines[:2] + self.lines[3:],
        self.lines[:-1],
        ['Unexpected diagnostic'] + self.lines,
        self.lines[:3] + list(reversed(self.lines[3:-1])) + self.lines[-1:],
        self.lines[:3] + [f' • {AZURE_FILE}'] + self.lines[3:],
    ):
      with self.subTest(lines=lines[:4]):
        self.write_log(lines)
        with self.assertRaisesRegex(PreparationError, 'Dry-run log'):
          self.verify()

  def test_rejects_preview_that_initialized_a_login_role(self):
    for message in ('Initialising login role...', 'Initializing login role...'):
      with self.subTest(message=message):
        self.write_log([message, *self.lines])
        with self.assertRaisesRegex(PreparationError, 'Dry-run log'):
          self.verify()

  def test_cli_reports_only_digest_count_or_sanitized_failure(self):
    args = ['--workspace', str(self.workspace), '--dry-run-log', str(self.log)]
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
      self.assertEqual(checker.main(args), 0)
    self.assertEqual(json.loads(output.getvalue()), self.verify())

    self.write_log(['synthetic-untrusted-output'])
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
      self.assertEqual(checker.main(args), 1)
    self.assertIn('Migration preview check failed', errors.getvalue())
    self.assertNotIn('synthetic-untrusted-output', errors.getvalue())

    self.log.unlink()
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
      self.assertEqual(checker.main(args), 1)
    self.assertIn('Migration preview check failed', errors.getvalue())
    self.assertNotIn(str(self.log), errors.getvalue())


if __name__ == '__main__':
  unittest.main()
