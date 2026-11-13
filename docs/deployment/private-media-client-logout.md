# Private media client logout and lifecycle


The [browser session protocol](private-media-browser-sessions.md) now defines the
current browser v2 namespace,16/17 inventory, strict inventory version and durable
global provider-ACK fence. Native v1 remains unchanged. Existing v1 completion
records prove app revocation; browser v2 inventory must still be completed with
the same committed receipt, without repeating an acknowledged provider logout.
Physical cookie absence and transport drain are not claimed by cleanup headers.
Remaining media issuers/consumers and actual hosted/browser/native acceptance
still block activation. The protocol-specific details below describe the original
v1/local boundary where the linked v2 section explicitly supersedes them.
Status: gated preparation. EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED defaults false.
Keep it off until every remaining media client/issuer, session transition,
deletion flow and required hosted acceptance below is complete. This flag does
not enable the server or its disabled provider-policy binding.

## Logout ordering

The installed Supabase JS/Auth SDK2.103.0 holds its auth lock while selecting
the logout token, sending its provider request and removing local session data.
The private-media fetch adapter is supplied through createClient's global.fetch.
It intercepts only POST to the exact configured Auth /logout endpoint; all
other requests retain the configured fetch. With the flag off, provider fetch
behavior is unchanged. With it on, only global/default logout scope is accepted.
Current UI logout preserves the existing all-device scope explicitly.

AuthContext uses signOutWithPrivateMedia, which deduplicates same-session calls,
rejects a different concurrent session and binds the UI intent to the SDK's
actual logout token. Players/cache state are released before entering Auth and
again inside the locked provider request. The adapter awaits backend app
revocation, validates its global completion receipt, persists confirmation and
only then sends the original provider request with its captured token. It does
not call Supabase APIs from inside the fetch adapter or auth-state callback.

Checkpoints contain only scope/completed_at/replayed and are keyed by backend,
Auth project, owner and provider session. No access token, refresh token,
raw claims, media grant or Storage URL is persisted by this module. Decoding
claims only correlates local state/UI intent; it never authenticates a JWT.
The backend independently verifies the captured token and chooses owner/session.
The API adapter refuses backend drift and a different current client session.

A lost provider response or process restart reuses a previously persisted app
confirmation rather than requiring a now-invalid token to read the backend
again. Refreshing a token for the same provider session retains its checkpoint;
another owner/session/deployment cannot inherit it. Failed app confirmation,
media release or storage access prevents provider logout. Provider failures
retain confirmation. Only provider statuses accepted by the installed SDK
(success or401/403/404) durably mark provider acknowledgement and make confirmation
eligible for cleanup. A retry never repeats an acknowledged global provider request; and cleanup
runs after the SDK emits SIGNED_OUT. Cleanup failure retains noncredential
metadata. Crash-orphaned receipts still require bounded stale cleanup before
rollout. Local storage is a client completion record, not a server trust seam.

## Player and private-state lifecycle

The shared registry attempts every resource release and awaits them all for an
explicit logout, reporting generic failure if any fail. Browser video pauses,
removes src/poster and reloads the captured element, including after ref
detachment on unmount. Native hook-owned players pause and replace their source
with null; the hook keeps responsibility for final player disposal. Each browser
pause/source/poster/reload step is attempted even if another step throws. Native
source replacement is still awaited when pause throws. Failures are sanitized
and still block logout; removing sources alone does not prove a successful
release. The web playback indicators clear before release so a player exception
does not retain stale playing/time state. Retry attempts the full release again.

Auth changes compare owner/provider-session keys: token refreshes and same-session
focus events preserve playback, while sign-out or another session starts release.
Saved/playback caches clear; a lifecycle epoch rejects late private API responses
and cache repopulation. Private web activity/layout and native screen children
remount for another media session without remounting native deep-link handling.
Native root selections and recordings clear; late preview/camera results are
fenced and overview state is tagged with its session. Web logout reports errors
and disables duplicate clicks; recovery navigation waits for successful logout.

## Verification and remaining acceptance

Focused tests execute the actual TypeScript API adapter and the installed SDK
using synthetic network/storage/session fixtures. They cover app-before-provider
ordering, checkpoint persistence/response loss/reload/refresh, project/owner/session
separation, wrong intent/double clicks, malformed data and storage errors,
provider rejection, post-SIGNED_OUT cleanup, cached and late responses, browser/
native resource adapters and the real SDK process lock while a later login waits.
Fault-injection cases also cover every browser release step, native pause and
replacement failures, pending replacement, and blocked logout followed by a
successful full retry. Relevant existing auth/backend/activity/web-route/submission
regressions and TypeScript are checked separately; exact logs and hashes live in
the evidence packet. Synthetic fixtures do not prove provider crypto/lifecycle behavior,
actual browser navigator locks, native bridge disposal or rendered accessibility.

The initial dependency-verifier attempt correctly rejected a symlink as an
installed dependency tree. The successful verifier runs against the actual
worktree dependencies, with every guard input matching the isolated candidate;
only TypeScript resolves that same dependency tree through a temporary link,
removed after checking. No patch/audit policy was changed. The older activity
test's provider-presence matcher now accepts JSX props so a session key can be
supplied; its durable-route and non-demo checks remain.

Before activation, complete real acceptance of every account/session replacement
(including deep-link/startup replacements) and matching HttpOnly-cookie clearing,
deleted-owner local completion, crash-receipt retention cleanup, bounded failure
and actual lock/bridge/reload/error acceptance. The [shared replacement boundary](private-media-session-replacement.md) now captures
the outgoing identity before main storage changes, commits exact-session
revocation and cookie pages, and validates incoming liveness before activation.
Its local proofs do not establish actual provider/browser/native acceptance.
Finish export/archive consumer adapters and real acceptance of playback/thumbnail
readers. Native grants remain in app memory; Expo playback caching is disabled,
and native HTTP/decoder cache behavior still needs acceptance. Finish deletion/
admission integration, apply and verify the required revocation/outbox/publisher
fences, and retire previously
issued Storage URLs under the approved preservation/recovery plan. Complete
real private two-owner/provider/browser/native/proxy/load/recovery tests and all
other launch gates. Existing clients/Storage URLs still prevent claiming complete
media revocation or public deployment readiness.

## Exporting changed public environment settings

The app:web:export command clears Metro's cache on each export. In a local
flag-off then flag-on export without --clear, Metro reused the flag-off adapter
bytes for the second output. Repeating both exports with --clear emitted the
requested false/true adapters and different bundle inventories. Keep cache
clearing when changing EXPO_PUBLIC settings; a zero exit code alone does not
prove that the emitted configuration matches the requested environment.
These diagnostic exports use synthetic configuration and do not replace
protected release checks or real browser/native acceptance.
