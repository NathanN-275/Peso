# PesoDatabase pre-cutover packet

This packet prepares a later decision. It does not authorize migration, Render
rebinding, paid service resumption, budget activation, or public launch. Each
needs its own decision. Target: **PesoDatabase `jfgiydtrskpqxyorvvbc`**.

The September 24 observations are historical, not current provider evidence.
The [hosted rehearsal](pesodatabase-hosted-recovery-rehearsal-20260924.md)
restored database rows and migration history; its temporary project was deleted
and staging resumed. The **eight custom Storage policies** in the private
`auth_storage_schema.sql` were not part of that hosted restore. Their recovery
and access behavior must be verified before claiming complete recovery. The
checker includes a separate gate for this gap. Do not schedule a migration from
the previous green restore result alone.

## 1. Read-only evidence and checker

Use Python 3.11+, Git, authenticated Supabase CLI (rehearsed version 2.98.2),
and the reviewed branch. The checker reads the linked project ref, runs only
`supabase migration list --linked` and `supabase db push --linked --dry-run`,
compares the repository and reviewed Blueprint, and hashes private backup files.
It never runs a hosted mutation, reads key values, exports data, or uploads a
backup. Its only write is a new mode-`0600` redacted report outside the repo.

Copy `config/pesodatabase-precutover-observations.example.json` into a private
mode-`0700` directory outside the repository and make the copy mode `0600`.
Fill it using fresh provider reads. Nulls and false defaults intentionally block.
Do not place credentials, connection strings, free-text notes, row samples,
provider responses, or backup contents in this file. Only the defined fields
are accepted; duplicate or unknown fields block. Use UTC timestamps in
`YYYY-MM-DDTHH:MM:SSZ` format. Secret credentials needed by the CLI must already
be configured through its normal authentication/environment mechanism; never
use `--password`, a credential-bearing `--db-url`, shell tracing, or debug output.

From the repo root, using actual private paths:

```sh
python3 scripts/check_pesodatabase_precutover.py \
  --backup /Users/nathan/Downloads/peso-private-backups/APPROVED-WINDOW/sql \
  --observations /Users/nathan/Downloads/peso-private-backups/APPROVED-WINDOW/observations.json \
  --output /Users/nathan/Downloads/peso-private-backups/APPROVED-WINDOW/check-01.json
```

The backup subdirectory must contain exactly the six SQL files listed below
and `SHA256SUMS`. Use a new output name for each run: existing files and
symlinks are rejected. Exit 0 means `CHECKS_PASSED`; exit 1 means the written
report contains `BLOCKED`; exit 2 means arguments or report creation failed.
Reports contain fixed check IDs/results, the fixed target, timestamps, and
validated local commit/Blueprint/backup-manifest digests (no credentials or paths);
stdout contains only the finding. Provider errors are captured, never echoed.
Unknown CLI output blocks instead of being copied into evidence. No regular
expression can prove arbitrary text is secret-free: safety comes from never
emitting input values, exceptions, dump contents, or provider output.

Checks ending in `_attestation` are operator observations, **not independent
provider verification**. The checker cannot establish a freeze, identify the
origin of an arbitrary SQL dump, authenticate a masked credential, prove a
remote backup exists, or prove recovery behavior. Do not mark these true just
to get a passing report. A report expires after 60 minutes or on any relevant
change, whichever comes first; even a pass grants no approval.

### Evidence requirements

| Observation | Required evidence / passing value |
| --- | --- |
| Project/history | Linked project exactly PesoDatabase; 21 remote versions matching the first 21 local files, ending `202608270001`; exactly the seven pending files below in order. Wrong target prevents all Supabase commands. History mismatch prevents dry run. |
| Source/Blueprint | `source_commit` equals full local `git rev-parse HEAD`; `blueprint_sha256` equals SHA-256 of `render-public-beta.yaml`; tracked migrations and Blueprint unmodified from HEAD. Other worktree edits are ignored and preserved. |
| Freeze/freshness | All writers stopped or drained, including direct client Storage writes, Auth changes, cleanup/schedulers, exports, and other workers. Render suspension alone is insufficient. `freeze_at` ≤ every dump/manifest modification time ≤ `backup_completed_at` ≤ `observed_at` ≤ now, all within the last 60 minutes. Needed provider freeze changes require a separate decision. |
| Work inventory | Numeric zero for `videos`, `active_uploads`, `active_analysis_jobs`, and `storage_objects`. `reservations` is null only when the table is absent in the expected pre-migration state. Otherwise require numeric zero. No strings, booleans, negatives, or missing counts. Any nonzero blocks this zero-work cutover route; investigate and review a revised packet rather than overriding it. |
| Backup provenance | Operator confirms dump target in `backup_project_ref`; `backup_manifest_sha256` matches the locally verified manifest. Directory `0700`, files `0600`, current owner, no symlinks, no extras, six unique fixed filenames, nonempty files. SHA-256 verifies bytes, not completeness or provenance. |
| Second copy | Nathan confirms protected **off-machine** copy, verifies all six files there against the copied manifest, and records its matching SHA-256 and `verified_at` between backup completion and observation. A second directory on this Mac is insufficient. No cloud upload is performed by this packet. |
| Budget/quota | GitHub enable variable is not `true`, workflow remains inactive; Supabase quota/headroom and service health checked with no unresolved restriction. Unknown is blocked. |
| Managed-schema recovery | `managed_schema_customizations_verified=true` only after a separately approved isolated hosted test restores custom Storage policies and any custom Auth/Storage triggers/functions/grants, compares their definitions, and verifies owner/non-owner access. The September 24 record does not satisfy this gate. |

Read counts with a read-only database transaction. For the current schema:

```sql
begin read only;
select count(*) as videos from public.videos;
select count(*) as active_uploads from public.videos where status = 'uploaded';
select count(*) as active_analysis_jobs from public.analysis_jobs
  where status in ('queued', 'processing', 'retry_wait');
select count(*) as storage_objects from storage.objects;
select to_regclass('public.upload_reservations') is not null as reservations_present;
rollback;
```

If the reservation table unexpectedly exists, stop and review schema/history
drift; never turn an SQL permission or query error into zero or null. The video
count blocks pending/nonterminal video rows too. Check in-flight direct Storage
and multipart uploads and scheduled writers separately before attesting freeze;
database counts cannot prove that a client is no longer writing bytes.

### Render binding evidence

Read both existing services by ID, including effective environment-group
overrides. Never provision a replacement or sync the Blueprint from this packet.

| Service | ID | Expected last deployed SHA |
| --- | --- | --- |
| API | `srv-dak9ohfqj5pc73ac2ga0` | `4325798f4a4bd7a8f8d55587c5520a5cf9c014d3` |
| Worker | `srv-dak9ohfqj5pc73ac2g8g` | `4325798f4a4bd7a8f8d55587c5520a5cf9c014d3` |

Record actual effective `PESO_DEPLOYMENT_ENVIRONMENT` as `environment`,
`SUPABASE_URL` as `supabase_url`, actual deployed full commit, suspension, and
auto-deploy state. Passing binding values are `production`,
`https://jfgiydtrskpqxyorvvbc.supabase.co`, and matching PesoDatabase server
credentials. Verify credential provenance through authorized private provider
inspection and a read-only authenticated check against PesoDatabase; record
only `credential_project_ref` and `credentials_verified`, never the credential
or its hash. A masked value's presence or a decoded JWT alone is not proof.
If verification cannot be performed without a credential change, leave false.

Both services must be suspended with `auto_deploy="off"`. An unexpected deployed
SHA blocks review; do not silently change the checker's approved baseline. The
candidate `source_commit` is separate from the last deployed SHA: this packet
does not require deploying the candidate. The known historical staging binding
will correctly produce `BLOCKED`; report that fact without editing Render.
Packet completion is distinct from eligibility to schedule the cutover.

During a separately approved rebind, update discriminator, URL, and matching
keys together while suspended; use a verified save-only operation. A Blueprint
update ignores existing `sync: false` values and does not re-prompt for them.
Confirm CORS, proxy/IP-admission inputs and reservation settings against the
[candidate binding](public-beta-candidate-binding.md) before any later deploy.
Never interpret saved settings as proof of the running environment.

## 2. Fresh recovery point — later approved window

Keep all writers frozen across inventory, export, copy verification and final
dry run. Recheck counts afterward; unexpected change invalidates the snapshot.
Create a **new** dated directory under the existing private backup root; never
overwrite September 23. Use `umask 077` and mode `0700` for the window directory
and its `sql` subdirectory. Put raw diagnostic logs in a separate private sibling,
never a terminal transcript, repository artifact, PR, or shared CI log. Stop on
each failed command; a partial export is not a backup.

After confirming the linked project, run these export commands from the repo
root. `PESO_BACKUP_DIR` must be the absolute private `sql` subdirectory chosen
for that approved window, not a path in Git. The linked CLI uses the existing
authentication; no credentials appear in command arguments.

```sh
supabase db dump --linked --role-only --file "$PESO_BACKUP_DIR/roles.sql"
supabase db dump --linked --file "$PESO_BACKUP_DIR/schema.sql"
supabase db dump --linked --schema auth,storage --file "$PESO_BACKUP_DIR/auth_storage_schema.sql"
supabase db dump --linked --data-only --use-copy --file "$PESO_BACKUP_DIR/data.sql"
supabase db dump --linked --schema supabase_migrations --file "$PESO_BACKUP_DIR/history_schema.sql"
supabase db dump --linked --schema supabase_migrations --data-only --use-copy --file "$PESO_BACKUP_DIR/history_data.sql"
```

Confirm the managed-schema export actually includes custom policy/trigger/grant
definitions; an empty or filtered export is a blocker. Do not exclude populated
tables to make an export succeed. A platform version change, encrypted/Vault
data, new vector tables, or new schema requires reviewing backup coverage first.
The six-file shape alone does not prove all newly introduced features are backed
up. From inside the private `sql` directory:

```sh
shasum -a 256 roles.sql schema.sql auth_storage_schema.sql data.sql history_schema.sql history_data.sql > SHA256SUMS
shasum -a 256 -c SHA256SUMS
shasum -a 256 SHA256SUMS
```

Record completion time after the manifest is written. Copy the whole private
window directory to Nathan's approved off-machine protected location and verify
the six hashes there. Record only the verified manifest digest and time in the
observations; keep the destination and account details private.

If Storage objects appear, keep this packet blocked. Inventory bucket settings
and object keys/versions privately, copy **bytes** through the authenticated
Storage API to a separate private sibling directory, and checksum each object.
Verify inventory completeness, byte lengths, and restore/read-back in an isolated
target before revising the zero-work gate. SQL metadata is not a byte backup.
Export provider settings (Auth redirects/providers/hooks, key provenance, Storage
settings, webhooks) separately and privately; SQL does not capture every setting.

## 3. Approved migration and verification checklist

This is a future execution checklist, not an action performed by the checker.
Review the report and fresh recovery point, then obtain the distinct migration
decision. Immediately rerun the live history/dry run. Apply only this sequence:

1. `202608300001_azure_analysis_queue_scaler.sql`
2. `202609030001_upload_reservations.sql`
3. `202609210001_unsaved_video_retention.sql`
4. `202609210002_retention_deletion_outbox.sql`
5. `20260922002632_intake_stop_reason.sql`
6. `20260922003008_us_ip_beta_admission.sql`
7. `20260923224101_budget_alert_delivery.sql`

Only after that decision use `supabase db push --linked` from the reviewed
checkout. Never add `--include-all`, repair history, or push only the ledger to
bypass drift. The chain can commit earlier files before a later failure; do not
assume all seven roll back together. Preserve private error evidence and inspect
actual migration history on failure. The pre-cutover checker intentionally blocks
after migration; it is not a post-migration validator.

Post-migration acceptance:

- History has 28 entries ending `20260923224101`; inventories match the frozen
  snapshot. The two-argument enqueue overload is absent; the four-argument
  `(uuid, boolean, integer, integer)` overload is present. Stop and alert
  claim/complete/release RPCs exist with the reviewed grants.
- Check RLS, ownership and grants for reservations, admission, retention outbox,
  IP ranges, alert ledger, public tables and Storage policies against the
  reviewed migrations. `anon`/unrelated `authenticated` cannot access private
  control tables or privileged RPCs; service-role access is sufficient, without
  granting it the private Azure scaler function.
- Through the Data API, check permitted service-role access and denied client
  access, plus two-user isolation. Any mutating RPC smoke test requires the
  separately approved private-test step; keep stop/reservation tests out of the
  read-only checker. SQL function existence does not prove REST exposure.
- Verify Auth account/profile preservation and bucket privacy/settings; compare
  custom managed-schema definitions and authorized/unauthorized Storage access.
  Keep the US Auth hook inactive until its dataset and private signup test pass.
  Confirm no cleanup scheduler or budget job was activated.
- Separately approve private upload/analysis testing and any paid resumption.
  A new reservation must fail after the intake stop while a previously accepted
  upload and **real media analysis** finish. A database job marked complete by
  hand is insufficient. Gmail tests and verified billing secrets precede a
  separate budget-activation decision; public launch remains separate.

## 4. Failure and recovery

Any failed or unavailable check means blocked, with a fixed result ID in the
redacted report. Missing CLI authentication, unfamiliar output, drift, nonzero
work, stale files, an unverified second copy, or unverified credentials must not
be replaced by historical values. Keep Render suspended and the workflow off.

Prefer a reviewed forward repair where safe. For data recovery, use the fresh
pre-push backup and separately backed-up object bytes, restoring first to a
separately approved disposable hosted project. Never restore over staging or
PesoDatabase as a test. Free-slot availability, a staging pause, project creation
and any paid plan must be decided for that recovery operation; prior temporary
pause approval was for the completed September 24 rehearsal.

Follow the [rehearsed transactional restore](pesodatabase-hosted-recovery-rehearsal-20260924.md):
verify target connection/project ref and checksums; retain hosted managed schema;
omit only the known forbidden `supabase_admin` role setting in a private copy;
restore roles, public schema, history schema, data and history data with TLS,
`psql --single-transaction --variable ON_ERROR_STOP=1`, and replication role
`replica` for import. Stop on any new error instead of deleting failing SQL.
Restore **custom** Auth/Storage policies/triggers/grants separately from reviewed
definitions; do not replace entire platform-managed schemas. Compare definitions,
roles, migration history and user access as well as counts. Restore object bytes
and verify reads if nonempty. Reconfigure project-bound settings/credentials only
under a separate rebind decision. Preserve both recovery material and failed-state
evidence until acceptance; an old deploy or a URL change is not data recovery.

The manual logical recovery method follows [Supabase's backup/restore guidance](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore),
including separately preserving history and managed-schema customizations. Our
September 24 rehearsal covers the documented subset only.

## Validation of this packet

```sh
python3 -m unittest discover -s scripts -p test_pesodatabase_precutover.py -v
git diff --check
```

Tests use synthetic private dumps and mocked read-only CLI responses, with no
network or real credentials. They establish checker behavior, not current hosted
readiness. Complete the packet with a dated actual report at execution time; do
not label fixture results as provider evidence.
