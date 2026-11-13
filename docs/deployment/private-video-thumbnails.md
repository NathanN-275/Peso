# Private video thumbnails

Local source preparation. Hosted media remains disabled; this does not complete
current browser/device acceptance, other media readers or the public launch gates.

The actual Home activity cards, Saved Lift folder previews, saved video rows and
web Saved Lift row/grid use VideoThumbnail. Private mode consumes only explicit
thumbnail_available true plus the video ID. List, page, overview and activity
responses return this availability hint without signing a thumbnail URL. Saved
responses also omit the thumbnail Storage path in private mode. The hint does not
authorize bytes or promise a current object exists: the media boundary verifies
owner, accepted provider/app session and current resource before every read.

The existing video issuer now shares a fixed playback/thumbnail implementation.
Browser video issuance still receives the fixed six-asset response and a
session-namespaced host-only HttpOnly cookie. Native thumbnail issuance requests
only thumbnail and receives a media grant. Original account Bearer goes only to
the exact configured HTTPS issuer; bytes use credentials include in browser or
only the media-grant header on native. No query credential or raw provider fallback
exists in private mode. Legacy development mode keeps its earlier URL behavior.

## Memory and image bounds

Thumbnails are fetched into bounded memory on both platforms. This avoids RNWeb
Image's missing crossOrigin/header forwarding while retaining the existing image
widgets. Only the media fetch contacts the backend; the image source is a JPEG
data URI. The app does not write preview bytes or media credentials to files or
AsyncStorage and does not maintain a persistent thumbnail cache.

The preview reader accepts at most4MiB, exact positive Content-Length, status200,
image/jpeg, private/no-store and no redirect. A streaming preallocated buffer checks
every chunk, empty chunks, byte count and context. A30second deadline includes
queueing/issuance/bytes and settles local work even if transport ignores abort.
Two logical reads may run at once; at most64 wait. Cancellation removes queued
work before issuance. The pool bounds local promises, not physical network drain;
backend stream permits independently remain authoritative.

Before either image decoder sees bytes, a bounded marker parser requires an8-bit
baseline JPEG, one frame and one scan containing all frame components, dimensions1..720 by1..720,
valid segment bounds and an exact EOI. It rejects progressive/hierarchical/unknown
formats, trailing payloads and oversized dimensions. This is a resource/format
filter, not a replacement for the platform decoder's full JPEG validation. Base64
encoding uses bounded chunks. The4MiB bound is an optional preview memory budget;
it is not inferred from the storage quota allowance or imposed on videos/exports.
Current FFmpeg generation caps dimensions at720, but has no explicit file-byte cap.
A synthetic real FFmpeg JPEG passes this reader and separately decodes with OpenCV.
Unverified historical formats can show a placeholder; inventory/compatibility
acceptance is required before activation. No old objects were changed or deleted.

## Lifetime and Retry

Requests and displayed state bind session, media epoch, backend, resource and
availability. Release aborts readers and clears mounted image state; late results
cannot repopulate another context. Each open preview permits one automatic
expiry/image-error renewal, then explicit Retry. Missing availability stays a
placeholder; issuance/body errors immediately offer Retry. Retry stops event
propagation to avoid opening/selecting its parent row and has a44px target.
Old decoder callbacks carry their original load generation and cannot discard a
renewed or same-session refreshed preview. Playback uses the same attempt fence; its actual-module regression goes
red on parentf11afce and green with the fix.

These are application memory/lifecycle controls. They do not prove physical
cookie deletion, browser/native decoder cache erasure, transport drain, or recall
of already displayed/exported pixels. Actual native HTTP-cache behavior and
current browser CORS/Secure/SameSite/custom-origin acceptance remain open.

## Verification scope

The new deterministic tests execute the actual Peso transport, parser, React
hook and component with synthetic network/React/Auth-context fixtures. They do
not import or probe an installed Auth SDK, user browser profile or provider.
Backend tests execute actual list/page/overview/activity routes with a signer
that fails if called in private mode. No SQL schema or provider setting changes.
The initial test harness omitted a TS filename when adding JSX support; TypeScript
therefore parsed generic TS as TSX and generated57 diagnostics. Formatting those
raw AST-bearing diagnostics exhausted the test process heap. Bounded probes
isolate that path; the loader now uses real filenames and compact diagnostics.
Application typecheck was independently successful. No production memory fix is
claimed from that harness correction.

Primary references checked November3,2026:

- [JPEG T.81 compressed data formats](https://www.w3.org/Graphics/JPEG/itu-t81.pdf)
- [Fetch credentials and CORS](https://fetch.spec.whatwg.org/#concept-request-credentials-mode)

Analyzed-export/archive downloads, old server playback/export capabilities,
complete deletion/provider orphan/backup settlement and all14 hosted launch
gates remain required. No public, paid or destructive hosted action is authorized
by these local checks. The historical avatar normalizer failure is unresolved.
