# Private media HTTP transport

This transport is disabled by default. It prepares the replacement for client
Storage URLs; enabling it alone does not complete media revocation or the public
launch gate. Existing URL issuers and clients still require migration.

## Requests and credentials

Native `POST /private-media/{video|archive|avatar}/{resource UUID}/session`
requires the captured account Bearer. Browser issuance uses
`POST /private-media/session/{provider-session UUID}/{kind}/{resource UUID}/session`.
Its URL session must match the independently verified Auth context; it cannot
select another owner or session. The JSON body contains transport and asset_kinds.
The old browser issuance/read routes reject with an update-required response;
v1 native routes and controlled legacy cookie cleanup remain available.

Avatars use their dedicated current-profile/retained-write grant RPC with only
asset avatar; resource UUID is the current profile revision. Archives use archive.
Video assets are playback, thumbnail, export:clean, export:pose, export:barbell and
export:pose-barbell. Native requests retain their selected subset. Browser video
grants use this fixed existing six-asset domain so a delayed same-session narrower
response cannot remove playback/export scope. Per-byte owner/session/current
resource/retained-artifact checks still apply; an asset grant never creates an
export or makes an unavailable artifact readable.

Browser issuance requires exact approved Origin and issuing host. It sets the
Secure, HttpOnly, SameSite=Strict, host-only __Secure-peso-media cookie at
`/private-media/session/{verified session}/{kind}/{resource}/`. Byte GET/HEAD uses
that namespace and checks the retained authorized grant session against the URL
before object metadata/signing. Late cookies from a different provider session
cannot replace the incoming session's path. They can remain physically present;
server revocation, cookie header completion and physical erasure are separate.
Browser JSON has fixed asset URLs but no grant token. Credentialed requests must
carry Origin; installed RNWeb Image does not implement this contract by adding a
crossOrigin prop, so consumer migration needs the actual image adapter.

Native issuance returns media_grant in JSON. Native clients send it only in
X-Peso-Media-Grant to byte GET/HEAD, without account Authorization, cookies, Origin
or Sec-Fetch metadata. This is a transport distinction, not device identity proof.
Returned URLs contain only resource/session identifiers and asset names. SQL stores
only the SHA256 of the random256-bit grant. Query strings and mixed byte credentials
remain rejected. See [browser session protocol](private-media-browser-sessions.md)
and [avatar readers](private-media-avatar-reads.md).

Each GET/HEAD reauthorizes the digest, resource and asset through the current
provider/app-session and video/archive or current-avatar predicates before Storage metadata,
signing or opening an upstream byte request. Metadata uses an owner-scoped query
and validates every selected path. Missing or failed assigned derivatives never
fall back to original bytes. Export GETs read an existing artifact; rendering
must be completed by a separately authorized operation.

## Global logout receipt

Native logout/replacement keep v1 endpoints. Browser clients use
`POST /private-media/v2/logout` and `/private-media/v2/session-replacement` with
transport and optional cursor; verified context selects owner/session/scope.
Global operation ID remains the verified provider-session UUID, while local
replacement uses its distinct existing stable operation. Retries return the same
committed revocation time and cutoff.

V1 pages have scope, owner_id, session_id, completed_at, replayed, next_cursor and
cookie_cleanup_complete. V2 adds literal cookie_inventory_version:2, uses retained
legacy and session-namespaced cookie paths, and emits16 expiration headers with
17-row lookahead. V1 stays32/33. A final null v1 cursor cannot certify v2 completion.
Client compact global receipts retain the inventory version separately from provider
acknowledgement; an app-only receipt never proves provider logout completed.

The accepted-session controller records explicit global pending intent before app
revocation, blocks replacement/reactivation, and releases its project lock before
provider I/O and SDK storage removal. Only accepted provider status plus durable
acknowledgement and matching inventory completion permits final global proof. Same
provider-session refresh can persist rotated credentials while media stays blocked.
Legacy inventory upgrades preserve the committed app receipt time and reuse any
existing provider acknowledgement without repeating global provider logout. See
[browser session protocol](private-media-browser-sessions.md) for compatibility and
failure limits. Provider denial/expiry and lost credentials can still prevent
historical proof recovery; no expired-JWT exception is introduced.

Unexpected media failures before response headers return generic503 with
private/no-store and nosniff. Failures after streaming starts terminate the
response with sanitized error text. Cancellation remains cancellable.

## Configuration and behavior

`PRIVATE_MEDIA_ENABLED` defaults false. `PRIVATE_MEDIA_PUBLIC_ORIGIN` and the
comma-separated `PRIVATE_MEDIA_BROWSER_ORIGINS` must be exact HTTPS origins at
usepeso.com or its subdomains, without ports, credentials, paths or wildcards.
Each browser origin must also be in `BACKEND_CORS_ORIGINS`.
`UPLOAD_STORAGE_PROVIDER` must be `supabase`. This deliberately rejects the
default Render hostname and cross-site browser cookies; the approved custom
API/media hostname, proxy handling and TLS must be verified before activation.
The verified provider-policy migration remains disabled until its separate
hosted attestation prerequisites are met.

Media responses are private/no-store and nosniff, including validation, query,
method and denial responses. Media bypasses gzip to preserve Range offsets;
ordinary API JSON still compresses. Range GET, HEAD, bounded chunks, strict
upstream length/type/status validation and disconnect cleanup use the shared
async transport. Storage URLs remain server-side and expire within 60 seconds.
Upstream requests do not inherit client cookies, media grants or account JWTs,
and do not follow redirects. CORS exposes range/download response headers.

Authorization has a 10-second response deadline. At most 16 synchronous SDK
authorization threads can remain active per process, including abandoned
requests; excess requests receive 429. A cancelled request marks its worker so
later metadata/signing calls stop between SDK calls. An SDK call already in
progress can finish within its configured network timeout; cancellation cannot
undo it. Streaming permits remain four per owner and 16 per process. These are
process bounds, not fleet-wide quotas or hosted load acceptance.

## Remaining launch work

Do not enable this path until legacy playback/thumbnail/export/archive issuers
and web/native consumers are migrated, logout has retry-safe durable app
revocation before provider sign-out, deletion invokes atomic revocation before
Storage cleanup, and job/publisher fences are complete. The prepared shared outbox consumer and
exact-snapshot finalizer are described in [private-media-deletion-cleanup.md](private-media-deletion-cleanup.md); route wiring and hosted acceptance remain open.
Retire previously issued URLs using the approved Saved Lift preservation and
recovery plan. Requests authorized before a revocation commit can already be
in flight; bytes already delivered cannot be recalled.

The [upload reconciliation probe](private-media-upload-reconciliation.md) rejects
tenant TUS/REST alone as sufficient cleanup proof for the tested crash window.
An unresolved upload must remain pending even when ordinary deletion reports
not found. The read transport does not settle that separate upload contract.

Required acceptance still includes exact hosted migrations and ACLs, complete
provider-policy readback, actual logout/reuse and two-owner races, real browser
and native cookies/headers/ranges/expiry/account switching, proxy/custom-host
and streaming behavior, load bounds, backup/recovery and all other launch
gates. Local mocks do not establish these hosted properties.

## Static migration audit binding

The source audit permits only the exact reviewed provider-session migration
SHA256 for the two boolean SECURITY DEFINER Auth readers. It rejects changed
definitions/default policy, duplicate definitions, changed direct privileges,
ownership/search-path alterations and broad public-schema function grants.
Every other unexpected privileged function remains blocked. Mutation regressions
run in the security workflow. This static source check is not a SQL parser or
proof of deployed ACLs; separate real PostgreSQL service/client-role tests and
fresh hosted verification remain required. The provider policy stays disabled.
