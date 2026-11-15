# Current analyzed-export publication

Overlay exports now use immutable attempt keys and the same service-only
generated-write ledger as thumbnails/playback. Admission binds owner/video,
effective playback source, variant, actual output size, analysis ID/model and
the exact rendered result JSON. SQL compares that JSON with the current row and
stores its SHA256 fingerprint. A reused analysis ID cannot silently reuse an
older result's export. Latest analysis selection consistently orders by
`created_at DESC, id DESC` when timestamps tie.

Admission and independent readback precede create-only upload. API success is
observed separately and remains recordable after resource/owner deletion.
Publication requires the observed attempt still match a live completed Saved
Lift, its current playback source and current analysis, with no active analysis
job. The publication response and a separate committed readback must both
validate before the producer returns the path. Lost responses preserve tracked
bytes; no automatic upload replay or compensating deletion occurs.

## Cache and downloads

The cache resolver returns only a successful published attempt for the current
source and analysis fingerprint. Expiry is anchored to admission time, preceding
the external object's creation, using the existing configured cache lifetime.
Publication is idempotent without extending that lifetime. An expired or absent
database publication permits a fresh attempt, subject to existing render cooldown,
work-slot and storage-capacity limits. Older generations retain their pending
charge and cleanup identity.

A cache hit must have metadata whose byte size matches its admitted generation.
Every metadata failure, including object-not-found, fails the request rather
than triggering another render. [Supabase documents](https://supabase.com/docs/guides/storage/debugging/error-codes)
that missing-key responses can also indicate unavailable permissions; they do
not establish why a cached object cannot be read or prove backing-byte erasure.

Private media export GET resolves the current publication through SQL and checks
its byte size. It no longer constructs a deterministic legacy export filename
or generates files during GET. The existing grant, owner/session, resource,
signed-upstream and streaming checks remain in place. Clean exports continue to
use the current playback/source path without generating a derivative.

## Cleanup and deployment

Exports share the generated ledger, so all pending/successful states count in
source and generated storage admission. Existing revocation/expiry snapshot
logic includes every admitted key, published or not. The shared pending predicate
blocks finalizer and Saved receipts even after Auth/video metadata disappears.
No setter declares a write settled or a provider generation erased.

Required CI includes real PostgreSQL stale-snapshot, same-ID update, deterministic
ordering, source change, publication, privileges, deadlines, capacity and lock
cases. Backend tests cover exact receipt/readback validation, uncertainty, cache
read failures, private GET and producer wiring. They are local synthetic evidence.
The managed Storage/PostgREST build and actual hosted behavior remain acceptance
work. Existing direct-video Storage capabilities and raw signed URL issuers must
still be retired during the separately approved cutover.

[ZIP archives](private-media-archive-writes.md) now add retained create-only
attempts, full-selection snapshot admission and atomic frozen-package publication.
Avatars, Azure write capabilities, historical dispatches, complete owner-wide
deletion and coherent session replacement remain unfinished. Provider settlement
and orphan/backup semantics remain unresolved; public media stays disabled.
No hosted migration or launch gate is accepted by these local changes.
