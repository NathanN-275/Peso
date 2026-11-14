# Browser media sessions

Local source preparation; private media remains disabled. This protocol does not
complete remaining export/archive consumers, current browser/device acceptance, old-client
retirement, hosted migrations, provider policy, device or public-launch gates.

## Session namespace

Browser issuance is POST
`/private-media/session/{session_id}/{kind}/{resource_id}/session`.
Byte GET/HEAD uses the same prefix and an asset name. The canonical nonzero URL
session must equal independently verified Auth context at issuance, and the
retained authorized grant session before any Storage metadata or signing at read.
Owner comes from verified authority; URL session is not an owner selector.

The existing Secure, HttpOnly, host-only, SameSite=Strict cookie uses that exact
session/kind/resource path. A late old-session response can leave an old cookie
physically present. Its path cannot replace the incoming session's cookie or be
sent to the incoming session's byte URL. Exact server session revocation makes
the old grant unusable independently of cookie storage. Neither expiration headers
nor abort completion proves physical erasure, transport drain or recall of bytes.

Browser video issuance uses all six existing asset names: playback, thumbnail,
export:clean, export:pose, export:barbell and export:pose-barbell. This prevents a
late narrower same-session response from replacing an active broader cookie.
Every byte request still checks current owner/provider/app-session/resource and
the selected current artifact; a grant does not render an export or bypass its
readiness/retention rules. Avatar/archive each keep their one asset. Native v1
transport and selected video subsets stay unchanged.

A late same-session response can replace cookie value and shorten expiry. The
reader must handle actual expiry with bounded renewal for the same current
session/resource. No persistent crash marker, forced ordinary-crash signout or
new recovery API is introduced solely to claim cookie erasure. Interrupted account
transitions still use their durable journal and fail closed without required proof.

The old unnamespaced browser issuance/read routes return update-required denial.
V1 native transport and controlled legacy inventory cleanup remain. All active
browser bundles must converge on this protocol before activation; no provider URL
or account-Bearer byte fallback is allowed.

## Retained cookie inventory

Browser cleanup uses POST `/private-media/v2/logout` or
`/private-media/v2/session-replacement`. Its body is browser transport and optional
cursor. Verified context selects owner and exact local session; global cleanup
selects that verified owner's retained inventory.

The service-only invoker RPC private_media_session_cookie_paths_v2 returns exactly
resource_kind, resource_id and cookie_session_id. It UNIONs distinct retained
legacy resource paths, represented only in inventory by a NIL session sentinel,
with actual retained session paths. It keeps expired/revoked rows after resource
or provider-session metadata loss. NIL never authorizes an issuer/byte request.
The owner share lock has a two-second wait bound; failure is not completion.

Rows sort by kind, resource UUID, cookie-session UUID. The cursor is that exact
tuple, at most81 characters; only its final session component may be NIL. V2
emits16 expiration headers and uses17-row lookahead. Legacy v1 remains32/33.
One tuple means one exact path; no caller chooses a path or owner. Actual16-cookie
ASGI/CORS/security headers measured4315 bytes, or4388 with example Uvicorn/status
headers. This is an internal response budget; actual production proxy/header
limits and maximum configured origins still require acceptance.

V2 replies contain the existing seven bound revocation-page fields plus literal
cookie_inventory_version:2. A null final v1 cursor cannot certify v2 cleanup.
Valid old progress is completed under v1 first, then v2 starts from null using the
same committed app-revocation receipt/time. Partial progress survives failures.
Already-complete old app proof remains distinct from new cookie-inventory proof.

## Global provider acknowledgement

Global logout records explicit durable global intent before app revocation under
the existing project exclusive lock. Pending global intent blocks account
replacement and same-session media reactivation; ordinary local revoke cannot
satisfy it. Rotated credentials for that same provider session can still persist
without reactivating media, so a failed transition does not discard refresh data.

App revocation and cookie pages run under that lock. The provider fetch runs
outside it; holding the lock through SDK storage removal would deadlock its
wrapped storage boundary. Only accepted provider status, durably retained provider
acknowledgement and current inventory completion permit final global proof.
Provider-response loss, failed journal writes and reload retain explicit retry
state. A known acknowledged provider operation is not repeated to upgrade cookie
inventory or repair a local completion write. Legacy controller global completion
proof must retain its provider acknowledgement even if its separate transient
acknowledgement key was already cleaned.

The bound global intent descriptor is not a loose allow-inactive switch. Owner,
session, backend and durable transition state must agree. No Auth API executes
inside the exclusive callback. Native v1 wire shapes remain, with the same durable
global-intent/acknowledgement safety at the accepted-session boundary.

## Remaining acceptance

The local Chromium experiments used synthetic loopback HTTP cookies and cached
Chromium149 with a Playwright engine-version mismatch. They demonstrate late
restoration and finite namespace isolation; they do not establish production TLS,
Secure/SameSite behavior, current WebKit/Chromium, hosted SQL or application identity.

Playback and thumbnail consumers now use the supported session namespace:
playback has typed native headers/credentialed web video; thumbnails use bounded
credentialed fetch into memory images. Finish analyzed-export/archive consumer
migration and bounded downloads before activation.
RNWeb Image does not forward crossOrigin to its hidden image/loader; Expo Video
does forward it to its web video. Direct download navigation does not meet the
current required-Origin byte contract. Resolve those actual callers without an
unbounded Blob or a broad Origin exception. Verify same-site custom application
and API/media origins, not the cross-site default Netlify/Render hostnames.

Required launch tests still include two owners, expired/revoked sessions, refresh,
old progress, reload and lost replies, delayed headers across tabs/unload, actual
native cache/decoder/release behavior, hosted ACLs/provider policy and all other
launch gates. Existing historical URLs, provider completed-orphan/backup settlement,
complete account deletion and the unexplained normalizer failure remain separate.
