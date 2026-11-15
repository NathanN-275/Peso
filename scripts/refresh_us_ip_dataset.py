"""Validate DB-IP Country Lite and atomically replace Peso's US admission ranges.

No hosted action occurs without --apply. Never log database credentials or errors.
Data: https://db-ip.com/db/lite.php (CC BY 4.0); transformed to US public unicast.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import ipaddress
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4


MAX_COMPRESSED_BYTES = 16 * 1024 * 1024
MAX_CSV_BYTES = 64 * 1024 * 1024
MIN_ROWS = 500_000
MIN_US_ROWS_PER_FAMILY = 1_000
MIN_COUNTRIES = 100
MAX_NETWORKS = 400_000
MAX_AGE = timedelta(days=35)
ALERT_BEFORE = timedelta(days=7)
VERSION = re.compile(r"dbip-country-lite/(\d{4}-(?:0[1-9]|1[0-2]))/([a-f0-9]{64})")

# Conservatively deny IANA special-purpose space, including globally routed
# anycast exceptions and transition mechanisms, for beta country admission.
EXCLUDED = {
    4: tuple(map(ipaddress.ip_network, (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
        "192.31.196.0/24", "192.52.193.0/24", "192.88.99.0/24", "192.168.0.0/16",
        "192.175.48.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
        "224.0.0.0/3",
    ))),
    6: tuple(map(ipaddress.ip_network, (
        "2001::/23", "2001:db8::/32", "2002::/16", "2620:4f:8000::/48", "3fff::/20",
    ))),
}
IPV6_UNICAST = ipaddress.ip_network("2000::/3")


@dataclass(frozen=True)
class Dataset:
    release: str
    sha256: str
    valid_until: datetime
    networks: tuple[str, ...]
    rows: int
    us_rows: dict[int, int]
    excluded_cidrs: int

    @property
    def source_version(self) -> str:
        return f"dbip-country-lite/{self.release}/{self.sha256}"

    def manifest(self) -> dict:
        return {"source": f"https://download.db-ip.com/free/dbip-country-lite-{self.release}.csv.gz",
                "license": "https://creativecommons.org/licenses/by/4.0/",
                "source_version": self.source_version, "compressed_sha256": self.sha256,
                "valid_until": self.valid_until.isoformat(),
                "source_rows": self.rows, "source_us_rows": self.us_rows,
                "us_cidrs": len(self.networks), "excluded_special_purpose_cidrs": self.excluded_cidrs}


def release_window(release: str, now: datetime) -> datetime:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", release):
        raise ValueError("Invalid release month.")
    start = datetime.fromisoformat(f"{release}-01T00:00:00+00:00")
    deadline = start + MAX_AGE
    if now.tzinfo is None or not start <= now < deadline:
        raise ValueError("Future or expired release.")
    return deadline


def public_unicast(network):
    if network.version == 6:
        if not network.overlaps(IPV6_UNICAST):
            return []
        if IPV6_UNICAST.subnet_of(network):
            network = IPV6_UNICAST
    remaining = [network]
    for block in EXCLUDED[network.version]:
        kept = []
        for candidate in remaining:
            if not candidate.overlaps(block):
                kept.append(candidate)
            elif not candidate.subnet_of(block):
                kept.extend(candidate.address_exclude(block))
        remaining = kept
    return remaining


def parse_dataset(compressed: bytes, release: str, *, now: datetime) -> Dataset:
    deadline = release_window(release, now)
    if not 0 < len(compressed) <= MAX_COMPRESSED_BYTES:
        raise ValueError("Compressed dataset size is invalid.")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as archive:
        raw = archive.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError("Expanded dataset is too large.")
    csv.field_size_limit(128)
    rows = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    previous = (0, -1)
    countries = set()
    us_rows = {4: 0, 6: 0}
    networks = []
    excluded = count = 0
    for count, row in enumerate(rows, 1):
        if count > 2_000_000 or len(row) != 3 or not re.fullmatch(r"[A-Z]{2}", row[2]):
            raise ValueError("Invalid dataset row.")
        start, end = (ipaddress.ip_address(value) for value in row[:2])
        if (start.version != end.version or int(start) > int(end)
                or (start.version, int(start)) <= previous):
            raise ValueError("Unordered, overlapping or invalid address range.")
        previous = (end.version, int(end))
        countries.add(row[2])
        if row[2] != "US":
            continue
        us_rows[start.version] += 1
        for network in ipaddress.summarize_address_range(start, end):
            allowed = public_unicast(network)
            if allowed != [network]:
                excluded += 1
            networks.extend(str(value) for value in allowed)
        if len(networks) > MAX_NETWORKS:
            raise ValueError("Too many US networks.")
    if (count < MIN_ROWS or len(countries) < MIN_COUNTRIES
            or min(us_rows.values()) < MIN_US_ROWS_PER_FAMILY
            or {ipaddress.ip_network(net).version for net in networks} != {4, 6}):
        raise ValueError("Incomplete dataset or missing IP family.")
    return Dataset(release, hashlib.sha256(compressed).hexdigest(), deadline,
                   tuple(networks), count, us_rows, excluded)


def download(release: str) -> bytes:
    # Only a validated month can select a public official URL; no arbitrary URL.
    release_window(release, datetime.now(timezone.utc))
    url = f"https://download.db-ip.com/free/dbip-country-lite-{release}.csv.gz"
    with urlopen(url, timeout=45) as response:
        if response.url != url:
            raise ValueError("Unexpected dataset redirect.")
        data = response.read(MAX_COMPRESSED_BYTES + 1)
    if len(data) > MAX_COMPRESSED_BYTES:
        raise ValueError("Download too large.")
    return data


def replace_dataset(connection, dataset: Dataset) -> None:
    """COPY and replacement share one transaction; readers retain old rows until commit."""
    with connection.transaction():
        connection.execute("set local lock_timeout = '5s'")
        connection.execute("set local statement_timeout = '120s'")
        connection.execute("select pg_catalog.pg_advisory_xact_lock(7108342026)")
        now = connection.execute("select pg_catalog.clock_timestamp()").fetchone()[0]
        if release_window(dataset.release, now) != dataset.valid_until:
            raise ValueError("Dataset expiry does not match its release.")
        current = connection.execute(
            "select distinct source_version, valid_until from public.us_beta_ip_ranges").fetchall()
        if len(current) > 1:
            raise ValueError("Mixed current dataset requires review.")
        if current:
            version, _ = current[0]
            match = VERSION.fullmatch(version)
            if (not match or match[1] > dataset.release
                    or (match[1] != dataset.release and match[2] == dataset.sha256)
                    or (match[1] == dataset.release and match[2] != dataset.sha256)):
                raise ValueError("Unknown, regressed or changed same-month dataset requires review.")
        connection.execute("create temporary table us_ip_refresh_stage (network cidr primary key) on commit drop")
        with connection.cursor().copy("copy pg_temp.us_ip_refresh_stage (network) from stdin") as copy:
            for network in dataset.networks:
                copy.write_row((network,))
        counts = connection.execute(
            "select family(network), count(*), sum(power(2::numeric, "
            "case family(network) when 4 then 32 else 128 end - masklen(network))) "
            "from pg_temp.us_ip_refresh_stage group by family(network)").fetchall()
        if len(counts) != 2 or sum(row[1] for row in counts) != len(dataset.networks):
            raise ValueError("Staged dataset is incomplete.")
        if current == [(dataset.source_version, dataset.valid_until)]:
            differs = connection.execute(
                "select exists ((select network from pg_temp.us_ip_refresh_stage "
                "except select network from public.us_beta_ip_ranges) union all "
                "(select network from public.us_beta_ip_ranges "
                "except select network from pg_temp.us_ip_refresh_stage))").fetchone()[0]
            if not differs:
                return
        previous = dict(connection.execute(
            "select family(network), sum(power(2::numeric, "
            "case family(network) when 4 then 32 else 128 end - masklen(network))) "
            "from public.us_beta_ip_ranges group by family(network)").fetchall())
        for family, _, addresses in counts:
            if previous and (family not in previous or not int(previous[family]) * 4 <= int(addresses) * 5 <= int(previous[family]) * 6):
                raise ValueError("US coverage changed by over 20 percent; review required.")
        # DELETE preserves MVCC snapshots, unlike TRUNCATE. A failed insert rolls back it too.
        connection.execute("delete from public.us_beta_ip_ranges")
        connection.execute(
            "insert into public.us_beta_ip_ranges (network, source_version, valid_until) "
            "select network, %s, %s from pg_temp.us_ip_refresh_stage",
            (dataset.source_version, dataset.valid_until))
        if connection.execute("select pg_catalog.clock_timestamp() >= %s", (dataset.valid_until,)).fetchone()[0]:
            raise ValueError("Dataset expired during replacement.")


def connect_database():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    raw = os.environ.get("PESO_GEO_DATABASE_URL", "")
    if not raw:
        raise ValueError("Geography database credential is missing.")
    values = conninfo_to_dict(raw)
    project = "jfgiydtrskpqxyorvvbc"
    host = values.get("host", "")
    direct = host == f"db.{project}.supabase.co" and values.get("user") == "postgres"
    pooler = bool(re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", host)) and values.get("user") == f"postgres.{project}"
    if (not (direct or pooler) or values.get("dbname") != "postgres"
            or values.get("port", "5432") != "5432"
            or set(values) - {"host", "port", "user", "password", "dbname", "sslmode"}):
        raise ValueError("Expected the reviewed PesoDatabase direct/session-pooler connection.")
    values["sslmode"] = "verify-full"
    values["port"] = "5432"
    return psycopg.connect(**values, sslrootcert="system",
                           connect_timeout=15, autocommit=True, prepare_threshold=None)


def write_evidence(path: Path, record: dict) -> str:
    """Create immutable sanitized evidence; refusal or fsync failure stops dispatch."""
    payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as target:
        target.write(payload)
        target.flush()
        os.fsync(target.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", help="Release month; defaults to current month for official downloads only.")
    parser.add_argument("--input", type=Path, help="Validate a previously downloaded gzip; still checked for expiry.")
    parser.add_argument("--apply", action="store_true", help="Replace ranges in the reviewed PesoDatabase.")
    parser.add_argument("--manifest", type=Path, help="Create a new sanitized input manifest and separate result before applying.")
    args = parser.parse_args()
    if args.input and (args.apply or not args.release):
        parser.error("Local input requires --release and is validation-only; --apply must download the official source.")
    if args.apply and args.manifest is None:
        parser.error("--apply requires a new --manifest path for reconciliation evidence.")
    args.release = args.release or datetime.now(timezone.utc).strftime("%Y-%m")
    phase = "download"
    manifest_hash = None
    result_path = None
    attempt_id = None
    apply_started = applied = result_written = False
    try:
        if args.input:
            with args.input.open("rb") as source:
                compressed = source.read(MAX_COMPRESSED_BYTES + 1)
        else:
            compressed = download(args.release)
        phase = "validation"
        dataset = parse_dataset(compressed, args.release, now=datetime.now(timezone.utc))
        if args.manifest:
            phase = "evidence"
            result_path = args.manifest.with_name(args.manifest.name + ".result.json")
            if os.path.lexists(result_path):
                raise ValueError("Result evidence already exists.")
            attempt_id = str(uuid4())
            manifest_hash = write_evidence(args.manifest, {
                "schema_version": 1, "attempt_id": attempt_id,
                "prepared_at": datetime.now(timezone.utc).isoformat(),
                "dataset": dataset.manifest(),
                "retrieval": "local_unverified" if args.input else "official_https",
                "apply_requested": args.apply,
                "apply_outcome": "unconfirmed" if args.apply else "not_requested",
            })
        if args.apply:
            phase = "database"
            with connect_database() as connection:
                apply_started = True
                replace_dataset(connection, dataset)
                applied = True
        if result_path:
            phase = "result_evidence"
            write_evidence(result_path, {
                "schema_version": 1, "attempt_id": attempt_id,
                "input_manifest_sha256": manifest_hash,
                "apply_outcome": "committed" if applied else "not_requested",
            })
            result_written = True
        manifest = dataset.manifest()
        manifest["retrieval"] = "local_unverified" if args.input else "official_https"
        manifest["applied"] = args.apply
        manifest["warning_expiring_within_7_days"] = dataset.valid_until - datetime.now(timezone.utc) <= ALERT_BEFORE
        print(json.dumps(manifest, sort_keys=True))
        return 1 if manifest["warning_expiring_within_7_days"] else 0
    except Exception:
        if manifest_hash and result_path and not result_written and phase != "result_evidence":
            try:
                write_evidence(result_path, {
                    "schema_version": 1, "attempt_id": attempt_id,
                    "input_manifest_sha256": manifest_hash,
                    "apply_outcome": "committed" if applied else "unknown" if apply_started else "not_started",
                })
            except Exception:
                pass  # Missing or unreadable result leaves the immutable attempt unconfirmed.
        print(f"US-IP refresh failed during {phase}; admission still expires. Read the retained manifest and result before retrying any apply.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
