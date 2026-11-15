"""Offline behavior checks for the US-IP refresh trust boundaries."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import io
import ipaddress
import json
import os
import sys
import tempfile
from pathlib import Path
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import refresh_us_ip_dataset as refresh


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
RELEASE = "2026-10"
DEADLINE = datetime(2026, 11, 5, tzinfo=timezone.utc)
PROJECT = "jfgiydtrskpqxyorvvbc"
BASE_ROWS = [
    ("8.8.8.3", "8.8.8.6", "US"),
    ("8.8.8.7", "8.8.8.7", "CA"),
    ("2606:4700::1111", "2606:4700::1111", "US"),
]


def csv_bytes(rows=BASE_ROWS):
    return "".join(",".join(row) + "\n" for row in rows).encode()


def compressed(rows=BASE_ROWS, *, mtime=0):
    return gzip.compress(csv_bytes(rows), mtime=mtime)


def sorted_rows(rows):
    return sorted(rows, key=lambda row: (ipaddress.ip_address(row[0]).version,
                                        int(ipaddress.ip_address(row[0]))))


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class ParserTests(unittest.TestCase):
    def setUp(self):
        # Keep production completeness thresholds unchanged; these are tiny fixtures.
        for name, value in (("MIN_ROWS", 2), ("MIN_US_ROWS_PER_FAMILY", 1),
                            ("MIN_COUNTRIES", 1)):
            patcher = mock.patch.object(refresh, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def parse(self, rows=BASE_ROWS, **kwargs):
        return refresh.parse_dataset(compressed(rows), RELEASE, now=NOW, **kwargs)

    def test_exact_cidrs_preserve_country_boundaries_and_both_families(self):
        dataset = self.parse()
        self.assertEqual(dataset.networks,
                         ("8.8.8.3/32", "8.8.8.4/31", "8.8.8.6/32",
                          "2606:4700::1111/128"))
        admitted = [ipaddress.ip_network(net) for net in dataset.networks]
        for address in ("8.8.8.2", "8.8.8.7", "2606:4700::1110",
                        "2606:4700::1112"):
            ip = ipaddress.ip_address(address)
            self.assertFalse(any(ip.version == net.version and ip in net for net in admitted))
        self.assertEqual(dataset.rows, 3)
        self.assertEqual(dataset.us_rows, {4: 1, 6: 1})
        self.assertEqual(dataset.excluded_cidrs, 0)
        self.assertEqual(dataset.sha256, hashlib.sha256(compressed()).hexdigest())
        self.assertEqual(dataset.valid_until, DEADLINE)

    def test_rejects_malformed_csv_and_ranges(self):
        bad_rows = [
            [("start", "end", "country")],
            [("8.8.8.8", "8.8.8.8")],
            [("8.8.8.8", "8.8.8.8", "US", "extra")],
            [("8.8.8.8", "8.8.8.8", "us")],
            [("8.8.8.8", "8.8.8.8", "USA")],
            [("999.8.8.8", "999.8.8.8", "US")],
            [("8.8.8.9", "8.8.8.8", "US")],
            [("8.8.8.8", "2606:4700::1111", "US")],
        ]
        for rows in bad_rows:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.parse(rows)
        for raw in (b'"8.8.8.8,8.8.8.8,US\n', b"\xff\n", b"x" * 129 + b",x,US\n"):
            with self.subTest(raw=raw[:20]), self.assertRaises(Exception):
                refresh.parse_dataset(gzip.compress(raw), RELEASE, now=NOW)

    def test_rejects_overlaps_duplicates_and_out_of_order_rows(self):
        invalid = [
            [("8.8.8.0", "8.8.8.8", "CA"), ("8.8.8.8", "8.8.8.9", "US")],
            [BASE_ROWS[0], BASE_ROWS[0]],
            [BASE_ROWS[1], BASE_ROWS[0]],
            [BASE_ROWS[2], BASE_ROWS[0]],
            [("2606:4700::1", "2606:4700::3", "CA"),
             ("2606:4700::2", "2606:4700::4", "US")],
        ]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.parse(rows)

    def test_missing_families_and_truncated_population_are_rejected(self):
        for rows in (BASE_ROWS[:2], BASE_ROWS[2:],
                     [BASE_ROWS[0], ("2606:4700::1111", "2606:4700::1111", "CA")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.parse(rows)
        for threshold, value in (("MIN_ROWS", 4), ("MIN_COUNTRIES", 3),
                                 ("MIN_US_ROWS_PER_FAMILY", 2)):
            with self.subTest(threshold=threshold), mock.patch.object(refresh, threshold, value):
                with self.assertRaises(ValueError):
                    self.parse()

    def test_special_purpose_addresses_never_become_admission_networks(self):
        excluded = [
            "0.0.0.0", "10.1.2.3", "100.64.0.1", "127.0.0.1", "169.254.1.1",
            "172.16.0.1", "192.0.0.9", "192.0.2.1", "192.31.196.1",
            "192.52.193.1", "192.88.99.1", "192.168.1.1", "192.175.48.1",
            "198.18.0.1", "198.51.100.1", "203.0.113.1", "224.0.0.1",
            "239.255.255.255", "240.0.0.1", "255.255.255.255", "::", "::1",
            "::ffff:8.8.8.8", "100::1", "2001::1", "2001:20::1", "2001:db8::1",
            "2002:808:808::1", "2620:4f:8000::1", "3fff::1", "fc00::1", "fe80::1", "ff02::1",
        ]
        rows = [BASE_ROWS[0], BASE_ROWS[2]] + [(ip, ip, "US") for ip in excluded]
        dataset = self.parse(sorted_rows(rows))
        self.assertEqual(dataset.networks, self.parse([BASE_ROWS[0], BASE_ROWS[2]]).networks)
        self.assertEqual(dataset.excluded_cidrs, len(excluded))

    def test_dataset_must_have_public_us_networks_in_each_family(self):
        rows = [("10.0.0.1", "10.0.0.1", "US"), BASE_ROWS[2]]
        with self.assertRaises(ValueError):
            self.parse(rows)
        rows = [BASE_ROWS[0], ("2002::1", "2002::1", "US")]
        with self.assertRaises(ValueError):
            self.parse(rows)

    def test_ipv4_special_block_subtraction_preserves_public_neighbors(self):
        rows = [("192.52.192.0", "192.52.195.255", "US"), BASE_ROWS[2]]
        dataset = self.parse(rows)
        self.assertEqual(set(dataset.networks),
                         {"192.52.192.0/24", "192.52.194.0/23", "2606:4700::1111/128"})
        self.assertEqual(dataset.excluded_cidrs, 1)

    def test_ipv6_special_block_subtraction_preserves_exact_surrounding_range(self):
        whole = ipaddress.ip_network("2620:4f:8000::/34")
        special = ipaddress.ip_network("2620:4f:8000::/48")
        dataset = self.parse([BASE_ROWS[0],
                              (str(whole.network_address), str(whole.broadcast_address), "US")])
        networks = [ipaddress.ip_network(net) for net in dataset.networks
                    if ipaddress.ip_network(net).version == 6]
        self.assertTrue(all(net.subnet_of(whole) and not net.overlaps(special)
                            for net in networks))
        self.assertEqual(sum(net.num_addresses for net in networks),
                         whole.num_addresses - special.num_addresses)
        for neighbor in ("2620:4f:8001::1", "2620:4f:bfff::1"):
            self.assertTrue(any(ipaddress.ip_address(neighbor) in net for net in networks))
        self.assertEqual(dataset.excluded_cidrs, 1)

    def test_compressed_size_limit_is_inclusive(self):
        body = compressed()
        with mock.patch.object(refresh, "MAX_COMPRESSED_BYTES", len(body)):
            self.assertEqual(refresh.parse_dataset(body, RELEASE, now=NOW).rows, 3)
        with mock.patch.object(refresh, "MAX_COMPRESSED_BYTES", len(body) - 1):
            with self.assertRaisesRegex(ValueError, "Compressed"):
                refresh.parse_dataset(body, RELEASE, now=NOW)
        with self.assertRaisesRegex(ValueError, "Compressed"):
            refresh.parse_dataset(b"", RELEASE, now=NOW)

    def test_expanded_size_limit_is_inclusive_and_blocks_compression_bombs(self):
        with mock.patch.object(refresh, "MAX_CSV_BYTES", len(csv_bytes())):
            self.assertEqual(self.parse().rows, 3)
        with mock.patch.object(refresh, "MAX_CSV_BYTES", len(csv_bytes()) - 1):
            with self.assertRaisesRegex(ValueError, "Expanded"):
                self.parse()
        with mock.patch.object(refresh, "MAX_CSV_BYTES", 16):
            with self.assertRaisesRegex(ValueError, "Expanded"):
                refresh.parse_dataset(gzip.compress(b"\n" * 2048), RELEASE, now=NOW)

    def test_truncated_and_corrupted_archives_are_rejected(self):
        body = compressed()
        corrupt_crc = body[:-8] + bytes([body[-8] ^ 1]) + body[-7:]
        for damaged in (b"not gzip", body[:-1], body[:len(body) // 2], corrupt_crc):
            with self.subTest(size=len(damaged)), self.assertRaises((OSError, EOFError)):
                refresh.parse_dataset(damaged, RELEASE, now=NOW)

    def test_network_count_limit_is_enforced(self):
        with mock.patch.object(refresh, "MAX_NETWORKS", 3):
            with self.assertRaisesRegex(ValueError, "Too many"):
                self.parse()

    def test_redownload_does_not_extend_release_expiry(self):
        original = refresh.parse_dataset(compressed(mtime=0), RELEASE,
                                         now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        redownload = refresh.parse_dataset(compressed(mtime=1), RELEASE,
                                           now=DEADLINE - timedelta(microseconds=1))
        self.assertNotEqual(original.sha256, redownload.sha256)
        self.assertEqual(original.valid_until, redownload.valid_until)
        self.assertEqual(redownload.valid_until, DEADLINE)
        with self.assertRaises(ValueError):
            refresh.parse_dataset(compressed(mtime=1), RELEASE, now=DEADLINE)


class ReleaseWindowTests(unittest.TestCase):
    def test_exact_35_day_window_and_exclusive_expiry(self):
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.assertEqual(refresh.release_window(RELEASE, start), start + timedelta(days=35))
        self.assertEqual(refresh.release_window(RELEASE, DEADLINE - timedelta(microseconds=1)), DEADLINE)
        for now in (start - timedelta(microseconds=1), DEADLINE,
                    DEADLINE + timedelta(microseconds=1), NOW.replace(tzinfo=None)):
            with self.subTest(now=now), self.assertRaises(ValueError):
                refresh.release_window(RELEASE, now)

    def test_release_is_a_month_not_an_arbitrary_download_path(self):
        for release in ("2026-00", "2026-13", "2026-1", "2026-10/../../secret",
                        "https://example.com/file", "2026-10\n", "2026-11"):
            with self.subTest(release=release), self.assertRaises(ValueError):
                refresh.release_window(release, NOW)


class DatabaseConnectionTests(unittest.TestCase):
    def setUp(self):
        psycopg = types.ModuleType("psycopg")
        psycopg.connect = mock.Mock(return_value=object())
        conninfo = types.ModuleType("psycopg.conninfo")
        conninfo.conninfo_to_dict = mock.Mock()
        self.connect = psycopg.connect
        self.decode = conninfo.conninfo_to_dict
        patcher = mock.patch.dict(sys.modules, {"psycopg": psycopg, "psycopg.conninfo": conninfo})
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {"PESO_GEO_DATABASE_URL": "fixture-only-no-real-credential"}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.direct = {"host": f"db.{PROJECT}.supabase.co", "user": "postgres",
                       "dbname": "postgres", "password": "synthetic-password"}

    def test_reviewed_direct_and_session_pooler_require_tls_verification(self):
        for values in (self.direct,
                       dict(self.direct, host="aws-0-us-east-1.pooler.supabase.com",
                            user=f"postgres.{PROJECT}", port="5432", sslmode="disable")):
            with self.subTest(host=values["host"]):
                self.decode.return_value = dict(values)
                refresh.connect_database()
                self.assertEqual(self.connect.call_args.kwargs,
                                 dict(values, port="5432", sslmode="verify-full", sslrootcert="system",
                                      connect_timeout=15, autocommit=True, prepare_threshold=None))

    def test_other_projects_hosts_ports_databases_and_connection_overrides_are_rejected(self):
        invalid = [
            {"host": "db.anotherproject.supabase.co"}, {"user": f"postgres.{PROJECT}"},
            {"host": "db." + PROJECT + ".supabase.co.evil.example"},
            {"host": "aws-0-us-east-1.pooler.supabase.com", "user": "postgres.anotherproject"},
            {"host": "aws-0-us-east-1.pooler.supabase.com", "user": "postgres"},
            {"host": "aws-0-us-east-1.pooler.supabase.com.evil.example", "user": f"postgres.{PROJECT}"},
            {"port": "6543"}, {"dbname": "other"}, {"hostaddr": "127.0.0.1"},
            {"options": "-c search_path=attacker"}, {"service": "other"},
            {"sslrootcert": "/tmp/untrusted-cert"},
        ]
        for overrides in invalid:
            self.decode.return_value = dict(self.direct, **overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                refresh.connect_database()
        self.connect.assert_not_called()

    def test_missing_credential_never_attempts_connection(self):
        os.environ.pop("PESO_GEO_DATABASE_URL")
        with self.assertRaises(ValueError):
            refresh.connect_database()
        self.decode.assert_not_called()
        self.connect.assert_not_called()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(refresh, "datetime", FrozenDatetime)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = f"https://download.db-ip.com/free/dbip-country-lite-{RELEASE}.csv.gz"

    def response(self, data, url=None):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.url = self.url if url is None else url
        response.read.return_value = data
        return response

    def test_only_official_release_url_and_bounded_download_are_used(self):
        response = self.response(b"1234")
        with mock.patch.object(refresh, "urlopen", return_value=response) as fetch:
            with mock.patch.object(refresh, "MAX_COMPRESSED_BYTES", 4):
                self.assertEqual(refresh.download(RELEASE), b"1234")
        fetch.assert_called_once_with(self.url, timeout=45)
        response.read.assert_called_once_with(5)

    def test_redirect_and_oversized_downloads_are_rejected(self):
        redirected = self.response(b"fixture", url="https://unreviewed.example/file.gz")
        with mock.patch.object(refresh, "urlopen", return_value=redirected):
            with self.assertRaisesRegex(ValueError, "redirect"):
                refresh.download(RELEASE)
        redirected.read.assert_not_called()
        response = self.response(b"12345")
        with mock.patch.object(refresh, "urlopen", return_value=response):
            with mock.patch.object(refresh, "MAX_COMPRESSED_BYTES", 4):
                with self.assertRaisesRegex(ValueError, "too large"):
                    refresh.download(RELEASE)
        response.read.assert_called_once_with(5)

    def test_invalid_future_or_expired_release_never_fetches(self):
        for release in ("2026-10/../../file", "2026-11", "2026-09"):
            with self.subTest(release=release), mock.patch.object(refresh, "urlopen") as fetch:
                with self.assertRaises(ValueError):
                    refresh.download(release)
                fetch.assert_not_called()


class ReplacementStateTests(unittest.TestCase):
    def test_same_compressed_bytes_cannot_be_relabeled_to_extend_expiry(self):
        dataset = refresh.Dataset(RELEASE, "a" * 64, DEADLINE,
                                  ("8.8.8.8/32", "2606:4700::1111/128"),
                                  2, {4: 1, 6: 1}, 0)
        connection = mock.MagicMock()
        connection.execute.side_effect = [
            mock.Mock(), mock.Mock(), mock.Mock(),
            mock.Mock(fetchone=mock.Mock(return_value=(NOW,))),
            mock.Mock(fetchall=mock.Mock(return_value=[
                (f"dbip-country-lite/2026-09/{dataset.sha256}",
                 datetime(2026, 10, 6, tzinfo=timezone.utc))])),
        ]
        with self.assertRaisesRegex(ValueError, "review"):
            refresh.replace_dataset(connection, dataset)
        connection.cursor.assert_not_called()
        self.assertFalse(any(call.args[0].startswith(("delete ", "insert "))
                             for call in connection.execute.call_args_list))


class MainTests(unittest.TestCase):
    def run_main(self, data, *, apply=False, failure=None, local=False, replace_failure=None, evidence_failure=None, manifest_path=None):
        argv = ["refresh_us_ip_dataset.py", "--release", RELEASE]
        self.evidence_dir = tempfile.TemporaryDirectory(prefix="peso-geo-evidence-")
        self.addCleanup(self.evidence_dir.cleanup)
        self.manifest_path = Path(manifest_path) if manifest_path else Path(self.evidence_dir.name) / "manifest.json"
        self.evidence_calls = []
        if apply:
            argv.extend(("--apply", "--manifest", str(self.manifest_path)))
        if local:
            argv.extend(("--input", "fixture-only.csv.gz"))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", argv))
            stack.enter_context(mock.patch.object(refresh, "datetime", FrozenDatetime))
            stack.enter_context(mock.patch.multiple(refresh, MIN_ROWS=2, MIN_US_ROWS_PER_FAMILY=1, MIN_COUNTRIES=1))
            download = stack.enter_context(mock.patch.object(refresh, "download", return_value=data))
            if local:
                stack.enter_context(mock.patch.object(refresh.Path, "open", return_value=io.BytesIO(data)))
            connection = stack.enter_context(mock.patch.object(refresh, "connect_database", side_effect=failure))
            replace = stack.enter_context(mock.patch.object(refresh, "replace_dataset", side_effect=replace_failure))
            original_write = refresh.write_evidence
            def write(path, record):
                self.evidence_calls.append((path, record))
                if evidence_failure == "input" or evidence_failure == "result" and path != self.manifest_path:
                    raise OSError("synthetic private database password must never reach output")
                return original_write(path, record)
            stack.enter_context(mock.patch.object(refresh, "write_evidence", side_effect=write))
            stack.enter_context(contextlib.redirect_stdout(stdout))
            stack.enter_context(contextlib.redirect_stderr(stderr))
            result = refresh.main()
            if local:
                download.assert_not_called()
        return result, stdout.getvalue(), stderr.getvalue(), connection, replace

    def test_validation_only_outputs_manifest_without_connecting(self):
        status, stdout, stderr, connection, replace = self.run_main(compressed())
        self.assertEqual(status, 1)  # This frozen run is within seven days of expiry.
        self.assertEqual(stderr, "")
        manifest = json.loads(stdout)
        self.assertFalse(manifest["applied"])
        self.assertTrue(manifest["warning_expiring_within_7_days"])
        self.assertEqual(manifest["valid_until"], DEADLINE.isoformat())
        self.assertEqual(manifest["us_cidrs"], 4)
        self.assertEqual(manifest["source_us_rows"], {"4": 1, "6": 1})
        self.assertEqual(manifest["retrieval"], "official_https")
        connection.assert_not_called()
        replace.assert_not_called()

    def test_local_validation_with_explicit_release_is_marked_unverified(self):
        status, stdout, stderr, connection, replace = self.run_main(compressed(), local=True)
        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        manifest = json.loads(stdout)
        self.assertEqual(manifest["retrieval"], "local_unverified")
        self.assertFalse(manifest["applied"])
        connection.assert_not_called()
        replace.assert_not_called()

    def test_local_input_requires_release_and_never_allows_apply(self):
        invalid = [
            ["--input", "fixture-only.csv.gz"],
            ["--input", "fixture-only.csv.gz", "--apply"],
            ["--input", "fixture-only.csv.gz", "--release", RELEASE, "--apply"],
        ]
        for args in invalid:
            with self.subTest(args=args), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(sys, "argv", ["refresh_us_ip_dataset.py", *args]))
                fetch = stack.enter_context(mock.patch.object(refresh, "download"))
                opened = stack.enter_context(mock.patch.object(refresh.Path, "open"))
                connection = stack.enter_context(mock.patch.object(refresh, "connect_database"))
                replace = stack.enter_context(mock.patch.object(refresh, "replace_dataset"))
                stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                with self.assertRaises(SystemExit) as error:
                    refresh.main()
                self.assertEqual(error.exception.code, 2)
                fetch.assert_not_called()
                opened.assert_not_called()
                connection.assert_not_called()
                replace.assert_not_called()

    def test_failed_parse_never_connects_even_with_apply(self):
        for body in (b"not gzip", compressed(BASE_ROWS[:2])):
            with self.subTest(body=body[:10]):
                status, stdout, stderr, connection, replace = self.run_main(body, apply=True)
                self.assertEqual(status, 1)
                self.assertEqual(stdout, "")
                self.assertIn("US-IP refresh failed", stderr)
                connection.assert_not_called()
                replace.assert_not_called()

    def test_database_failure_is_sanitized(self):
        secret = "postgresql://private-user:secret-password@private-host/private-db"
        status, stdout, stderr, connection, replace = self.run_main(
            compressed(), apply=True, failure=RuntimeError(secret))
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertNotIn(secret, stderr)
        self.assertNotIn("secret-password", stderr)
        self.assertIn("US-IP refresh failed", stderr)
        connection.assert_called_once_with()
        replace.assert_not_called()


    def test_apply_requires_manifest_before_network_or_database_activity(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["refresh_us_ip_dataset.py", "--apply"]))
            fetch = stack.enter_context(mock.patch.object(refresh, "download"))
            connection = stack.enter_context(mock.patch.object(refresh, "connect_database"))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            with self.assertRaises(SystemExit) as error:
                refresh.main()
        self.assertEqual(error.exception.code, 2)
        fetch.assert_not_called()
        connection.assert_not_called()

    def test_lost_commit_reply_retains_exact_input_and_unknown_result_without_replay(self):
        dispatched = []
        def lost_reply(connection, dataset):
            # The immutable identity must be durable before dispatch, not emitted after success.
            prepared = json.loads(self.manifest_path.read_text())
            self.assertEqual(prepared["dataset"]["source_version"], dataset.source_version)
            dispatched.append(dataset.source_version)
            raise ConnectionError("postgresql://private-user:private-password@private-host/private-db")
        status, stdout, stderr, connection, replace = self.run_main(
            compressed(), apply=True, replace_failure=lost_reply)
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertNotIn("private-password", stderr)
        self.assertNotIn("postgresql", stderr)
        self.assertEqual(len(dispatched), 1)
        replace.assert_called_once()
        prepared = json.loads(self.manifest_path.read_text())
        result = json.loads(self.manifest_path.with_name("manifest.json.result.json").read_text())
        self.assertEqual(prepared["dataset"]["compressed_sha256"], hashlib.sha256(compressed()).hexdigest())
        self.assertEqual(prepared["dataset"]["valid_until"], DEADLINE.isoformat())
        self.assertEqual(prepared["retrieval"], "official_https")
        self.assertTrue(prepared["apply_requested"])
        self.assertEqual(prepared["apply_outcome"], "unconfirmed")
        self.assertEqual(result["apply_outcome"], "unknown")
        self.assertEqual(result["attempt_id"], prepared["attempt_id"])
        self.assertEqual(result["input_manifest_sha256"], hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())
        self.assertNotIn("private-password", self.manifest_path.read_text())
        self.assertNotIn("private-password", json.dumps(result))
        self.assertEqual(len(self.evidence_calls), 2)

    def test_retry_cannot_replace_prior_unknown_attempt_evidence_or_dispatch_again(self):
        status, stdout, stderr, _, replace = self.run_main(
            compressed(), apply=True, replace_failure=ConnectionError("synthetic lost reply"))
        self.assertEqual(status, 1)
        replace.assert_called_once()
        original_path = self.manifest_path
        original_manifest = original_path.read_bytes()
        original_result = original_path.with_name("manifest.json.result.json").read_bytes()
        status, stdout, stderr, connection, replace = self.run_main(
            compressed(), apply=True, manifest_path=original_path)
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        connection.assert_not_called()
        replace.assert_not_called()
        self.assertEqual(original_path.read_bytes(), original_manifest)
        self.assertEqual(original_path.with_name("manifest.json.result.json").read_bytes(), original_result)

    def test_input_evidence_failure_prevents_connecting_and_apply(self):
        status, stdout, stderr, connection, replace = self.run_main(
            compressed(), apply=True, evidence_failure="input")
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertNotIn("private database password", stderr)
        connection.assert_not_called()
        replace.assert_not_called()
        self.assertEqual(len(self.evidence_calls), 1)

    def test_file_or_directory_fsync_failure_prevents_database_dispatch(self):
        for failure_at in (1, 2):
            with self.subTest(failure_at=failure_at):
                calls = []
                def fail_sync(fd):
                    calls.append(fd)
                    if len(calls) == failure_at:
                        raise OSError("synthetic private sync error must stay sanitized")
                with mock.patch.object(refresh.os, "fsync", side_effect=fail_sync):
                    status, stdout, stderr, connection, replace = self.run_main(compressed(), apply=True)
                self.assertEqual(status, 1)
                self.assertEqual(stdout, "")
                self.assertIn("during evidence", stderr)
                self.assertNotIn("private sync error", stderr)
                self.assertEqual(len(calls), failure_at)
                connection.assert_not_called()
                replace.assert_not_called()
                # Partial durability never becomes permission to dispatch or overwrite.
                self.assertTrue(self.manifest_path.exists())
                self.assertFalse(self.manifest_path.with_name("manifest.json.result.json").exists())

    def test_result_write_failure_after_commit_stays_unconfirmed_without_retry(self):
        status, stdout, stderr, connection, replace = self.run_main(
            compressed(), apply=True, evidence_failure="result")
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("result_evidence", stderr)
        self.assertNotIn("private database password", stderr)
        replace.assert_called_once()
        self.assertEqual(len(self.evidence_calls), 2)
        prepared = json.loads(self.manifest_path.read_text())
        self.assertEqual(prepared["apply_outcome"], "unconfirmed")
        self.assertFalse(self.manifest_path.with_name("manifest.json.result.json").exists())
        self.assertNotIn("rollback", stderr)

    def test_acknowledged_apply_binds_committed_result_to_immutable_input(self):
        status, stdout, stderr, connection, replace = self.run_main(compressed(), apply=True)
        # Warning window still makes the job fail even after a confirmed commit.
        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertTrue(json.loads(stdout)["applied"])
        result = json.loads(self.manifest_path.with_name("manifest.json.result.json").read_text())
        self.assertEqual(result["apply_outcome"], "committed")
        self.assertEqual(result["input_manifest_sha256"], hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())
        replace.assert_called_once()


class EvidenceFileTests(unittest.TestCase):
    def test_input_cannot_overwrite_a_prior_attempt_or_follow_a_symlink(self):
        with tempfile.TemporaryDirectory(prefix="peso-geo-file-") as directory:
            path = Path(directory) / "manifest.json"
            first = {"source_version": "synthetic-only", "apply_outcome": "unconfirmed"}
            digest = refresh.write_evidence(path, first)
            original = path.read_bytes()
            self.assertEqual(digest, hashlib.sha256(original).hexdigest())
            with self.assertRaises(FileExistsError):
                refresh.write_evidence(path, {"apply_outcome": "committed"})
            self.assertEqual(path.read_bytes(), original)
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(FileExistsError):
                refresh.write_evidence(link, {"apply_outcome": "committed"})
            self.assertEqual(path.read_bytes(), original)


class WorkflowEvidenceTests(unittest.TestCase):
    def test_disabled_refresh_retains_scoped_evidence_after_success_or_failure(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/public-beta-geography.yml").read_text()
        self.assertIn("if: vars.PESO_PUBLIC_BETA_GEO_REFRESH_ENABLED == 'true'", workflow)
        self.assertIn("environment: public-beta-geography", workflow)
        self.assertIn("timeout-minutes: 10", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("id: geography_refresh", workflow)
        self.assertIn("--apply --manifest artifacts/us-ip-refresh/manifest.json", workflow)
        self.assertIn("always() && !cancelled()", workflow)
        self.assertIn("steps.geography_refresh.outcome == 'success'", workflow)
        self.assertIn("steps.geography_refresh.outcome == 'failure'", workflow)
        self.assertRegex(workflow, r"uses: actions/upload-artifact@[a-f0-9]{40}")
        self.assertIn("path: artifacts/us-ip-refresh/", workflow)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("upload-artifact@main", workflow)


if __name__ == "__main__":
    unittest.main()
