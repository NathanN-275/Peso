# PesoDatabase seven-migration rehearsal — September 23, 2026

**Result: all seven pending migrations applied in order to an isolated local
restore of PesoDatabase.** Database-level admission, queue, alert-ledger, and
role-access checks passed. No hosted schema, Render service, GitHub workflow,
or public launch state was changed. This is a rehearsal, not authorization to
push migrations to PesoDatabase (`jfgiydtrskpqxyorvvbc`).

## Target and method

The source was the verified private backup described in the
[backup and restore record](pesodatabase-backup-restore-rehearsal-20260923.md).
Its 21 migration-history entries ended at `202608270001`, as on the linked
project. The target was a disposable local Supabase Postgres 17.6 database.
Before private data was loaded, its Docker network was disconnected and its
published port was checked unreachable. Administration used `docker exec` only.
The private dump and account data remained outside Git and PR logs.

Each migration below was applied as its own transaction with `ON_ERROR_STOP=1`:

1. `202608300001_azure_analysis_queue_scaler.sql`
2. `202609030001_upload_reservations.sql`
3. `202609210001_unsaved_video_retention.sql`
4. `202609210002_retention_deletion_outbox.sql`
5. `20260922002632_intake_stop_reason.sql`
6. `20260922003008_us_ip_beta_admission.sql`
7. `20260923224101_budget_alert_delivery.sql`

All seven completed without SQL errors. The only notice concerned an
`updated_at` trigger that did not exist in the restored source. See the
[migration-chain review](pesodatabase-migration-chain-review-20260923.md) for
each file's effect and the hosted cutover requirements.

## Checks on the migrated copy

The old `enqueue_video_analysis_job(uuid, boolean)` overload was absent and
the four-argument overload was present. Render's last deployed API commit,
`4325798`, calls this function with those four named arguments. A service-role
reservation made before the stop could be marked received, verified, enqueued,
claimed, and marked completed after the stop. A new reservation attempted after
`disable_video_upload_admission()` raised the expected admission failure and
created no row. The admission row remained disabled. These outcomes were
checked in separate transactions using the restored account's ID, without
printing private data.

The service role could atomically claim and complete a `$15` monthly alert;
a duplicate claim returned false. The new admission, reservation, deletion
outbox, IP-range, and alert-ledger tables had RLS enabled, service-role read
access, and no `anon` or `authenticated` read access. `anon` could not invoke
the stop or Auth hook. The retention claim RPC was available to the service
role; the Azure scaler function was not. The US IP-range table was empty, and
the migration only created its Auth hook function; it did not activate the
hook. No cleanup scheduler was installed by these SQL files.

These are database-level checks. They did not upload Storage bytes, run the
API or media-analysis process, exercise PostgREST, deliver email, or test a
hosted restore. The local test marked a claimed analysis job completed through
its RPC; it did not perform media analysis. Tests of the guardrail thresholds,
SMTP retry, and concurrent workflow runs are separate from this migration
rehearsal.

## Hosted decision and next gate

**Hosted application remains blocked.** Keep Render suspended and the budget
workflow disabled. Before a hosted push, recheck the live project ID, seven-file
dry run, fresh backup and restoreability, quota state, queue/video/reservation
counts, and Storage objects. Prepare the compatible API/worker release and
rollback, then use a reviewed cutover window to apply and verify the chain.
Afterward, a private end-to-end stop and accepted-job test, Data API checks,
GitHub secrets, and Gmail test are required before activating the guardrail.
Paid Render resumption and public launch need separate approval.
