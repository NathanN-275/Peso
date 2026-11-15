# US admission dataset and refresh

Prepared locally; no hosted ranges, credentials, workflow variable, Auth hook or
API admission flag were changed. Gate 8 remains open. This is IP-country network
admission, not proof of a person's location; VPN exits and incorrect US labels
can admit people outside the US.

## Source and attribution

Country admission data is derived from [DB-IP IP to Country Lite](https://db-ip.com/db/download/ip-to-country-lite),
by [DB-IP](https://db-ip.com), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Peso transforms the full download into US CIDRs and excludes special-purpose
space. Retain this notice with source/derived evidence. DB-IP describes Lite as
reduced coverage and accuracy; its internal accuracy index is not a percentage
guarantee. The [source comparison](us-ip-data-source-review-20261029.md) records
why this no-new-cost source was selected over credentialed alternatives.

The `/app` web AuthLayout and AppShell now share a visible DB-IP backlink and
license link. They cover signup, signed-in upload and their error states. A
legal-page-only credit would not satisfy the provider's stated web-page
requirement. Verify the exact released bundle and actual hosted viewport/error
screens before activation; local source placement alone is not hosted acceptance.

## Validation and fixed expiry

`scripts/refresh_us_ip_dataset.py` downloads only the validated release month's
official HTTPS gzip URL, rejects redirects, and bounds compressed/expanded bytes
at 16/64 MiB. It parses the documented UTF-8 three-field CSV, checks every row for
format, ordering and non-overlap, and rejects fewer than 500,000 source rows,
100 country labels or 1,000 US rows per family. These are corruption/anomaly
guards, not proof of completeness or geographic accuracy. Missing families deny.

Only `US` rows become CIDRs using exact range summarization; no supernet widening.
The conservative policy removes CIDRs overlapping IANA special-purpose IPv4
space (including anycast, multicast and reserved blocks), and accepts IPv6 only
inside `2000::/3`, excluding special-purpose blocks there. Excluded blocks are subtracted from each CIDR, preserving ordinary
neighboring addresses without widening the original source range. Transition mechanisms such as Teredo/6to4 are excluded even if tagged US.
The policy reflects the [IPv4](https://www.iana.org/assignments/iana-ipv4-special-registry/)
and [IPv6](https://www.iana.org/assignments/iana-ipv6-special-registry/) registries
reviewed October 29, 2026; review registry changes before broadening admission.

Expiry is **35 days after UTC midnight on the release month's first day**.
This is Peso's conservative policy, not a provider freshness SLA. Future and
expired releases reject. Re-download/replay cannot extend this deadline.
The lookup migration checks actual database wall time for each admission.

Local files require an explicit release month and are validation-only. They
cannot be applied or implicitly relabeled to the current month. Hosted apply
always retrieves the source directly over HTTPS. An identical digest under a
different release is rejected as a stale replay, even on the download path.

Validate without a database credential or writes:

```sh
python scripts/refresh_us_ip_dataset.py --release 2026-10 --input /path/to/dbip-country-lite-2026-10.csv.gz
```

The JSON manifest records the exact compressed SHA-256, source URL, license,
release, finite expiry, counts, exclusions and retrieval mode. Local-file
validation reports `local_unverified`; it does not authenticate release provenance. Store it privately with run
evidence, not as proof of a hosted load. An exit status of 1 with a valid manifest
and `warning_expiring_within_7_days=true` is the pre-expiry alert, including after
a successful apply; read `applied` before retrying. Other failures log only a
phase, never exception text or a connection string.

## Atomic replacement and recovery

`--apply` requires a new `--manifest` path, the reviewed `PESO_GEO_DATABASE_URL` secret and
`psycopg[binary]==3.2.6` (already used by database security checks). It does not add
a backend runtime dependency. The connection must identify selected PesoDatabase
`jfgiydtrskpqxyorvvbc`, database `postgres`, direct Postgres or its session-pooler
user, and port 5432. TLS uses `verify-full` with system roots; host-address/service
overrides and transaction-pooler port 6543 reject. The actual session-pooler host
must be obtained from the provider, not guessed. See Supabase's
[connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

Within one database transaction the loader serializes cooperating refreshes with
an advisory lock, checks version/expiry against the database clock, COPYs into a
temporary table, checks both families and coverage, then replaces rows with DELETE
and INSERT. It never TRUNCATEs the active table. Concurrent readers keep the old
committed set until commit. Constraint, COPY, insert or expiry failures roll back
the whole replacement. Lock/statement timeouts bound waits. Ambiguous connection
loss at commit requires readback; do not infer that a failed client response means
the transaction rolled back.

Every apply must retain its exact input before any database action. For example,
choose a new, private evidence path for each manual attempt:

```sh
python scripts/refresh_us_ip_dataset.py --release 2026-10 --apply --manifest artifacts/us-ip-refresh/manual-20261030T200000Z.json
```

The create-only manifest is flushed and fsynced before connection or dispatch.
It contains only the attempt UUID, validated source URL/version, compressed
SHA-256, fixed expiry, counts, retrieval mode and requested action. It contains
no database credential, environment values or exception text. An existing input
or result path refuses a new apply rather than replacing previous evidence.
Evidence-write failure before dispatch prevents database access.

The separate `<manifest-name>.result.json` binds the attempt UUID and SHA-256 of
the immutable input manifest. `committed` means the loader observed transaction
completion; `unknown` means dispatch began without an acknowledgement;
`not_started` means it failed before dispatch. No result, an unreadable result,
or one that fails those bindings leaves the input attempt unconfirmed. A result
write failure after commit exits unsuccessfully, keeps the input manifest and
never retries the database apply or invents rollback. Validation-only runs still
print their JSON result without requiring an evidence path.

On an unconfirmed attempt, read the selected database in a new transaction and
compare the retained exact source version, expiry and reviewed row set before any
new apply. Neither a failed process nor source re-download proves rollback.
Preserve the old attempt evidence and make an explicit recovery decision; do
not overwrite it or blindly retry an uncertain commit with a new path.

The source version includes release and SHA-256. Older releases, changed bytes in
the same month, unknown/mixed current versions, or over-20% per-family address
coverage changes reject for review. An identical verified row set is a no-op,
avoiding daily write churn. This is not an overrideable automatic rollback path:
review and rehearse any provider republish or source change before replacing data.
Never disable admission to compensate for expired data; accepted jobs may drain.

## Scheduled operation and remaining activation work

`.github/workflows/public-beta-geography.yml` prepares a daily 03:43 UTC refresh,
with manual dispatch, read-only repository permission, one non-cancelling
concurrency group and a ten-minute job limit. It is disabled unless the repository
variable `PESO_PUBLIC_BETA_GEO_REFRESH_ENABLED` is exactly `true`. It uses the
separate `public-beta-geography` environment. The refresh supplies a create-only
manifest path and an artifact step attempts to retain its sanitized identity and
outcome directory after refresh success or failure, for 90 days. Missing expected
evidence fails the artifact step. The locally fsynced manifest and a successfully
uploaded artifact are separate evidence: cancellation, timeout or runner loss
can prevent remote retention. If the job disappears without an uploaded manifest,
treat the apply as unconfirmed and inspect database state before any recovery.
Download/validation failures can occur before an input manifest exists; the
sanitized job log identifies that phase, without pretending a database apply
occurred. No secrets were created or uploaded.

Before enabling, rehearse backup/migrations/restore and private hosted load,
review the new database credential's scope/storage at action time, restrict the
environment to reviewed release source, verify the provider connection and row
ACLs, and verify web attribution in the candidate. The prepared adapter uses the administrative
connection; its broad privilege must be reviewed before storing it in CI. Confirm
that GitHub failure notifications actually reach Nathan and rehearse download
failure, rollback, pre-expiry warning and expiry. Workflow failure is an alert
signal, **not evidence of delivered notification**. GitHub schedule delays or
disablement cannot extend the database expiry. If the job stops, admission stops
at expiry and operators must restore reviewed fresh data. Do not silently fall
back to allowing unknown IPs. Hosted Auth/proxy/direct-Storage cutover and actual
US/non-US clients remain mandatory under [US admission](us-ip-admission.md).

## Local verification, October 29

Official October CSV compressed SHA-256:
`097426b8ddae89157d444a59ac1847e873f7943c32d52becc4371c8b0273af80`.
710,834 rows (65,156 US IPv4 / 27,130 US IPv6) produced 252,921 CIDRs
(155,177 IPv4 / 97,744 IPv6); nine source CIDRs had special-purpose exclusions,
with their public neighbors retained.
Expiry: `2026-11-05T00:00:00Z`. It is already in the seven-day warning window.

The real source was loaded only in a non-root disposable PostgreSQL 17 fixture,
with a loopback-published port. Initial replacement took about 5.2 seconds and
replay about 2.0 seconds; unchanged row `xmin` values prove replay avoided writes.
Sample results matched the source classification and excluded private/transition
space; they do not prove physical location or whole-dataset accuracy. This fixture
was not network-egress isolated. Its container and dedicated network were removed.
Offline parser/credential tests and actual PostgreSQL transaction/regression
evidence are retained separately. No hosted scale/performance result is claimed.
