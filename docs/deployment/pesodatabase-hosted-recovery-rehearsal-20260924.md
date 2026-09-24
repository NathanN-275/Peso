# PesoDatabase hosted recovery rehearsal — September 24, 2026 UTC

**Result: the logical database restore succeeded on a separate hosted Supabase
project.** This rehearsed recovery from the September 23 private backup; it did
not restore, migrate, or modify PesoDatabase (`jfgiydtrskpqxyorvvbc`). The
temporary target was `peso-recovery-rehearsal-20260924`
(`nvoznzwdrkwwixyvhwfc`) in `us-east-1`. Existing `peso-staging`
(`iseqgaewjpjcxrndibep`) was paused to free one of the two active Free-plan
slots. The API and worker remained suspended and the budget workflow inactive.

**Current cutover finding: BLOCKED.** The hosted logical-restore blocker is
resolved for this backup, but the Render API/worker are still intentionally
staging-bound. Their PesoDatabase credentials have not been verified or changed,
the seven migrations remain unapplied to PesoDatabase, and a fresh protected
pre-cutover backup is still required. The existing
`render-public-beta.yaml` is a review-only candidate, not a deployed binding.

## Procedure and evidence

1. Reverified all six SQL exports against `SHA256SUMS` in the private backup
   directory. The directory remained mode `0700`, the dump and checksum files
   `0600`. The generated password for the disposable target was held only in a
   mode-`0600` file under `/private/tmp`, outside the repository. That local
   password file and the adjusted role-script copy were removed after the
   rehearsal. Connection
   used TLS through the Supabase session pooler with the target project ref in
   the database username. The target initially had managed `auth` and
   `storage` tables, no `public.videos`, and no migration-history table.
2. The first single-transaction restore stopped at `roles.sql` line 16:
   hosted Supabase reserves `supabase_admin`, so `ALTER ROLE
   "supabase_admin" SET "statement_timeout" TO '0'` was denied. PostgreSQL
   rolled back the whole attempt. A private copy of the role script omitted
   **only** that platform-owned setting; the source backup was not edited.
3. A second `psql --single-transaction -v ON_ERROR_STOP=1` run applied, in
   order, the adjusted roles script, `schema.sql`, `history_schema.sql`,
   `data.sql`, and `history_data.sql`. It exited 0 without SQL errors. The
   hosted target's existing managed Auth/Storage schema was retained; the
   separate `auth_storage_schema.sql` export was not applied because replacing
   those managed schemas on a hosted project is unnecessary and unsafe.
4. Post-restore SQL showed `auth.users=1`, `public.profiles=1`,
   `public.videos=0`, `public.analysis_jobs=0`, `storage.buckets=3`, and
   `storage.objects=0`; there were 21 migration-history rows ending
   `202608270001`, six public policies, and the custom
   `analysis_job_scaler` role. The hosted dashboard displayed the restored Auth
   account and the three expected buckets: `videos`, `profile-avatars`, and
   `saved-lift-exports`. No private row values, passwords, or keys were
   recorded in this note.

At approximately 02:16 UTC, the temporary recovery project was **paused** and
the original staging project had returned to **Healthy**. After Nathan confirmed
permanent deletion, the temporary project was deleted. At approximately 02:25
UTC, the organization project list contained only PesoDatabase and
`peso-staging`; both project dashboards showed **Healthy**. PesoDatabase was
never the restore target.

This establishes a **hosted logical database recovery path for this backup's
contents**. It does not prove recovery of Storage object bytes: the source had
zero `storage.objects` at the snapshot, and SQL exports only contain Storage
metadata. A later nonempty bucket requires separate byte copy and an object
read-back test. It also does not make the September 23 export a current
pre-migration recovery point. Immediately before any PesoDatabase migration,
take a fresh private export, checksum it, make an off-machine protected copy,
recheck live work and Storage objects, and rehearse or validate the exact
recovery material that will be relied upon.

## Safe recovery recipe for a later cutover

Use a new isolated hosted project in the correct region and verify its project
ref in both the dashboard and connection username before any write. Keep the
source project and Render services untouched. Verify dump checksums. Retain
the new project's managed Auth/Storage schema. In a **single transaction**,
restore roles (omitting only hosted-reserved role settings), application
schema, migration-history schema, data, and migration-history data. Enable
`ON_ERROR_STOP`, TLS, and `session_replication_role=replica` for the data
import; the exported `data.sql` already sets that role. Abort on any error and
inspect the first failure before retrying. Validate Auth, public-table,
migration-history, role, RLS-policy, and Storage-metadata counts; verify
Auth/Storage in the hosted dashboard. If object metadata is nonempty, restore
the separately backed-up bytes and read each sample back. Only then consider
a service rebind, with the correct project URL **and matching keys**.

The original private backup remains outside Git. Do not commit the dumps, the
adjusted role script, a password, an API key, or a row sample.
