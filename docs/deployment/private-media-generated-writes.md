# Durable thumbnail and playback writes

Pipeline thumbnails/playback and Saved Lift thumbnail backfill now use a fresh
write attempt and an immutable per-attempt key. The version marker remains at
the end of the filename so current-thumbnail recognition still works. A retry
never overwrites another attempt's bytes.

After rendering, the writer records the exact owner/video, source path, purpose,
configured bucket, key, MIME type and actual byte size. Pipeline writes include
the claimed analysis job, worker and attempt count. Backfill has no analysis
lease: it requires a completed Saved Lift with no active analysis work.
Admission locks and rechecks current state, including owner deletion, resource
revocation, outbox and wall-clock deadlines. A foreign, missing, expired or stale
binding fails before external I/O. Direct ledger inserts execute the same guards.

The backend requires a fresh exact typed RPC result and a separate matching
readback before dispatch. There is no replay fallback after a lost response.
Upload is create-only through the Storage client whose redirects are disabled.
Only an acknowledged success observation returns the exact path for metadata
publication. Neither observed success nor publication is provider settlement.

## Publication and cleanup

Every new or changed nonnull thumbnail/playback metadata path must match a
successful admitted attempt for the same owner/video/source and permitted
purpose. Pipeline publication rechecks the exact live analysis generation;
backfill rechecks the Saved/completed/no-active-job boundary. Existing unchanged
references and path clearing preserve their prior cleanup behavior. Old writers
cannot publish fresh untracked paths. Migration rehearsal must quiesce or
replace those writers first; this document does not authorize hosted changes.

A metadata error or lost publication response does not delete the uploaded key:
publication may have committed. The ledger retains unreferenced attempts too.
Video revocation adds all admitted generated keys to its durable cleanup
snapshot, including keys whose upload or publication outcome remains unknown.
The source and generated ledgers survive Auth/video removal. Both dispatching
and successful attempts block outbox completion and Saved deletion receipts.
Ordinary API deletion, expiry and missing metadata cannot clear that denial.

The pipeline's existing original-source delete remains an API observation after
confirmed playback metadata publication; it is not an erasure acknowledgement.
The source attempt remains pending under its own settlement contract.

## Verification and launch limits

Required CI runs real PostgreSQL generation, owner/resource, privilege, lock,
publication, snapshot and finalizer cases. Caller regressions cover immutable
keys, exact admission/readback, uncertain responses, lease binding and preserving
bytes after uncertain metadata publication. Historical SQL fixture rows are
explicitly seeded with only the new publication trigger temporarily disabled
in disposable local tests. Application paths retain every runtime guard.

This change covers the pipeline and Saved thumbnail backfill. The
[analyzed-export successor](private-media-export-writes.md) adds exact snapshot
publication and cache resolution. [ZIP archives](private-media-archive-writes.md)
add full-selection frozen-package publication using this ledger.
[Avatar writes](private-media-avatar-writes.md) use a separate retained
owner/session ledger and atomic profile publication. Azure write capabilities and
historical dispatched writes still need reconciliation. Source reservations and
these generated writes share the existing capacity lock and configured per-user
and global byte limits. Every generated attempt stays charged in both states;
new source admission includes those bytes too. All remaining writers, complete
owner-wide deletion and session replacement remain launch work. These partial
capacity controls do not accept the complete quota/budget gate. The supported provider exact-generation settlement and
orphan/backup contract remains unresolved. Public media remains disabled.
Existing direct video Storage write capabilities and old Storage URLs must also
be retired at cutover; application key discipline does not remove those paths.

See [source attempts](private-media-source-write-attempts.md),
[owner deletion](private-media-owner-deletion.md) and
[provider reconciliation](private-media-upload-reconciliation.md).
