# PesoDatabase hosted cutover preflight — September 24, 2026 UTC

**Finding: BLOCKED for scheduling the hosted migration and service cutover.**
This was a read-only check of the existing **PesoDatabase** project
`jfgiydtrskpqxyorvvbc`, not staging. The seven-file database chain still
matches the [isolated rehearsal](pesodatabase-seven-migration-rehearsal-20260923.md),
but both suspended Render services retain their **intentional historical staging**
binding (`iseqgaewjpjcxrndibep`). The separate
[public-beta candidate blueprint](public-beta-candidate-binding.md) already
specifies PesoDatabase; converting the existing services is a coordinated
future cutover, not a correction to make in isolation. The available backup is a
single local copy, and a hosted recovery has not been rehearsed. No hosted database, Render,
GitHub, payment, or launch setting was changed.

## Evidence snapshot

| Check | Result and source |
| --- | --- |
| Target and status | Supabase project detail: `PesoDatabase`, `jfgiydtrskpqxyorvvbc`, `ACTIVE_HEALTHY`, Postgres `17.6.1.084`. Local `supabase/.temp/project-ref` matches. Checked September 24 at approximately 01:14 UTC. |
| Migration history | Supabase migration list and linked CLI agree: 21 applied migrations, latest `202608270001`; no unmatched hosted migration. `supabase db push --linked --dry-run` reported exactly the seven files below, in order. Checked approximately 01:15 UTC. |
| Live work and Storage | Read-only SQL at 01:15:15 UTC: `public.videos=0`, `public.analysis_jobs=0`, `storage.objects=0`, `storage.buckets=3`. The reservation, admission, and alert tables do not yet exist, so a reservation count is **not applicable**, not zero. No job-status or object-bucket rows were returned. Recheck immediately before any cutover. |
| Current RPC | Read-only SQL at 01:18:44 UTC: `enqueue_video_analysis_job(uuid, boolean)` exists; the four-argument overload and `disable_video_upload_admission()` do not. This is the expected pre-migration state. |
| Backup | The six private SQL exports and `SHA256SUMS` in `/Users/nathan/Downloads/peso-private-backups/2026-09-23-pesodatabase-pre-migration` all passed SHA-256 verification. The dump files were written at about 00:18 UTC, roughly 57 minutes before the first live-count query. Directory mode is `0700`, files `0600`. The [restore record](pesodatabase-backup-restore-rehearsal-20260923.md) proves an isolated local restore, but this one local copy is neither a fresh pre-cutover point nor a rehearsed hosted recovery. |
| Supabase plan and quota | [Backups page](https://supabase.com/dashboard/project/jfgiydtrskpqxyorvvbc/database/backups/scheduled): Free Plan, no managed project backups. [Organization billing](https://supabase.com/dashboard/org/ireiverxhceuwvshqkjz/billing): spend cap enabled; grace period over; requests may return 402 if quota is exceeded. [Usage](https://supabase.com/dashboard/org/ireiverxhceuwvshqkjz/usage) for Aug 26–Sep 26: organization egress `0.709/5 GB`, database size `0.03/0.5 GB`, average Storage `0.05/1 GB`; the PesoDatabase database was `28.54 MB`. These usage figures are organization or billing-cycle measures where labeled, not PesoDatabase calendar-month charges; they can refresh with delay. Checked approximately 01:17 UTC. |
| Render API and worker | [API](https://dashboard.render.com/web/srv-dak9ohfqj5pc73ac2ga0) and [worker](https://dashboard.render.com/worker/srv-dak9ohfqj5pc73ac2g8g) are both **Suspended**, Starter, Blueprint managed, on `main`, with last successful deploy [`4325798`](https://github.com/NathanN-275/Peso/commit/4325798f4a4bd7a8f8d55587c5520a5cf9c014d3). Their environment pages show `SUPABASE_URL=https://iseqgaewjpjcxrndibep.supabase.co`, consistent with the historical staging Blueprint. The API's `UPLOAD_RESERVATIONS_ENABLED=true` and `UPLOAD_STORAGE_PROVIDER=supabase` were verified; both keys are present on the worker, whose values remain masked. Credential values were neither revealed nor copied. Checked approximately 01:20 UTC. |
| Deployment contract | At deployed commit `4325798`, the [historical staging Blueprint](https://github.com/NathanN-275/Peso/blob/4325798f4a4bd7a8f8d55587c5520a5cf9c014d3/render-beta.yaml) sets `PESO_DEPLOYMENT_ENVIRONMENT=student`, reservation mode on, Supabase uploads, and manual deploys. The [separate public candidate Blueprint](https://github.com/NathanN-275/Peso/blob/feat/combined-public-beta/render-public-beta.yaml) selects `production` and PesoDatabase. Runtime configuration rejects a production URL paired with the student discriminator. The deployed API supplies four named arguments to `enqueue_video_analysis_job` and probes the reservation/admission tables at startup. The migrated local database provided that signature and passed the database-level accepted-job smoke test. The current hosted database does not, so resuming either service against it is unsafe. The dashboard's Auto-Deploy control did not expose a resolved value; confirm it again at cutover. |
| Budget workflow | [Draft PR #47](https://github.com/NathanN-275/Peso/pull/47) is open against `main`. The budget workflow file is absent from `main`, and the repository Actions variables list has no `PESO_PUBLIC_BETA_BUDGET_MONITOR_ENABLED` entry. The guardrail is inactive. Checked approximately 01:18 UTC. |

The seven pending files are, in order:

1. `202608300001_azure_analysis_queue_scaler.sql`
2. `202609030001_upload_reservations.sql`
3. `202609210001_unsaved_video_retention.sql`
4. `202609210002_retention_deletion_outbox.sql`
5. `20260922002632_intake_stop_reason.sql`
6. `20260922003008_us_ip_beta_admission.sql`
7. `20260923224101_budget_alert_delivery.sql`

## Blockers and exact later cutover checklist

**Blockers now:** the coordinated switch from the historical staging service
configuration to the public candidate has not occurred; its project-bound
credentials and other release inputs have not been checked against PesoDatabase.
Hosted restoration is untested and the verified dump is a single local copy;
Supabase warns of quota restriction. The guardrail code is in an unmerged draft
PR and has no configured secrets or private end-to-end test. None of these is
resolved by the migration dry run. Do not schedule a coordinated migration and
service cutover yet. This corrects the initial reading that the staging binding
was an accidental mismatch; it was intentional for the existing beta services.

Follow-up at approximately 01:43 UTC: the candidate Blueprint already pairs
`PESO_DEPLOYMENT_ENVIRONMENT=production` with the exact PesoDatabase URL, while
the historical Blueprint pairs `student` with staging. Seven Blueprint-policy
tests and six backend runtime-boundary tests passed. Both configurations are
internally consistent; a URL-only Render edit is not a valid cutover.

The Supabase CLI listed exactly two active Free-plan projects, PesoDatabase and
`peso-staging`, and no PesoDatabase preview branch. [Supabase's Free-plan
limit](https://supabase.com/docs/guides/platform/billing-on-supabase) is two
active projects across organizations owned or administered by the account;
paused projects do not count. A separate hosted logical-restore rehearsal
therefore needs a temporary free slot, such as a reversible pause of staging,
or an approved paid plan. The [managed restore-to-new-project
feature](https://supabase.com/docs/guides/platform/clone-project) itself requires
paid physical backups, so the available Free-plan route is a manual logical
restore into a **new, private, disposable project**, never into staging. Do not
pause staging, create a project or branch, or spend money without a specific
decision on that route.

For a later, separately authorized cutover:

1. **Freeze and recheck.** Keep API/worker suspended and the budget workflow
   disabled. Confirm project ref, latest migration history and seven-file dry
   run, service deploy SHA and manual-deploy state, Supabase quota, and live
   counts of videos, jobs by status, reservations if present, and Storage
   objects by bucket. Investigate any nonzero work or drift before continuing.
2. **Create a recovery point.** Export fresh roles, application and managed
   Auth/Storage schema, data, and migration history to a private directory;
   checksum and verify each file. If `storage.objects` is nonzero, separately
   copy and checksum the corresponding object **bytes** and bucket settings.
   Rehearse recovery to a compatible isolated hosted target, including Auth,
   RLS, representative rows, migration history, and object access. Preserve
   the recovery point off this single machine. No backup is fresh indefinitely;
   repeat the inventory and export immediately before the hosted push.
3. **Resolve bindings and release compatibility.** Apply the reviewed
   `render-public-beta.yaml` candidate to the existing service IDs only in the
   coordinated cutover. Set `PESO_DEPLOYMENT_ENVIRONMENT=production` together
   with PesoDatabase's URL and matching project credentials; verify both
   services' values, reservation mode, Supabase upload provider, and exact
   deploy SHA without exposing secrets in logs or PRs. Keep services suspended
   and deploys manual. Do not roll back to a two-argument enqueue caller after
   the schema changes. Save-only environment edits would not update a running
   process, and URL-only edits would fail the runtime discriminator.
4. **Apply and inspect only after review.** With a reviewed recovery point and
   cutover window, apply the seven files in the dry-run order to PesoDatabase.
   Verify 28 migration-history entries ending `20260923224101`; the old enqueue
   overload is gone and the four-argument overload, stop RPC, and alert RPCs
   exist; admission singleton, RLS, role grants, and Auth-hook activation state
   match the review. Check service-role and client-role behavior through the
   Data API, since SQL grants alone do not prove REST exposure. Do not enable
   the budget workflow or resume Render as part of this check.
5. **Failure path.** On any failed migration or verification, leave Render
   suspended and the workflow disabled. Prefer a reviewed forward repair for
   an additive failure. If restoration is necessary, use the verified pre-push
   database export **and** separate Storage bytes, restore first to an isolated
   compatible hosted target, compare counts/schema/RLS/object access, and
   reconcile migration history before deciding whether to rebind services or
   restore PesoDatabase in place. The hosted procedure must be rehearsed before
   relying on it; an older Render deployment or `DROP TABLE` is not a backup.

Only after the migration and Data API checks should a **separate** private test
exercise a real accepted upload and worker analysis across an intake stop, then
configure billing secrets and test Gmail before activating the workflow. Nathan's
$50 preference does not authorize public launch or paid Render resumption.
