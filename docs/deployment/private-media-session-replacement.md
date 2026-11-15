# Private media session replacement


The [browser session protocol](private-media-browser-sessions.md) now defines the
current browser v2 namespace,16/17 inventory, strict inventory version and durable
global provider-ACK fence. Native v1 remains unchanged. Existing v1 completion
records prove app revocation; browser v2 inventory must still be completed with
the same committed receipt, without repeating an acknowledged provider logout.
Physical cookie absence and transport drain are not claimed by cleanup headers.
Remaining media issuers/consumers and actual hosted/browser/native acceptance
still block activation. The protocol-specific details below describe the original
v1/local boundary where the linked v2 section explicitly supersedes them.
Prepared locally; all private-media flags remain off. This implements the shared
replacement boundary, not hosted Auth, browser/native or public-launch acceptance.

## One accepted session

The exact main Auth storage key is wrapped before client construction. Password
login, signup, automatic web PKCE, trusted native callbacks, recovery, refresh and
main-key removal use that boundary. Password/signup do not consistently acquire
the installed SDK's Auth lock, so the wrapper has its own queue and a separate
project navigator lock across cooperating browser tabs. Native uses its process
queue and existing AsyncStorage. Required browser lock/storage failure blocks;
there is no unlocked or empty-memory fallback when media is enabled.

SDK events are hints. The controller rereads committed storage and transition
state, and only its accepted stream publishes the active media key, AuthContext
session, profile work or backend token. Stale SDK results cannot replace a newer
accepted generation. Callbacks return without calling Auth APIs or awaiting work
which needs its lock. Same-provider-session refresh is not replacement. A rotated
same-session credential is persisted even if initial app validation fails, so an
API outage cannot discard the provider's new refresh token; activation stays
blocked until validation succeeds. An already accepted same-session refresh
preserves media. Native callback allowlists and PKCE no-replay behavior remain.

## Outgoing retirement and incoming validation

Before a changed identity overwrites the main key, a noncredential journal binds
backend, issuer, outgoing and intended incoming owner/session keys. The old SDK
value remains the retry credential; the journal never copies access/refresh
tokens. Media release and the lifecycle epoch fence old and late private work.
The fixed `/private-media/session-replacement` endpoint verifies the captured old
Bearer and revokes only its exact local provider session. Its deterministic
server UUID5 operation is separate from the session UUID reserved for global
logout. It cannot accept a caller-selected old owner/session, scope or path.

Every cookie page and final receipt is bound to that old identity and operation.
Partial progress is persisted before requesting another page. Complete outgoing
proof is retained before main-key mutation. A strict bounded cache retains at
most 64 exact outgoing completions, without credentials, so a stale tab can prove
its own A retirement after a later B-to-C transition. An unrelated latest journal
alone cannot prove A ended. Missing, corrupt, evicted or unknown proof blocks.
Known retired sessions cannot be reactivated by a stale SDK save.

A fresh `/private-media/session-acceptance` decision then verifies the incoming
Bearer and requires literal true from the existing provider/app/owner session
predicate. It authorizes no bytes or writes and returns only bound owner/session
and accepted=true. This prevents adopting an incoming token already invalidated
by an overlapping global logout. New/recovered identity adoption validates before
activation; changed-key persistence waits for that decision. Normal backend/media
requests retain their current-session and epoch guards. Only the two fixed
transition transports may carry a captured outgoing or not-yet-active token.

On failure the old value/proof stays, incoming media remains unavailable, and
both web/native shells expose a sanitized error and Retry. Retry can finish a
secured old-session removal and return to normal sign-in when an incoming login
response was lost. It never replays passwords or consumed PKCE codes. A rejected
or expired old Bearer without complete durable proof remains blocked; no expired
JWT exception, new-owner authority or client assertion substitutes for it.

## Global logout and credential updates

Explicit logout keeps its all-device scope. Version2 local records distinguish
app/cookie completion from provider acknowledgement. Replacement/removal may use
a global confirmation only after a successful/accepted provider response was
persisted. A later retry reuses that acknowledgement instead of repeating global
provider logout and revoking a later login. Captured logout intent prevents a
late A removal from removing or locally revoking B. Legacy three-field records
are app-only; version1 records cannot certify the newer cookie protocol.

The visible transition Retry can also resume an already requested global logout
whose bound cookie page or app/cookie receipt is durable but provider acknowledgement
is missing. Partial and final seven-field cookie pages are strictly bounded and
bound to the captured outgoing owner/session, issuer and backend storage key. A
partial page only selects continuation; it never certifies app/cookie completion.
The final global page is retained before the compact receipt, so a failed receipt
write can resume without issuing another app revocation request.

Retry first captures the unresolved outgoing identity under the controller lock,
then releases that lock before reading Auth or calling sign-out. Only an exact
matching raw outgoing session and its pending global record select continuation.
The fixed global transport may resume while the active key is null only with a
validated retained page. A fresh attempt requires the exact active outgoing key;
a later page can continue from null only after its previous page's persistence
callback succeeds. Another active account/session always blocks continuation.
The backend still verifies the outgoing Bearer; local progress is no substitute
for authentication. Acknowledged records use normal transition Retry and never
repeat provider logout. Provider/read errors remain sanitized and blocked, without
replaying login or PKCE operations or selecting a global logout for the incoming
account.

Email/password updates capture the accepted UI identity, await ordinary session
acceptance outside callbacks, and bind that intent to the actual Auth `/user` PUT
Bearer. Unbound, changed or superseded requests fail closed. The storage wrapper
also rejects a late A credential-update save over B without revoking/hiding B.
Recovery activation is bound to the exact accepted callback key; stale closures
and late callbacks cannot put another account into recovery or clear its mode.

## Exact cookie paths and limits

Retained grant records supply distinct resource paths even after metadata,
provider-session removal or expiry. The service-only invoker inventory uses an
indexed keyset with 33-row lookahead, emitting at most 32 host-only, Secure,
HttpOnly, SameSite=strict expiration cookies per response. Local replacement
selects only the verified old session; global logout selects that verified
owner's inventory. Native uses no cookie inventory or Set-Cookie response.
The cursor selects only continuation, never an owner or arbitrary path. Avatar
revision cookies join archive/video inventory in archive, avatar, video ordering;
SQL, server and all three client progress validators must deploy together before
avatar issuance. Retire old bundles that reject avatar cursors. See [avatar readers](private-media-avatar-reads.md).

`cookie_cleanup_complete` means the final inventory page and its expiration
headers were returned. It is not independently observed browser erasure. Issuance
must freeze/cancel/drain outgoing requests before final clearing: a delayed
Set-Cookie response can otherwise arrive afterward, although its revoked grant
cannot authorize bytes. The current issuer migration and real browser testing
still must establish this. The transport bounds an attempt to 60 seconds and
256 pages; persisted progress allows explicit continuation without false success.
It never abandons a pending progress write when the network deadline expires.

## Remaining acceptance

Project-owned storage/callback/fetch/React tests prove bounded local behavior;
real PostgreSQL tests cover exact local/global revocation and retained inventory.
The normal pre-existing installed-SDK logout fixture is a separate regression;
no previously rejected adversarial SDK probe is repeated or certified here.
Actual SDK startup, navigator locks, multiple tabs, native bridges, issuing-host
cookies, reload/response loss and supported recovery still require acceptance.
A stale shipped client can bypass new local coordination; protected rollout must
ensure version convergence before claiming cross-tab completion.

Finish all media issuers/consumers (including remaining legacy avatar compatibility), historical
capabilities/URLs, provider policy attestation, account deletion and supported
exact-generation/backup settlement. Bound stale logout-record cleanup still needs
rollout acceptance. These local changes enable none of the hosted flags and do
not close the full staging-authentication or end-to-end launch gates.
