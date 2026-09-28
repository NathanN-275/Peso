"""No provider credentials or network: synthetic private-backup fixtures only."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_pesodatabase_precutover as checker

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
COMMIT = "a" * 40
SENTINEL = "sb_secret_PRIVATE_ROW_AND_CREDENTIAL_SENTINEL"


def stamp(delta=0):
    return (NOW + timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


class PrecutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.migrations = self.repo / "supabase/migrations"
        self.migrations.mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / "supabase/migrations"
        self.names = sorted(p.name for p in source.glob("*.sql"))
        for name in self.names:
            (self.migrations / name).write_text("-- fixture\n")
        self.link = self.repo / "supabase/.temp/project-ref"
        self.link.parent.mkdir()
        self.link.write_text(checker.PROJECT)
        (self.repo / "render-public-beta.yaml").write_text("# fixture\n")
        self.backup = self.root / "backup"
        self.backup.mkdir(mode=0o700)
        for name in checker.BACKUP_FILES:
            path = self.backup / name
            path.write_text("-- " + SENTINEL + "\n")
            path.chmod(0o600)
        self.manifest = self.backup / "SHA256SUMS"
        self.manifest.write_text("".join(
            f"{checker.digest(self.backup / name)}  {name}\n" for name in checker.BACKUP_FILES))
        self.manifest.chmod(0o600)
        for path in self.backup.iterdir():
            os.utime(path, (NOW.timestamp() - 120, NOW.timestamp() - 120))
        self.obs_path = self.root / "observations.json"
        self.obs = {
            "observed_at": stamp(), "freeze_at": stamp(-300), "backup_completed_at": stamp(-60),
            "backup_project_ref": checker.PROJECT,
            "backup_manifest_sha256": checker.digest(self.manifest),
            "second_copy": {"verified_at": stamp(-30), "off_machine": True,
                            "manifest_sha256": checker.digest(self.manifest)},
            "source_commit": COMMIT, "blueprint_sha256": checker.digest(self.repo / "render-public-beta.yaml"),
            "budget_workflow_disabled": True, "quota_healthy": True,
            "managed_schema_customizations_verified": True,
            "counts": {"videos": 0, "active_uploads": 0, "active_analysis_jobs": 0,
                       "reservations": None, "storage_objects": 0},
            "services": {service: {"environment": "production", "supabase_url": checker.URL,
                         "credential_project_ref": checker.PROJECT, "credentials_verified": True,
                         "suspended": True, "auto_deploy": "off", "deployed_commit": checker.DEPLOYED_COMMIT}
                         for service in checker.SERVICES},
        }
        self.save()
        self.history = "Initialising login role...\nConnecting to remote database...\nLocal | Remote | Time (UTC)\n---|---|---\n" + "\n".join(
            f"{name.split('_')[0]} | {name.split('_')[0] if i < 21 else ''} | 2026-09-23 00:00:00"
            for i, name in enumerate(self.names))
        self.dry_run = "DRY RUN: migrations will *not* be pushed to the database.\nWould push these migrations:\n" + "\n".join(
            " • " + name for name in checker.PENDING) + "\nFinished supabase db push.\n"
        self.calls = []

    def save(self):
        self.obs_path.write_text(json.dumps(self.obs))
        self.obs_path.chmod(0o600)

    def run_command(self, args, repo):
        self.calls.append(args)
        if args == ["supabase", "migration", "list", "--linked"]:
            return self.history
        if args == ["supabase", "db", "push", "--linked", "--dry-run"]:
            return self.dry_run
        if args == ["git", "rev-parse", "HEAD"]:
            return COMMIT + "\n"
        if args == ["git", "diff", "--quiet", "HEAD", "--", "supabase/migrations", "render-public-beta.yaml"]:
            return ""
        raise AssertionError("Unexpected command")

    def report(self):
        self.save()
        return checker.check(self.repo, self.backup, self.obs_path, NOW, self.run_command)

    def assert_blocked(self, name):
        result = self.report()
        self.assertEqual(result["finding"], "BLOCKED")
        self.assertEqual(result["checks"][name], "blocked")
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_matching_layout_and_provider_evidence_pass(self):
        result = self.report()
        self.assertEqual(result["finding"], "CHECKS_PASSED")
        self.assertEqual(result["authorization"], "none")
        self.assertEqual(result["verified_local_artifacts"]["source_commit"], COMMIT)
        self.assertEqual(result["verified_local_artifacts"]["backup_manifest_sha256"], checker.digest(self.manifest))
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertEqual(self.calls[:2], [["supabase", "migration", "list", "--linked"],
                                        ["supabase", "db", "push", "--linked", "--dry-run"]])

    def test_wrong_project_never_contacts_supabase(self):
        self.link.write_text("iseqgaewjpjcxrndibep")
        self.assert_blocked("linked_project")
        self.assertFalse(any(call[0] == "supabase" for call in self.calls))

    def test_reordered_or_partial_dry_run_blocks(self):
        for files in (checker.PENDING[::-1], checker.PENDING[:-1], checker.PENDING + checker.PENDING[:1]):
            with self.subTest(files=files):
                self.dry_run = "\n".join(" • " + name for name in files)
                self.assert_blocked("live_migration_dry_run")

    def test_changed_history_prevents_dry_run(self):
        self.history = self.history.replace("202608270001 | 202608270001", "202608270001 | 202608270002")
        self.assert_blocked("live_migration_history")
        self.assertFalse(any("push" in call for call in self.calls))

    def test_unknown_history_output_blocks_without_echo(self):
        self.history += "\n" + SENTINEL
        self.assert_blocked("live_migration_history")

    def test_unexpected_secret_or_row_in_dry_run_blocks_without_echo(self):
        for text in (SENTINEL, "nathan@example.invalid | private row", '{"password":"hidden"}'):
            with self.subTest(text=text):
                previous = self.dry_run
                self.dry_run += "\n" + text
                self.assert_blocked("live_migration_dry_run")
                self.dry_run = previous

    def test_missing_backup_file(self):
        (self.backup / "data.sql").unlink()
        self.assert_blocked("backup_layout_and_permissions")

    def test_stale_checksum(self):
        (self.backup / "data.sql").write_text("changed private data")
        self.assert_blocked("backup_checksums_and_target_attestation")

    def test_unsafe_file_and_directory_permissions(self):
        (self.backup / "data.sql").chmod(0o644)
        self.assert_blocked("backup_layout_and_permissions")
        (self.backup / "data.sql").chmod(0o600)
        self.backup.chmod(0o755)
        self.assert_blocked("backup_layout_and_permissions")

    def test_symlink_and_unexpected_file_rejected(self):
        path = self.backup / "data.sql"
        path.unlink()
        path.symlink_to(self.backup / "schema.sql")
        self.assert_blocked("backup_layout_and_permissions")

    def test_manifest_path_traversal_and_duplicates_rejected(self):
        original = self.manifest.read_text()
        for content in (original.replace("  data.sql", "  ../data.sql"), original + original.splitlines()[0] + "\n"):
            self.manifest.write_text(content)
            self.assert_blocked("backup_checksums_and_target_attestation")

    def test_stale_future_or_before_freeze_backup_blocks(self):
        for updates in ({"freeze_at": stamp(-3601)}, {"observed_at": stamp(1)},
                        {"freeze_at": stamp(-90)}, {"backup_completed_at": stamp(-301)}):
            with self.subTest(updates=updates):
                original = self.obs.copy()
                self.obs.update(updates)
                self.assert_blocked("fresh_backup_after_freeze_attestation")
                self.obs = original

    def test_second_copy_requires_matching_digest_and_attestation(self):
        self.obs["second_copy"]["manifest_sha256"] = "0" * 64
        self.assert_blocked("second_copy_attestation")

    def test_wrong_backup_project_blocks(self):
        self.obs["backup_project_ref"] = "iseqgaewjpjcxrndibep"
        self.assert_blocked("backup_checksums_and_target_attestation")

    def test_unrehearsed_managed_schema_customizations_block(self):
        self.obs["managed_schema_customizations_verified"] = False
        self.assert_blocked("managed_schema_recovery_attestation")

    def test_each_live_work_count_blocks_and_booleans_are_not_counts(self):
        for field in checker.COUNT_FIELDS:
            original = self.obs["counts"][field]
            for value in (1, -1, False, "0"):
                self.obs["counts"][field] = value
                self.assert_blocked("work_and_storage_counts_attestation")
            self.obs["counts"][field] = original

    def test_render_binding_credentials_and_service_hold_checked(self):
        for i, service in enumerate(checker.SERVICES):
            for field, value, check in (
                ("environment", "student", "binding"), ("supabase_url", "https://iseqgaewjpjcxrndibep.supabase.co", "binding"),
                ("credentials_verified", False, "binding"), ("credential_project_ref", "unknown", "binding"),
                ("suspended", False, "suspension_and_commit"), ("auto_deploy", "commit", "suspension_and_commit"),
                ("deployed_commit", "b" * 40, "suspension_and_commit"),
            ):
                with self.subTest(service=service, field=field):
                    original = self.obs["services"][service][field]
                    self.obs["services"][service][field] = value
                    self.assert_blocked(f"render_{i + 1}_{check}_attestation")
                    self.obs["services"][service][field] = original

    def test_candidate_digest_source_and_budget_drift_block(self):
        self.obs["blueprint_sha256"] = "b" * 64
        self.assert_blocked("reviewed_source_and_blueprint")
        self.obs["budget_workflow_disabled"] = False
        self.assert_blocked("budget_disabled_attestation")
        self.obs["quota_healthy"] = False
        self.assert_blocked("quota_healthy_attestation")

    def test_unknown_input_field_and_malformed_input_never_reflected(self):
        self.obs["password"] = SENTINEL
        self.assert_blocked("observation_schema_and_privacy")
        self.obs_path.write_text(SENTINEL)
        result = checker.check(self.repo, self.backup, self.obs_path, NOW, self.run_command)
        self.assertEqual(result["finding"], "BLOCKED")
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_cli_private_report_no_overwrite_and_no_provider_error_leak(self):
        output = self.root / "report.json"
        args = ["--repo", str(self.repo), "--backup", str(self.backup),
                "--observations", str(self.obs_path), "--output", str(output)]
        logs = io.StringIO()
        with patch.object(checker, "command", side_effect=RuntimeError(SENTINEL)), \
                contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            self.assertEqual(checker.main(args), 1)
            before = output.read_bytes()
            self.assertEqual(checker.main(args), 2)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(SENTINEL, output.read_text() + logs.getvalue())

    def test_cli_success_writes_only_redacted_evidence(self):
        output = self.root / "success.json"
        args = ["--repo", str(self.repo), "--backup", str(self.backup),
                "--observations", str(self.obs_path), "--output", str(output)]
        logs = io.StringIO()
        with patch.object(checker, "command", side_effect=self.run_command), \
                patch.object(checker, "datetime", wraps=datetime) as clock, \
                contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            clock.now.return_value = NOW
            self.assertEqual(checker.main(args), 0)
        self.assertEqual(logs.getvalue(), "CHECKS_PASSED\n")
        self.assertEqual(json.loads(output.read_text())["finding"], "CHECKS_PASSED")
        self.assertNotIn(SENTINEL, output.read_text())

    def test_unsafe_report_destination_never_runs_commands(self):
        args = ["--repo", str(self.repo), "--backup", str(self.backup),
                "--observations", str(self.obs_path), "--output", str(self.repo / "report.json")]
        with patch.object(checker, "command") as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(checker.main(args), 2)
        run.assert_not_called()

    def test_unrelated_worktree_files_are_untouched(self):
        user_file = self.repo / "CONTEXT.md"
        user_file.write_text("uncommitted user notes")
        self.assertEqual(self.report()["finding"], "CHECKS_PASSED")
        self.assertEqual(user_file.read_text(), "uncommitted user notes")

    def test_dirty_migration_or_blueprint_blocks(self):
        def dirty(args, repo):
            if args[:3] == ["git", "diff", "--quiet"]:
                raise ValueError("dirty tracked inputs")
            return self.run_command(args, repo)
        report = checker.check(self.repo, self.backup, self.obs_path, NOW, dirty)
        self.assertEqual(report["checks"]["reviewed_source_and_blueprint"], "blocked")

    def test_duplicate_json_keys_rejected(self):
        self.obs_path.write_text('{"observed_at":"one","observed_at":"two"}')
        with self.assertRaises(ValueError):
            checker.load_observations(self.obs_path, self.repo)

    def test_shipped_template_is_incomplete_and_blocks(self):
        template = Path(__file__).resolve().parents[1] / "config/pesodatabase-precutover-observations.example.json"
        self.obs = json.loads(template.read_text())
        report = self.report()
        self.assertEqual(report["checks"]["observation_schema_and_privacy"], "pass")
        self.assertEqual(report["finding"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
