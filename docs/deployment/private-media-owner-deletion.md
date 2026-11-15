# Owner deletion boundary

The owner-deletion migration adds a permanent `deleting_at` timestamp to
`private_media_owners`. This row has no Auth foreign key, so its denial survives
Auth removal and a later identity with the same UUID. Once set, the timestamp
cannot change or clear, the owner identity cannot change, and the row cannot be
deleted through normal table writes. The transition atomically revokes existing
grants. These constraints also apply to direct privileged maintenance updates.

The service-only `begin_private_media_owner_deletion(uuid)` RPC locks the owner,
sets the timestamp once and returns `(deleting_at, replayed)`. It can be retried
after a lost response without requiring a current provider session. Its caller
must bind the owner to verified request authorization; a service RPC is not
end-user authorization. No HTTP route invokes it yet.

`read_private_media_owner_deletion(uuid)` returns one row containing
`owner_exists` and nullable `deleting_at`. It waits for an update of an existing
owner row. Absence is an observation, not permission or proof that no deletion
is starting: an uncommitted first insert is invisible. No caller may report
cleanup complete from either this read or the begin timestamp.

Grant issuance and byte authorization already lock the owner before checking
`private_media_app_session_is_live`. The replacement predicate rejects every
session of a deleting owner, including newly created sessions. An authorization
transaction that already holds the owner lock finishes before deletion begins;
a later authorization waits and observes the committed denial. The transaction
boundary does not cancel bytes that an earlier HTTP authorization has already
allowed the server to stream.

The upload/publication successor migration backfills owners from existing video
and reservation rows while holding write-conflicting table locks. Those locks
use NOWAIT with a bounded migration lock timeout, so an active writer requires
retrying the migration after quiescence. Existing deletion timestamps survive.

Reservation admission creates and locks its owner before taking capacity locks;
receive and verify lock an existing owner before child/validation locks. All
three refuse a deleting owner, including a verified-upload replay. Wall-clock
checks after lock waits reject expired reservations and validation leases.
Direct reservation and video metadata writes require an existing live owner and
use NOWAIT to avoid reversing the owner-first lock order. A missing owner cannot
be created from a child trigger. Callers must handle lock conflicts through
bounded retry and preserve pending external-write outcomes.

Exact cleanup-only updates remain possible: video revocation, reservation
rejection/expiry, deadline shortening, cleanup timestamps, and Auth/video FK
nulling. Comparisons include every non-cleanup field so a terminal state cannot
carry a new media path, lease, size, identity or analysis payload. A shorter
deadline cannot be combined with metadata publication or used to extend access.
These metadata timestamps do not establish provider settlement or erasure.

The analysis successor checks the owner before enqueue can reuse a job. Global
claim and expired-lease recovery distinguish a busy owner from a missing or
deleting owner: busy candidates are skipped unchanged; unavailable candidates
are cancelled without changing their video, then the loop continues. Recovery
cancellations increment neither retry nor failure counts, preserving the API.
A claim returns one ready job; a later poll handles candidates after that job.

Worker preflight reads the owner binding, locks that existing owner before child
rows, then rereads the video binding and validates the current attempt and
wall-clock deadlines. Renewal, progress, completion, failure and publication all
use this boundary. Short owner contention can finish normally; its two-second
lock timeout still fails closed. Direct job/result writes take nonwaiting video
and owner locks and reject revoked, expired, pruned or outboxed resources. Job
and result identities cannot change. Exact job cancellation and result deletion
remain available for cleanup; a cancellation cannot carry a retry schedule,
new attempt or identity change. The legacy cancellation RPC uses that shape.

The archive successor checks its existing owner with NOWAIT before any new
archive row, processing transition or completed publication. The earlier archive
fence continues to validate selection, state ordering and artifact details.
Exact failure/expiry cleanup can proceed without a live owner: path is cleared,
identity/selection/attempt/start fields stay fixed, completion bookkeeping stays
finite, and expiry can only stay, clear or shorten. A terminal status cannot
carry a new artifact or hidden work. The existing archive repository retries
only SQL errors that establish rollback, never ambiguous transport outcomes.

The profile/Storage successor initializes an owner row after trusted Auth user
insertion and backfills existing users while signup/profile writes are locked.
The initializer preserves an existing deletion tombstone. Its private trigger
function has no application caller privileges. Initialization failure rolls back
signup, so actual hosted signup permissions and latency require rehearsal.

A second private SECURITY DEFINER function returns only an ownership-bound
boolean and locks the caller's existing owner row with NOWAIT. It checks
`auth.uid()` before reading any owner; it cannot initialize missing rows or inspect
another account. Clients retain no table access. The profile trigger uses that
function for authenticated writes and the service-only owner check for backend
writes. Profile identity cannot change; deletion remains available for cleanup.
Both privileged functions have fixed empty search paths, postgres ownership and
exact source/ACL bindings enforced by the migration audit. Verify that
`peso_private` is not an exposed Data API schema in the actual hosted candidate.

Restrictive INSERT/UPDATE policies add owner denial to existing video/avatar
Storage policies. They grant no access themselves and keep existing folder/type
rules. They do not modify provider object rows or backing bytes. SQL transaction
ordering is tested; it does not prove that Storage's permission probe holds a
transaction through an external upload. Backend service-role Storage writes
bypass RLS and still require durable intents. Existing signed URLs, provider
crash outcomes and direct-video policy retirement remain separate cutover work.

The current `/account` prefix-sweep route is still unsuitable for public-beta
acceptance. Before wiring begin to that route, complete durable tracking and
settlement for every direct client and backend Storage writer. Historical direct avatar/video Storage
dispatches need the same reconciliation contract. No database decision
settles an external write that was already dispatched.

The Supabase source PUT now has [durable dispatch admission and cleanup denial](private-media-source-write-attempts.md).
Admission and an observed API success both remain unsettled; pending attempts
retain the reservation capacity charge and block deletion completion.
[Pipeline and Saved backfill assets](private-media-generated-writes.md) now have
durable generation-bound attempts, strict publication and complete admitted-key
cleanup snapshots too. Their success observations remain unsettled. [Analyzed exports](private-media-export-writes.md)
now use the same ledger with exact analysis/source snapshots and published cache
resolution. [ZIP archives](private-media-archive-writes.md) now retain full-selection
attempts even after job/Auth/video loss. [Avatar writes](private-media-avatar-writes.md)
now have retained owner/session attempts and atomic profile publication. Azure
capabilities and historical dispatches still need coverage.

Every external write needs a durable attempt/generation record. Unknown Storage
outcomes remain pending until a supported provider reconciliation contract can
settle their exact generations. Only then can targeted cleanup and durable
completion precede Auth deletion and verified client lifecycle release. See
[the provider counterexample and support request](private-media-upload-reconciliation.md).
Media remains disabled; no hosted migration or deletion acceptance follows from
this local foundation.

The required grant, reservation, revocation, analysis, archive, Saved deletion and
profile-owner PostgreSQL suites load their relevant current owner migrations. They cover prior
behavior plus owner transition/replay, rollback, future/recreated sessions,
worker skip/cancel, exact counters, publication denial, other owners, immutable
state, service-only privileges and actual lock waits in both orderings. Local fixture
results do not prove hosted provider configuration or end-to-end deletion.

The profile fixture models trusted Auth INSERT permission and Storage metadata
with synthetic tables. It exercises client RLS and the full current media SQL;
it is not an actual managed Auth/Storage service. The initializer pattern is
documented in [Supabase user management](https://supabase.com/docs/guides/auth/managing-user-data),
and the policy combination follows [PostgreSQL restrictive policies](https://www.postgresql.org/docs/17/sql-createpolicy.html).
