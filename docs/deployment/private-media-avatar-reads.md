# Private avatar readers

Local source preparation; all private-media flags stay OFF. This is not managed
provider, browser/native, migration or public-launch acceptance.

## Resource and retained authority

Avatar capability resource IDs are the current random profile_revision, with
resource kind/asset avatar. A dedicated service-only invoker SQL issuer and byte
authorizer share the existing hash-only random256bit retained grant table. They
resolve current owned profile+revision+path to the exact succeeded, published,
immutable avatar write. Provider/bucket/type are Supabase/profile-avatars/JPEG;
size is1..524288, normalized hash and attempt-derived path are required. The write
ledger's profile_revision is the PREpublication expectation, not the current
published profile generation. Later legitimate text edits may use the same avatar
write, but rotate profile revision and invalidate old grants. Historical published
name fields do not authorize the current profile.

Owner-first lock order, bounded waits and fresh provider/app-session/wallclock
checks fence publication, logout and owner tombstones. SQL authorization occurs
per request, not per output chunk; bytes already received or an authorized request
already in flight cannot be recalled. The backend strictly validates returned
identity/ledger fields before object metadata/signing, requires retained object
length and the exact signed provider pathname, and proxies bytes with no-store.
The retained SHA is validated metadata, not a fresh byte-content hash claim.

Browser issuance uses existing exactOrigin/issuinghost +Secure/HttpOnly/SameSiteStrict
host-only cookie scoped /private-media/session/{verified_session}/avatar/{revision}/.
Avatar browser byte requests require issuinghost, allowedOrigin and retained grant
session equal to the URL session before object metadata/signing. Native v1 paths
remain unchanged. See [browser session protocol](private-media-browser-sessions.md). Native sends account Bearer
only to issuance, random media grant only in X-Peso-Media-Grant to byte routes.
No query credentials, arbitrary owner/path/provider selectors or account JWTs at
byte routes. Existing server-side provider URLs are never returned to clients.

Logout inventory includes archive,avatar,video sorted keyset paths. Browser v2
adds retained session IDs plus an explicit NIL legacy-path sentinel and16/17
paging; native/legacy v1 remains32/33. Exact local
session/global owner filtering and retained paths survive profile deletion,
replacement, grant expiry and resource metadata loss. SQL/backend and all three
client cookie-progress validators must deploy together; old bundles that reject
avatar cursors cannot remain active during avatar issuance.

## Client boundary and legacy compatibility

Native Profile/Settings load/save/upload share one typed avatar reader. It
validates configuredHTTPS backend, exact currentrevision issuance/byte routes,
strict response shape/expiry/credential, bounded streamed response and JPEG body.
It renders a data image from memory; grants/dataimages are not serialized to
AsyncStorage, app cache, logs or temporary files. Account session/epoch, local
profile mutation and observed revision fences abort/drop late work and clear
mounted avatar images. Metadata remains usable after an image-only error, with
explicit retry. Uncertain metadata writes are not replayed automatically.
FeatureOFF and existing web account UI use initials; no web avatar feature is added.

An explicit409 from the dedicated issuer denotes a live owner's CURRENT safe
legacy pointer with no retained ledger for that path. It returns no grant/cookie.
Client metadata remains editable and asks for reupload. Present malformed,
unpublished or wrong-owner ledger records are denied, not classified as legacy.
No historical object/ledger is fabricated, rewritten or deleted by reader code.
Existing legacy bytes remain preserved for separately approved inventory/import
or reupload. Denying old readers does not prove legacy migration complete.

A subtractive restrictive authenticated SELECT policy denies new avatar SDK reads/
signing without granting access or changing otherbuckets. Previously issued URLs
survive until provider expiry/retirement; a new policy cannot recall them. Actual
hosted role/policy/inventory and old-client retirement must precede cutover.

## Native and rollout acceptance limits

The bundled expo/fetch reader exposes streams but no JS cachepolicy option.
Requests require no-store and responses must carry no-store; rendering data images
avoids credentialed RNImage URL requests and their file-backed image cache. This
does not independently prove that the native HTTP stack stores no bytes. Actual
URLSession/OkHttp cache inspection, device decoding/memory lifetime, abort/background/
foreground and release behavior remain mandatory. Clearing React state is not a
physical-memory erasure claim. Keep activation blocked until these are established
or a verified native cache-policy adapter is supplied.

Session-namespaced paths and exact server revocation isolate late old-session
Set-Cookie responses from incoming identities; expiration headers do not prove
physical cookie absence. Remaining issuance/consumer migration and browser tests
must verify this supported protocol after logout. Historical one-hour avatar URLs, Azure/other capabilities, provider caches,
backup retention and completed-orphan settlement remain separate open boundaries.
The earlier intermittent backend normalizer failure remains unexplained despite
unchanged passing diagnostic/ordinary runs; this change is no evidence of its fix.
No hosted mutation/public exposure/paid resumption follows from local tests.

## Required verification

Dedicated realPostgres tests cover exact current assignment/owner/session, legacy
classification, invalid ledgers, expiry/lock waits, profile edits/replacement/
recreation, logout/tombstones, roleACLs/readpolicy and mixed cookie inventory.
Server tests cover strict contracts, browser/native credentials/headers/GET/HEAD/
Range, providerpath/length/cancellation failures. Project-only client mocks cover
bounded bodies, malformed/expired/cross-scope replies, release/revision races,
metadata/reupload UX and noStorageSDK fallback. Join these with existing session/
profile regressions, SQL audit+mutation tests, CI, TypeScript, fixture build/budget,
image runtime/scan and exact committed-source scan. These are local proofs; real
two-owner/provider/browser/native/hosted recovery/release gates remain required.
