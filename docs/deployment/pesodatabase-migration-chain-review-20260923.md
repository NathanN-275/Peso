# PesoDatabase migration-chain review — September 23, 2026

**Verdict: BLOCKED for hosted application.** This is a read-only review of the
existing PesoDatabase project (`jfgiydtrskpqxyorvvbc`), not staging. No hosted
migration, service resumption, workflow activation, or public launch occurred.

## Current state and compatibility

- Supabase project status was `ACTIVE_HEALTHY` on Postgres 17.6.1.084. Its
  migration history ends at `202608270001`. A linked `supabase db push --dry-run`
  listed the seven files below in that order. None of the new admission,
  deletion-outbox, IP-range, or alert-ledger tables exists yet. The only current
  `enqueue_video_analysis_job` overload takes `(uuid, boolean)`.
- Render's [peso-beta-api](https://dashboard.render.com/web/srv-dak9ohfqj5pc73ac2ga0)
  and [peso-beta-analysis-worker](https://dashboard.render.com/worker/srv-dak9ohfqj5pc73ac2g8g)
  are both suspended. Their last successful deployment is
  [commit `4325798`](https://github.com/NathanN-275/Peso/commit/4325798f4a4bd7a8f8d55587c5520a5cf9c014d3).
  That deployed API already passes four named arguments to
  `enqueue_video_analysis_job` and its Blueprint enables reservations. Thus the
  deployed API is **incompatible with the current two-argument database RPC**;
  the pending reservation migration would supply the matching four-argument
  signature. Keep both services suspended until migration and private tests
  verify the entire upload path. A future code rollback to a two-argument
  caller would be incompatible after this migration.
- The current database had zero videos, analysis jobs, and storage objects at
  inspection. Recheck these counts immediately before any cutover; this is a
  point-in-time observation, not proof that future work is drained.
- The [PesoDatabase backups page](https://supabase.com/dashboard/project/jfgiydtrskpqxyorvvbc/database/backups/scheduled)
  reports the **Free Plan does not include project backups**.
  There is no verified recovery point or isolated restore rehearsal in this
  review. The dashboard also warned that requests may stop when its quota is
  exhausted. Neither condition is resolved by the migration dry run.

Follow-up: a private logical export and isolated local restore were verified
later on September 23; see the [backup rehearsal record](pesodatabase-backup-restore-rehearsal-20260923.md).
The [seven-file migration rehearsal](pesodatabase-seven-migration-rehearsal-20260923.md)
then passed on that restored copy. The hosted cutover remains blocked pending
fresh pre-cutover checks, the compatible release, and private end-to-end tests.
A [hosted cutover preflight](pesodatabase-hosted-cutover-preflight-20260924.md)
on September 24 confirmed that both suspended Render services retain their
intentional historical staging binding. The separate public candidate selects
PesoDatabase; see the blocker finding and cutover checklist before any hosted
change.

## Pending migrations, in required order

| Migration | Effect and relation to the spending guardrail |
| --- | --- |
| `202608300001_azure_analysis_queue_scaler.sql` | Adds a private queue-depth function for the Azure scaler; unrelated to the guardrail. It revokes public and service-role access. |
| `202609030001_upload_reservations.sql` | Adds the admission-control row, reservation table and RPCs; replaces the two-argument analysis enqueue RPC with a reservation-verified four-argument version. **Required for a durable intake stop.** This is the major compatibility cutover: old uploads without verified reservations cannot be newly queued, and old two-argument callers fail. Existing direct Storage policies are not removed here. |
| `202609210001_unsaved_video_retention.sql` | Changes only the database default for new video expiry from 24 to 72 hours; no existing deadlines are backfilled. Unrelated to the guardrail. Deployed commit `4325798` explicitly supplies a 24-hour expiry by default, so the migration alone does not deliver 72-hour API behavior. |
| `202609210002_retention_deletion_outbox.sql` | Adds a service-only deletion outbox and an expiry-claim RPC; unrelated to the guardrail. Installing it does not schedule cleanup. Any future cleanup can delete metadata and storage bytes, so its rollback needs both database and object recovery. |
| `20260922002632_intake_stop_reason.sql` | Replaces the stop RPC with the shared reservation lock and an operator/measured reason. **Required for the combined guardrail's intended stop behavior.** It does not cancel accepted work. |
| `20260922003008_us_ip_beta_admission.sql` | Adds a service-only IP range table and Auth hook function; unrelated to the guardrail. The hook is not activated by this SQL, and the range table starts empty. Do not enable the hook without a reviewed dataset and private signup tests. |
| `20260923224101_budget_alert_delivery.sql` | Adds a service-only monthly alert ledger and atomic claim/complete/release RPCs. **Required for Gmail alert deduplication and retry.** It does not start the GitHub workflow. |

The guardrail needs migrations 2, 5, and 7, but the linked CLI will push all
seven pending files in order. Do not mark the intervening migrations applied
without executing and reviewing them, or apply only the ledger outside normal
migration history. The `supabase db push --dry-run` confirms selection and
order; it does **not** prove that every SQL statement will execute successfully
or that the deployed services and storage policies behave correctly afterward.

## Required cutover and recovery evidence before a hosted push

1. Reconfirm the linked project ID, migration list, dry run, current API/worker
   commit, live queue/reservation/video counts, storage-object inventory, and
   Supabase quota state. Keep Render suspended and the budget workflow disabled.
2. Produce a restorable database backup despite the absence of managed Free
   Plan backups. Capture relevant Storage objects separately if any exist.
   Restore to an isolated target and verify schema, representative data,
   ownership/RLS, and object access. Record the backup timestamp, restore
   target, and exact recovery steps. Do not assume a database dump restores
   Storage bytes.
3. Rehearse the **exact seven-file chain** against a schema and data copy of
   PesoDatabase. Check that the old enqueue overload disappears, the new one
   works with the intended API commit, reservation admission rejects new work
   after a stop, and accepted work can finish. Check role grants/RLS on all new
   tables and RPCs. Confirm the US Auth hook remains disabled and no cleanup
   scheduler is enabled by the migration itself.
4. Prepare a compatible rollback: keep API/worker suspended while changing the
   schema; do not roll back to a two-argument caller after the RPC replacement.
   Prefer forward repair for an additive failure. If restoration is necessary,
   restore the database and any Storage objects from the verified pre-cutover
   recovery point, and reconcile the migration history. Do not use an old
   deploy or `DROP TABLE` as a substitute for a tested restore.
5. Only after that review, apply the exact migration chain to PesoDatabase in
   order and verify migration history, table/RPC signatures, service-role RPC
   access, client-role denial, admission state, and Supabase Data API exposure.
   The [Supabase Data API change](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically)
   makes a direct PostgREST RPC smoke test important. The budget workflow stays
   disabled until its secrets, private stop/accepted-job test, and Gmail test
   pass. Public launch and paid Render resumption require separate approval.

**Unblock condition:** verified backup and restore, compatible API/worker
cutover and rollback, seven-file rehearsal, and a reviewed production window.
The current zero-work snapshot reduces drain work but does not waive those
checks.
