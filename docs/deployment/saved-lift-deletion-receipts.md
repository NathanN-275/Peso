# Saved Lift deletion retries

`20261028190657_saved_lift_deletion_receipts.sql` and the matching API revision
replace Storage-first batch deletion with committed revocation, targeted cleanup
and durable completion readback. Apply through the reviewed recovery/migration
process before deploying this API; there is no legacy RPC/schema fallback.
No hosted operation is performed by adding these sources. Media flags remain off.

`revoke_saved_lifts` validates the entire distinct1–50 selection under sorted
video locks. A first request needs an owned Saved Lift under either legacy saved
flag, with no discard or prior deletion outbox. Missing/foreign selections return
generic unavailable; unsaved/discarded selections are conflicts. A matching
pending Saved-deletion receipt authorizes retry after the first revocation has
removed saved state. A completed receipt authorizes retry only when both video
and outbox metadata are absent. Invalid mixed selections roll back every new
receipt, tombstone, job cancellation and archive expiry.

The service-only RLS receipt table has no cascading video/Auth foreign keys.
New receipts begin pending and require a currently owned Saved Lift; identity
and creation time cannot change, completion cannot be reopened, and live video/
outbox metadata prevents completion. The exact-snapshot finalizer marks the
receipt completed atomically after deleting the video/outbox. Generic discard
and retention finalization without a Saved receipt keep their previous behavior.
The receipt proves this application cleanup transaction; it is not independent
proof of provider quiescence, byte erasure or backup retention.

Missing video rows cannot anchor locks or prevent ID reuse. Batch and finalizer
therefore acquire transaction advisory keys before video→receipt→outbox locks;
batches sort actual distinct advisory keys to account for hash collisions. The
video INSERT trigger takes the same key before insertion and rejects every
retired receipt ID. Video ID/owner rewrites are rejected too. An insert waiting
behind finalization cannot reuse the deleted ID. New functions are invoker-only
with an empty search path; mutating RPC/finalizer/insert fences have a two-second
lock timeout. Contention rolls back for retry; it never authorizes cleanup.

The route preserves input deduplication/order and the existing deleted_lift_ids/
deleted_count response. Its repository requires exactly one matching owned
partition row per requested ID, real booleans and strict pending cleanup snapshots.
Only pending tasks reach targeted cleanup; completed retries construct no Storage
client. Every requested receipt must subsequently confirm completion before API
success. A partial failure returns503 with access already revoked; retry the
original selection, including members whose metadata was already removed.
Selection/UI media release and broader client session acceptance remain pending.

Readiness selects every receipt column without a mutating probe. The new real
PostgreSQL suite is part of the required security CI matrix, whose runner rejects
missing/zero/skipped/failing suites. Disposable tests cover full-selection
rollback, partial retries, exact finalization, receipt ownership/immutability,
retention compatibility, overlapping batches, controlled ID-reuse waiting and
role privileges. This does not establish hosted migration or Storage acceptance.

Retain completed receipts until an approved retention/generation policy can
preserve retry and retired-ID guarantees. There is no automatic receipt purge.
Account-wide admission fencing and deletion, durable upload intents, ambiguous
provider-operation reconciliation, every media issuer/client, legacy URL
retirement and hosted launch acceptance remain required. In particular, existing
late or uncertain uploads can outlive object cleanup: these receipts do not
close that Storage race, and must not be used to enable the revocable-media path.
