#!/usr/bin/env python3
"""Read-only pre-cutover checks. Never print provider output or input values.

The sole write is an exclusively created, private, redacted JSON report.
Provider observations are operator attestations, not independently fetched facts.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

PROJECT = "jfgiydtrskpqxyorvvbc"
URL = f"https://{PROJECT}.supabase.co"
SERVICES = ("srv-dak9ohfqj5pc73ac2ga0", "srv-dak9ohfqj5pc73ac2g8g")
DEPLOYED_COMMIT = "4325798f4a4bd7a8f8d55587c5520a5cf9c014d3"
PENDING = (
    "202608300001_azure_analysis_queue_scaler.sql",
    "202609030001_upload_reservations.sql",
    "202609210001_unsaved_video_retention.sql",
    "202609210002_retention_deletion_outbox.sql",
    "20260922002632_intake_stop_reason.sql",
    "20260922003008_us_ip_beta_admission.sql",
    "20260923224101_budget_alert_delivery.sql",
)
BACKUP_FILES = (
    "roles.sql", "schema.sql", "auth_storage_schema.sql", "data.sql",
    "history_schema.sql", "history_data.sql",
)
MAX_AGE = timedelta(minutes=60)
TOP_FIELDS = {
    "observed_at", "freeze_at", "backup_completed_at", "backup_project_ref",
    "backup_manifest_sha256", "second_copy", "source_commit", "blueprint_sha256",
    "budget_workflow_disabled", "quota_healthy", "counts", "services",
    "managed_schema_customizations_verified",
}
SERVICE_FIELDS = {
    "environment", "supabase_url", "credential_project_ref", "credentials_verified",
    "suspended", "auto_deploy", "deployed_commit",
}
COUNT_FIELDS = {"videos", "active_uploads", "active_analysis_jobs", "reservations", "storage_objects"}


def exact_fields(value, fields):
    return type(value) is dict and set(value) == set(fields)


def timestamp(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("invalid timestamp")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def private_path(path, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    return (kind(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600))


def outside_repo(path, repo):
    return not path.resolve().is_relative_to(repo.resolve())


def command(args, repo):
    result = subprocess.run(args, cwd=repo, capture_output=True, text=True,
                            timeout=45, env={**os.environ, "NO_COLOR": "1"})
    if result.returncode:
        raise ValueError("command failed")
    return result.stdout + "\n" + result.stderr


def provider_lines(output):
    # Allow known CLI framing only. New CLI diagnostics block for review.
    framing = (
        "Initialising login role...", "Initializing login role...",
        "Connecting to remote database...", "Finished supabase migration list.",
        "Finished supabase db push.", "Would push these migrations:",
        "DRY RUN: migrations will *not* be pushed to the database.",
    )
    if len(output) > 65536:
        raise ValueError("oversized output")
    return [line.strip() for line in output.splitlines()
            if line.strip() and line.strip() not in framing]


def parse_history(output):
    rows = []
    for line in provider_lines(output):
        if re.fullmatch(r"Local\s*\|\s*Remote\s*\|\s*Time \(UTC\)", line):
            continue
        if re.fullmatch(r"[-+| ]+", line):
            continue
        match = re.fullmatch(r"(\d{12,14})\s*\|\s*(\d{12,14})?\s*\|\s*[0-9 :+-]*", line)
        if not match:
            raise ValueError("unexpected provider output")
        rows.append(match.groups())
    if not rows:
        raise ValueError("empty history")
    return rows


def parse_dry_run(output):
    files = []
    for line in provider_lines(output):
        match = re.fullmatch(r"[•*\-]\s+(\d{12,14}_[a-z0-9_]+\.sql)", line)
        if not match:
            raise ValueError("unexpected provider output")
        files.append(match.group(1))
    return tuple(files)


def load_observations(path, repo):
    if (not private_path(path) or not private_path(path.parent, directory=True)
            or not outside_repo(path, repo) or path.stat().st_size > 65536):
        raise ValueError("unsafe observations")

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate key")
            obj[key] = value
        return obj

    obj = json.loads(path.read_text(), object_pairs_hook=unique)
    if not exact_fields(obj, TOP_FIELDS):
        raise ValueError("unexpected fields")
    if not exact_fields(obj["counts"], COUNT_FIELDS):
        raise ValueError("unexpected counts")
    if not exact_fields(obj["second_copy"], {"verified_at", "manifest_sha256", "off_machine"}):
        raise ValueError("unexpected copy fields")
    if not exact_fields(obj["services"], SERVICES):
        raise ValueError("unexpected services")
    for service in obj["services"].values():
        if not exact_fields(service, SERVICE_FIELDS):
            raise ValueError("unexpected service fields")
    return obj


def check(repo, backup, observations, now=None, run=None):
    now = now or datetime.now(timezone.utc)
    run = run or command
    checks = {}
    artifacts = {}

    def probe(name, fn):
        try:
            passed = bool(fn())
        except Exception:
            # Do not interpolate exception text, paths, rows, CLI output or credentials.
            passed = False
        checks[name] = "pass" if passed else "blocked"
        return passed

    obs = {}

    def read_observations():
        obs.update(load_observations(observations, repo))
        return True

    probe("observation_schema_and_privacy", read_observations)
    linked = probe("linked_project", lambda: repo.joinpath("supabase/.temp/project-ref").read_text().strip() == PROJECT)
    files = sorted(p.name for p in repo.joinpath("supabase/migrations").glob("*.sql"))
    versions = [name.split("_")[0] for name in files]
    local_ok = probe("repository_migration_chain", lambda: len(files) == 28
                     and tuple(files[-7:]) == PENDING and versions[20] == "202608270001")
    history_ok = False
    if linked and local_ok:
        def history():
            nonlocal history_ok
            rows = parse_history(run(["supabase", "migration", "list", "--linked"], repo))
            history_ok = rows == [(v, v if i < 21 else None) for i, v in enumerate(versions)]
            return history_ok
        probe("live_migration_history", history)
    else:
        checks["live_migration_history"] = "blocked"
    if history_ok:
        probe("live_migration_dry_run", lambda: parse_dry_run(run(
            ["supabase", "db", "push", "--linked", "--dry-run"], repo)) == PENDING)
    else:
        checks["live_migration_dry_run"] = "blocked"

    def source():
        commit = run(["git", "rev-parse", "HEAD"], repo).strip()
        if not re.fullmatch(r"[a-f0-9]{40}", commit) or obs["source_commit"] != commit:
            return False
        run(["git", "diff", "--quiet", "HEAD", "--", "supabase/migrations", "render-public-beta.yaml"], repo)
        blueprint = digest(repo / "render-public-beta.yaml")
        if blueprint != obs["blueprint_sha256"]:
            return False
        artifacts.update(source_commit=commit, blueprint_sha256=blueprint)
        return True
    probe("reviewed_source_and_blueprint", source)

    def backup_layout():
        return (outside_repo(backup, repo) and private_path(backup, directory=True)
                and set(p.name for p in backup.iterdir()) == set(BACKUP_FILES) | {"SHA256SUMS"}
                and all(private_path(backup / name) and (backup / name).stat().st_size > 0
                        for name in (*BACKUP_FILES, "SHA256SUMS")))
    backup_ok = probe("backup_layout_and_permissions", backup_layout)
    manifest_digest = None
    if backup_ok:
        def verify_hashes():
            nonlocal manifest_digest
            manifest = backup / "SHA256SUMS"
            if manifest.stat().st_size > 4096:
                return False
            hashes = {}
            for line in manifest.read_text().splitlines():
                match = re.fullmatch(r"([a-f0-9]{64})  ([a-z_]+\.sql)", line)
                if not match or match[2] in hashes:
                    return False
                hashes[match[2]] = match[1]
            if set(hashes) != set(BACKUP_FILES):
                return False
            if not all(digest(backup / name) == hashes[name] for name in BACKUP_FILES):
                return False
            manifest_digest = digest(manifest)
            if obs["backup_manifest_sha256"] != manifest_digest or obs["backup_project_ref"] != PROJECT:
                return False
            artifacts["backup_manifest_sha256"] = manifest_digest
            return True
        probe("backup_checksums_and_target_attestation", verify_hashes)
    else:
        checks["backup_checksums_and_target_attestation"] = "blocked"

    def freshness():
        observed, frozen, completed = (timestamp(obs[key]) for key in
                                       ("observed_at", "freeze_at", "backup_completed_at"))
        if not now - MAX_AGE <= frozen <= completed <= observed <= now:
            return False
        return backup_ok and all(frozen.timestamp() <= (backup / name).stat().st_mtime
                                 <= completed.timestamp() for name in (*BACKUP_FILES, "SHA256SUMS"))
    probe("fresh_backup_after_freeze_attestation", freshness)
    probe("second_copy_attestation", lambda: manifest_digest is not None
          and obs["second_copy"]["off_machine"] is True
          and obs["second_copy"]["manifest_sha256"] == manifest_digest
          and timestamp(obs["backup_completed_at"]) <= timestamp(obs["second_copy"]["verified_at"])
          <= timestamp(obs["observed_at"]) <= now)
    probe("work_and_storage_counts_attestation", lambda: all(
        (value is None and key == "reservations" and history_ok)
        or (type(value) is int and value == 0) for key, value in obs["counts"].items()))
    probe("budget_disabled_attestation", lambda: obs["budget_workflow_disabled"] is True)
    probe("quota_healthy_attestation", lambda: obs["quota_healthy"] is True)
    probe("managed_schema_recovery_attestation", lambda: obs["managed_schema_customizations_verified"] is True)
    for i, service_id in enumerate(SERVICES):
        def binding():
            service = obs["services"][service_id]
            return (service["environment"] == "production" and service["supabase_url"] == URL
                    and service["credential_project_ref"] == PROJECT
                    and service["credentials_verified"] is True)
        def held():
            service = obs["services"][service_id]
            return (service["suspended"] is True and service["auto_deploy"] == "off"
                    and service["deployed_commit"] == DEPLOYED_COMMIT)
        probe(f"render_{i + 1}_binding_attestation", binding)
        probe(f"render_{i + 1}_suspension_and_commit_attestation", held)

    return {
        "format_version": 1, "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_ref": PROJECT, "finding": "CHECKS_PASSED" if all(v == "pass" for v in checks.values()) else "BLOCKED",
        "authorization": "none", "max_age_minutes": 60, "checks": checks,
        "verified_local_artifacts": artifacts,
        "expected_deployed_commit": DEPLOYED_COMMIT,
        "limitations": ["provider_and_backup_provenance_require_operator_attestation",
                        "not_a_runtime_or_restore_test", "recheck_in_approved_cutover_window"],
    }


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid arguments; use --help.\n")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # Reject unsafe destinations before connecting to any provider.
        if (not outside_repo(args.output, args.repo) or args.output.exists() or args.output.is_symlink()
                or not private_path(args.output.parent, directory=True)):
            raise ValueError("unsafe report destination")
        report = check(args.repo, args.backup, args.observations)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(report["finding"])
        return 0 if report["finding"] == "CHECKS_PASSED" else 1
    except Exception:
        print("BLOCKED: unable to complete private evidence report.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
