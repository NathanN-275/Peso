# Avatar write and profile publication

Avatar updates now use a retained owner/session-bound write attempt and an atomic
profile publication. The client no longer uploads or deletes Storage objects or
upserts profile metadata directly. Auth initialization reads the backend profile
and creates only an actually absent row; it preserves an existing username and
display name. All calls retain the original access token and reject responses
after the captured owner, session or media epoch changes.

## Admission and publication

`private_media_avatar_writes` retains each immutable attempt after profile,
session or Auth loss. A unique `owner/avatar-attempt.jpg` key receives one
create-only dispatch. The ledger records the normalized JPEG's actual size and
SHA-256, expected profile revision, previous avatar path and capacity limits.
Typed RPC receipts and a separate committed readback must agree before dispatch.
Every admitted attempt remains charged under the shared user/global media caps,
including failed or uncertain writes. API success is only an observation.

Profile rows have a random `profile_revision` that rotates on every insert and
update, including same-value updates. A null expected revision means that the
row is absent. Admission locks the owner, exact live provider/app session and
profile before taking capacity locks. Publication rechecks that boundary and the
expected revision/path, then atomically publishes the ledger and profile fields.
An intervening text update, avatar replacement or row recreation rejects stale
publication. Exact publication replay preserves later text edits and cannot
reattach a subsequently replaced avatar. New nonnull avatar paths require a
matching observed published attempt, including for service-role profile writes.

`GET /profile` returns the owned profile or actual absence. `PUT /profile` saves
text with revision comparison. `POST /profile/avatar` accepts a bounded raw image
with the expected revision header; `POST /profile/avatar/{attempt}/publish` commits
its avatar and text. Metadata, upload and publication writes disable automatic
localhost fallback: an uncertain response never triggers another dispatch.
The client validates the owner, revision and response shape before use. Conflict
handling offers an explicit profile reload. Superseded or uncertain objects are
retained; no compensating deletion claims cleanup.

## Bounded image processing

The backend accepts at most 512 KiB of JPEG, PNG or WebP. The existing FFmpeg
installation normalizes the first frame to a maximum 512-pixel JPEG and strips
metadata. A separate Linux child has no service credentials, a minimal environment,
pipe-only input protocols, a 256 MiB address-space limit, CPU and output limits,
one normalization slot and an eight-second timeout. The parent kills and waits
for the child before releasing the slot on failure. No new image dependency is
introduced. The exact normalized output is bounded and hashed before admission.

## Rollout and remaining boundaries

Install the matching migration, backend and client together while media intake
is stopped. Retire old clients' avatar Storage INSERT/UPDATE/DELETE policies via
the restrictive backend-only policies in this migration. They add denials rather
than granting new access. The matching reader migration denies legacy avatars without retained write evidence
and offers explicit reupload while preserving historical bytes; it does not
rewrite or erase them. Old in-flight uploads
must be reconciled separately because a database policy cannot cancel a dispatch
already accepted by the provider. Metadata/profile routes fail closed unless
private media and the Supabase storage provider are enabled. New avatar admission
also requires upload reservations, the US IP boundary and the intake guard;
already admitted publication can finish after intake stops.

The [avatar reader boundary](private-media-avatar-reads.md) replaces client signing
with current-revision grants and bounded in-memory JPEG delivery. Already issued
Storage URLs remain a historical capability to retire; source replacement alone
cannot revoke them. Actual native cache, provider/browser, coordinated old-client
retirement, Azure/historical capabilities and owner-wide cleanup remain required
before launch. `private_media_avatar_write_pending`
is an owner-wide pending predicate; an unrelated avatar must not block deletion
of every individual lift. The ledger has no settlement setter. Provider orphan
and backup disposition remains unresolved under the approved support request.

Local tests model SQL/Auth/Storage tables and controlled I/O. They do not certify
managed-provider behavior, native devices, hosted configuration or physical
erasure. No hosted migration follows from this source change; media flags stay
off and public, destructive and paid actions retain their separate approvals.
