# Three-day retention and deletion recovery

Prepared implementation; hosted migration and scheduling are not yet approved or
verified. This document does not authorize deleting production data.

## Policy and timestamp

The backend assigns `expires_at` at successful upload registration (or verified
reservation finalization), using 72 hours from that time. Analysis completion
does not restart the timer. Saving clears the deadline. Saved videos and results
remain until user deletion; retention never claims `save_state=saved` or
`is_saved=true`. No training-media copy is created.

Existing deadlines are unchanged by the migration. Before launch, inventory
existing unsaved rows and review any proposed backfill separately. Deployments
with an explicit `SAVED_VIDEO_STORAGE_TTL_HOURS=24` must update that setting to
72; changing the code default alone does not override provider configuration.

## Atomic record removal and asynchronous media deletion

The cleanup worker finds expired candidates, then invokes the service-role-only
`claim_expired_video_deletion` transaction. It locks the video row, rechecks save
state and expiry, and defers videos with queued, processing or retry-wait jobs.
Queue recovery owns stalled jobs; retention no longer deletes a video merely
because its update timestamp is more than six hours old.

The transaction stores the video's owned media paths in `video_deletion_outbox`
and removes its analysis results and video row together. Job history cascades
with the video. A concurrent save that locks first protects the video; a save
after successful cleanup receives the existing not-found response. Late result
writes cannot recreate a deleted video because of the foreign key.

Storage deletion follows the transaction. Original, playback and thumbnail
paths plus all video-specific exports are deleted. Prefix listing is paginated;
listing errors are propagated rather than treated as an empty directory. The
outbox row is acknowledged only after every storage operation succeeds. It
contains no analysis output or video bytes and has no user-readable RLS policy.

On a storage failure, expired history/results stay removed, and the file-path
task remains for the next cleanup run. Repeated removal of already-deleted
objects is safe. Previously signed links can remain usable until their own
expiry or physical object removal. A late process that lost its lease may leave
an orphan object; the existing orphan sweep remains necessary. A real worker
restart/late-upload test is still a release gate.

Dry runs do not claim videos, delete records, or acknowledge tasks. Counts for
unclaimed candidates are estimates: a concurrent save or active job may make
the database reject an eventual claim.

## Deployment order and rollback boundary

1. Inspect backup/restore support, existing deadlines, current migration history,
   and storage quotas in the chosen environment. Obtain approval for hosted
   migration and deletion behavior with the explicit recovery limitation.
2. Apply the existing reservation/queue prerequisites, then
   `202609210001_unsaved_video_retention.sql`, then
   `202609210002_retention_deletion_outbox.sql` in isolated staging first.
3. Deploy the matching API and worker with the 72-hour setting. Readiness now
   requires the outbox schema. Verify service-role execution and denial to
   anonymous/authenticated users; run two-user acceptance against actual RLS.
4. Run `python -m app.jobs.storage_cleanup --dry-run` from `backend` against
   staging. Review the report before an explicitly approved destructive test.
5. Run approved cleanup through the token-protected API or existing worker job.
   Scheduling and provider identity must be verified before public launch; no
   paid cron service is implicitly authorized by this implementation.
6. Monitor oldest outbox age, pending count and cleanup errors. Pending media
   tasks are retried on every run (up to 200 oldest tasks per pass). Persistent
   failures require operator intervention; do not drop or manually empty the
   outbox to silence them.

Stop cleanup scheduling before rollback. Keep the outbox table and drain its
pending tasks using compatible code. Returning to old storage-first cleanup
reintroduces the save race. A code rollback does not restore removed database
rows or media. Do not reverse migrations or claim recovery without a tested
database **and storage** backup. No such production restore evidence is yet
recorded.

## Verification

- 15 disposable PostgreSQL integration tests passed, including transaction
  ordering for both save/cleanup outcomes, concurrent claims, result/history
  removal, active-job protection, late-result rejection, and client-role denial.
- Focused cleanup/storage/routes/health suite: 102 passed; 11 subtests passed.
- Storage failure/retry, idempotent cleanup, export-listing failure, a save after
  candidate enumeration, and missing-migration fail-closed behavior are covered.
- Static migration/RLS audit passed. These results do not establish hosted
  cleanup scheduling, storage-provider recovery, user-initiated deletion races,
  account deletion, or complete release acceptance.
- Full backend regression rerun: 491 passed, 34 subtests passed; the 15 database
  tests were skipped in that run and passed separately against disposable
  PostgreSQL 17. Repository policy tests: 217 passed. The temporary database
  container was stopped and removed after testing. An initial regression run
  caught an obsolete readiness mock; it was updated to require both queue and
  outbox schema checks, then the full suite passed.

## Account directory cleanup checkpoint — September 22

Directory prefixes ending in `/` now enumerate nested Supabase objects instead
of attempting to remove the virtual folder returned by its parent listing.
Listing completes before deletion; malformed entries, excessive nesting and
listing failures fail explicitly. Deletes are batched at 100 paths, and any
failed batch propagates to the caller. Filename prefixes used for individual
video exports retain their existing behavior.

Account deletion sweeps the exact `<user-id>/` video namespace after deleting
known video paths, covering abandoned Supabase uploads and orphan files with no
remaining video row. Avatars and saved-lift archives use the same recursive
directory handling. A storage error prevents profile/Auth deletion so the user
can retry. Focused route/storage/cleanup verification passed 103 tests and 11
subtests, including nested files, partial listing, partial delete and identity
preservation after storage failure.

This does not establish deletion under concurrent uploads, worker/export writes,
or Auth failure after profile deletion. Those races still need durable account
deletion coordination and live acceptance. Azure objects without repository
references are not covered by the Supabase namespace sweep; the selected public
beta uses Supabase storage. No hosted account or object was deleted by this work.

## Explicit video deletion failure handling

Saved Lift deletion and discard now reject cross-owner paths before removing
media, propagate media-delete failures as retryable 503 responses, and retain
database references on those failures. Batch Saved Lift deletion finishes all
selected media operations before deleting any selected rows, preserving retry
of the same selection after a later media failure. Missing files from an earlier
partial attempt can be deleted again safely by the storage provider.

Database failures during the subsequent multi-row deletion are still not atomic;
concurrent save/discard and worker/export writes remain open. This is failure
handling, not the durable deletion coordination needed for full acceptance.
The pre-change backend regression passed 508 tests and 68 subtests; 18 database
tests were skipped without a connected database. The changed route/storage suite
is verified separately and does not establish hosted deletion behavior.
