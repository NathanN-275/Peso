# Durable source upload dispatch

Supabase source uploads now require a committed, fresh attempt before the
backend calls Storage. The request body is validated first; admission then locks
the live owner and current reservation, rechecks wall-clock expiry and exact
owner/path/content type/actual size, and returns the exact attempt receipt.
The backend validates every field and reads the exact record in a separate
request before dispatch. No receipt, malformed
receipt, timeout or database failure permits a Storage call.

Each reservation and bucket/path can dispatch once. Repeating the admission,
even with the same attempt UUID or another bucket, fails rather than authorizing
a second write. An uncertain admission response may leave a record for a write
that never began. This conservative ambiguity remains pending. Current clients
make one PUT and cancel on failure; a user retry obtains a new reservation.
The backend never retries either admission or the external upload.
The separate read prevents a successful response from a rollback-configured API
from authorizing an unrecorded upload. It cannot authorize dispatch by itself:
the fresh admission must succeed first. PostgREST documents configurable
[transaction endings](https://docs.postgrest.org/en/stable/references/transactions.html#transaction-end);
actual hosted endpoint behavior still requires acceptance testing.

The upload remains create-only. A returned Storage success is recorded as
`succeeded`; this is an API observation, not provider-generation identity,
quiescence, cleanup settlement or physical erasure. A crash, timeout or lost
observation response leaves the attempt pending. Exact success observation is
idempotent and remains possible after owner deletion, cancellation or Auth
removal; it cannot reopen the reservation or authorize publication.
The pinned Storage SDK otherwise follows redirects, allowing a 307/308 to send
the upload body again. The cached admin client disables Storage redirects once
at initialization; Auth and PostgREST retain their separate clients. A real-SDK
loopback HTTP test verifies that a redirect receives one body and fails closed.
The source file is owned by a context manager and closes on SDK failure too.

The service-only ledger has no cascading Auth/reservation/video foreign key.
Owner, reservation, configured bucket, key, body metadata and attempt identity
cannot change. A source-to-video association is retained independently once
published. Ordinary deletion cannot remove the record or clear its outcome.
Clients have no table or function access; functions use invoker privileges and
fixed empty search paths. Direct privileged inserts still execute admission
guards. A trusted database administrator can bypass database guards; routine
maintenance must not disable them.

Both admitted and successful attempts remain unsettled. Expired-upload cleanup
may observe API deletion but cannot set `cleanup_confirmed_at`, purge the
reservation, release its capacity charge, remove its deletion outbox, complete
a Saved Lift receipt, or finish `complete_video_media_deletion`. Other owners
and legacy reservations without attempts retain their existing behavior. SQL
guards enforce this even if an application tries the old confirmation path.
The cleanup job counts only confirmations it could record. No automatic
settlement transition exists while the provider contract remains unresolved.

## Launch scope and remaining work

This implements the Supabase source PUT boundary only. Historical dispatched
writes and Azure SAS capabilities still require reconciliation.
[Avatar writes](private-media-avatar-writes.md) now have retained attempts and
atomic profile publication, with old client Storage policies denied at rollout. Pipeline thumbnails/playback and Saved thumbnail
backfill are covered by the [generated-write successor](private-media-generated-writes.md).
[Analyzed exports](private-media-export-writes.md) now use published snapshot-bound
attempts. [ZIP archives](private-media-archive-writes.md) now use retained
create-only attempts with complete selection binding and atomic publication.
Provider settlement remains unresolved. No public flag, transport, hosted setting, Auth deletion route or
provider credential changes here.

Before activation, finish all writers, exact resource/generation publication,
owner-wide cleanup and session replacement; establish the supported provider
settlement contract and rehearse the actual hosted roles/configuration. Until
then new source attempts deliberately keep capacity and deletion pending.
See [owner deletion](private-media-owner-deletion.md) and
[the unresolved provider crash window](private-media-upload-reconciliation.md).

Required CI includes real PostgreSQL admission, concurrency, lifecycle,
privilege, quota and finalizer tests. Backend tests cover dispatch ordering,
exact receipt validation, malformed/uncertain responses, post-upload observation
failure, invalid bodies and cleanup continuing for unrelated reservations.
These fixtures do not prove managed Storage behavior or hosted erasure.
