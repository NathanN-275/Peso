# Private media deletion cleanup

The shared outbox consumer and discard route use atomic revocation before
cleanup. Private media remains disabled. Saved Lift batches now use
[durable deletion receipts](saved-lift-deletion-receipts.md); account deletion
and remaining object publisher fences remain launch prerequisites.

Apply `20261027173544_complete_video_media_deletion.sql` only after the atomic
revocation migration, using the separately reviewed migration/cutover process.
No hosted migration is part of this change. Missing snapshot columns or a
missing finalizer must leave tasks pending; there is no legacy direct-delete
fallback.

The cleanup worker reads each full snapshot: owner/video, `storage_paths`,
`archive_paths`, `export_prefixes` and `delete_metadata`. It validates every
snapshot path and exact per-video export prefix before listing or deleting
anything for that task. Export listings are refreshed and all returned paths
must remain under the requested prefix. Video assets and rendered exports use
the existing video Storage bucket; archives use `saved-lift-exports`. Identical
object names in different buckets are independent deletions.

Any validation, listing, bucket/client or object-deletion failure preserves the
outbox. Successful objects may be deleted again during retry. Dry-run performs
validation/listing/counting only; it never constructs a new archive client,
deletes media or acknowledges an outbox. Archive byte sizes are not looked up;
reclaimable-byte reporting is therefore conservative for archives.

After every required bucket operation succeeds, the worker calls the service-only
`complete_video_media_deletion` with the exact original snapshot. The SQL
function uses an empty search path and caller privileges. It locks video then
outbox, matching revocation's order. An owner mismatch, active/saved video,
active analysis job or changed snapshot returns false without deleting records.
The worker reports this as retryable and leaves the task. For permanent deletion,
analysis/video removal and outbox acknowledgement commit together. Child job,
analysis and upload-reservation rows are locked without waiting; contention
raises a retryable database error and preserves the complete task. Discard
preserves its tombstoned video and analysis. Earlier retention tasks whose video
metadata is already gone work with their empty/default extended snapshot fields.

The finalizer confirms a caller's exact cleanup snapshot, not a Storage audit.
The [upload reconciliation probe](private-media-upload-reconciliation.md) records
a completed-backing/missing-metadata crash gap that tenant TUS/REST alone does
not settle in the tested local release.
It does not stop an already running worker or prevent a later archive creation,
upload or metadata publication. Queue admission now rejects committed revocation; remaining admission and publisher
fences, post-upload rejection cleanup, account route wiring and hosted
races must be completed before activation or public launch. A request authorized
before revocation may already be delivering bytes.

Pipeline metadata publication and worker lifecycle now use the
[attempt-bound analysis fence](analysis-publication-fence.md); archive admission
and transitions use the [archive fence](archive-publication-fence.md). They
serialize database state with revocation. Durable upload intents, late-object
reconciliation and cleanup acknowledgement remain unfinished.

## Discard route integration

Discard first checks existing ownership, then calls revoke_video_media with the
verified owner, one video ID and delete_metadata=false. The SQL transaction
commits the tombstone, job cancellation, archive expiry and durable cleanup
snapshot before the first Storage operation. The repository validates the exact
one-owner/one-video response, nondeleting metadata flag and safe snapshot paths;
missing, mismatched or unavailable RPC responses have no legacy fallback.

The route passes only that snapshot to the shared targeted cleanup entry point.
It performs no global Storage listing, expired-video claim or unrelated outbox
scan. Both buckets and newly listed exports must finish, and exact-snapshot SQL
finalization must confirm true, before discarded=true is returned. Failure
returns retryable503 while the committed tombstone and outbox remain. Retrying
the same owned tombstoned video is supported and retains its metadata. Saved
Lift batches use durable receipts; account deletion remains unfinished.

The read-only readiness query now selects every required outbox snapshot column.
This rejects a missing extended schema without calling a mutating RPC. It does
not establish that revoke_video_media/complete_video_media_deletion exist or
are executable: no existing read-only runtime schema verifier exposes that
fact. Reviewed migration inventory/permissions and a controlled acceptance test
must prove those RPCs before release; route calls themselves fail closed.

No feature flag bypasses discard's atomic path. No hosted migration, actual
Storage deletion or media-policy activation is performed by this local change.
Existing issuer migration, admission and late-publisher fences, old Storage URL
retirement and real browser/native/owner-race acceptance remain launch gates.

## Queue admission revocation fence

`20261027182727_queue_video_revocation_fence.sql` replaces the existing four-argument
enqueue RPC after the retention outbox exists. Its arguments, defaults, result
shape, verified-upload requirement, state errors, force-completed behavior,
global admission advisory lock, user/global queue quotas and active-job
idempotence are preserved. The RPC remains service-only SECURITY INVOKER with
an empty search path and qualified tables and lock/time functions.

After the global admission lock and video row lock, discarded, pruned, expired
or nonfinite-deadline media and any deletion outbox row deny admission before
an old active job can be reused. A null deadline remains valid. A finite saved
video deadline still applies, matching private-resource authorization. Expiry
and outbox are rechecked after a potentially waiting active-job lock. Current
wall-clock time is used, since transaction-start time can precede lock waits.
This changes no retention timestamps or existing jobs for a denied request.

Revocation and admission serialize on the same video row: admission first can
commit a job that the waiting revoker then cancels; revocation first causes the
waiting admission to deny. This does not stop a worker already running,
replace worker claim/lease/publication fences, authorize direct SQL insertion,
or make Storage deletion atomic with SQL. Those remain separate prerequisites.
No hosted migration, queue change, worker action or data removal occurs merely
by adding this migration and its disposable-database tests.

Saved Lift batches now use the receipt-aware finalizer in the successor migration.
Its additional advisory/video/receipt/outbox ordering protects missing-row retries
and retired IDs. See [Saved Lift deletion retries](saved-lift-deletion-receipts.md).
