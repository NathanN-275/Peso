# Private media upload reconciliation

The October28 local probes reject ordinary tenant TUS/REST and tenant S3
multipart abort/delete alone as sufficient upload/deletion protocols for the
tested Supabase Storage release. Do not replace
`StorageService.create_file` with TUS on the assumption that a resumable handle
makes all late writes and orphan bytes reclaimable. Private media stays disabled;
deletion receipts still prove application snapshot cleanup, not settled uploads
or physical erasure. No production transport or hosted configuration changed.

## Observed counterexample

A disposable official Storage v1.84.34 server used Postgres locking and the
vendor's local S3 fixture, RustFS1.0.0. Each upload started with an empty TUS handle
and positive declared length before sending synthetic media. An exact-path SQL
trigger paused the actual object metadata INSERT, after backing completion and
outside the rolled-back permission probes (which use version `1`). This trigger
was fault injection in the disposable database only; never install it in hosted
Storage metadata.

With metadata paused, a TUS DELETE returned400, "Cannot terminate an already
completed upload". Releasing the pause let the original PATCH return204 and commit
a readable12MiB object. A failed termination is not a cancellation certificate.

In a separate upload, killing and restarting Storage at that pause retained the
S3 backing store and database. The original metadata transaction rolled back.

| Observation after restart | Result |
| --- | --- |
| Backing object |12MiB present, plus542-byte TUS `.info` sidecar |
| `storage.objects` | No matching row |
| TUS HEAD |200, offset equals declared length, no object ID/version headers |
| TUS DELETE |400, refuses termination of completed upload |
| REST DELETE with known provider version |400 with structured404 `NoSuchKey` |
| Zero-byte PATCH at final offset |500, multipart upload does not exist |
| Readback after those attempts | Same backing bytes and sidecar; metadata absent |

Thus neither full offset, API metadata absence, ordinary delete `NoSuchKey` nor
zero-byte replay resolves this crash window. Empty/partial cancellation, an
open request body and an explicitly lost Postgres lease did leave no managed
object in the tested cases, but those successful cases do not close this gap.

## Tenant S3 multipart follow-up

The same pinned local server's S3-compatible API does not close the gap. A normal
incomplete two-part upload aborted successfully (HTTP 200), then ListParts returned
NoSuchUpload and no completed backing object remained. The first observer had
assumed AWS's 204 abort response; that failed attempt is retained, then corrected
without changing provider behavior.

For a separate two-part upload, the actual metadata commit was paused only for
the generated version of its exact bucket/path. After direct backing readback
confirmed 12 MiB, only the API was killed/restarted; Postgres and backing S3 stayed
alive. The original completion client ran inside that disposable API container
and ended with exit 137. This is not a test of arbitrarily delayed external clients.

After restart, AbortMultipartUpload returned **200 success** and removed the
provider multipart ledger row (one to zero), while the completed 12 MiB remained.
Tenant DeleteObject then returned **204 success**. HeadObject returned 404 and
REST exact-version deletion returned 400 with structured NoSuchKey; metadata was
absent and the completed backing object remained. Thus even a successful tenant
abort followed by successful tenant deletion is not an erasure certificate for
this tested crash window. No hosted affectedness is inferred.

The reviewed source explains this: completeMultiPartUpload completes backing
bytes before completeUpload commits object metadata; abortMultipartUpload treats
backing NoSuchUpload as success and then removes the multipart record. Ordinary
object deletion still requires metadata to select the backing generation. The
project's S3 endpoint is not raw access to its internal backing bucket.

[Supabase's S3 upload guide](https://supabase.com/docs/guides/storage/uploads/s3-uploads)
documents aborting incomplete uploads and an automatic 24-hour abort. It does not
establish completed-orphan cleanup or a terminal receipt for this crash window.
Do not replace that missing contract with a 24-hour timer.

The follow-up prototype is captured on standalone branch
`prototype/tenant-s3-quiescence-20261028`, commit
`f00a73981239108bde44a8e9c23f576a86803fc7`. Verified bundle SHA256:
`0ba2d25640aae867a1217aa7607381af08bc684f1d2066e6061597dc5fef29cd`.
[Evidence packet](/Users/nathan/.codex/visualizations/2026/10/23/01a16692-8c4a-7f93-a124-c243a95c6eac/gate4-tenant-s3-quiescence-20261028-v1/README.md)
retains both attempts, source and logs. Both final scenario assertions pass and
all owned fixtures are removed. Nothing was run against hosted Storage, no
hosted S3 key was created, and no transport or feature flag changed.

Nathan authorized the exact private provider-support request on October 28.
The dashboard confirmed it was sent for PesoDatabase, asking for the actual
managed build/configuration, a supported exact-generation orphan reconciliation
path and cleanup/backup retention semantics. Optional human/AI project access
was off; no attachments or credentials were sent. No ticket ID was displayed.
The provider response and supported cleanup contract remain pending.

## Source and evidence binding

Official image:
`supabase/storage-api@sha256:4cb75cee56eaca2a6e9544fa998161dfc6d6b5d4797efd1f2b40d0b93622a589`.
Official release source:
[`b6a70fc7e7da00b5fbd5e194bb347dfe13cba793`](https://github.com/supabase/storage/tree/b6a70fc7e7da00b5fbd5e194bb347dfe13cba793).
The observed version/tag match does not provide a cryptographic source-image
attestation. Exact lockfile-pinned `@tus/server2.4.6` and `@tus/s3-store2.0.9`
tarballs were verified against SHA512 integrity and their relevant source retained.

The source corroborates the result: the TUS lock is released before metadata
completion; HEAD decorates IDs only for an existing row; completed uploads refuse
termination; REST version deletion requires the row; final-offset S3 PATCH reads
parts of an already completed multipart upload before rerunning completion.
Source review also found that S3 removal ignores per-object `DeleteObjects.Errors`;
that failure mode was not fault-injected, so a204 alone is not universal evidence
of all backing bytes being removed. The admin scanner is a separate age/bucket
operation with different authorization and backup behavior; it is not a verified
tenant reconciliation primitive.

The throwaway prototype is retained outside the application branch:

- Branch: `prototype/storage-quiescence-20261028` in the standalone captured repo.
- Commit: `aea57c81caf66d128c0bd0d4234490aec0289535`.
- Bundle SHA256: `c6adda7d7b8fef188e3d49a58e0c96dc965cc2a6ca3fc6655329e2024b62a623`.
- [Evidence packet](/Users/nathan/.codex/visualizations/2026/10/23/01a16692-8c4a-7f93-a124-c243a95c6eac/gate4-storage-quiescence-prototype-20261028-v1/README.md)
  includes the bundle, seven run receipts, observer failures, runtime logs, source
  integrity receipts and review. Run the captured probe with
  `python3 prototype.py unique-run-name s3`; it requires the pinned local images.

The final S3 run's seven scenarios and negative-contract assertions pass. Every
owned container/network was removed. These are local synthetic fault tests, not
hosted acceptance, a production regression rerun or proof of physical erasure.
Default query cancellation was false; other settings, arbitrary delays and S3
partial failures were not exhaustively tested. No host ports were published.

## Consequences for implementation

Keep the planned durable intent ledger, immutable per-attempt keys, resource and
analysis-generation publication fences, and exact cleanup receipts. They remain
necessary, but do not solve the provider gap. Preserve unknown outcomes as pending;
never convert a timeout, process exit, list-empty result or expired lease to proof.
Do not modify provider Storage tables or synthesize a row to make deletion pass.

Before selecting the transport, obtain a supported provider operation that can
settle the known upload and remove its exact backing generation after this crash,
with retry-safe evidence and a documented orphan/backup disposition. Prove that
contract locally, then bind the actual hosted Storage version/configuration and
capabilities separately. The project's S3-compatible endpoint must not be assumed
to expose its internal backing bucket. A different storage service, credentials,
new costs or data migration are not authorized merely by this negative result.

Deletion finalization must stay pending for unresolved intents. Account deletion,
all derived publishers and client/session replacement remain separate work.
Continue those independent changes under the existing launch plan; this evidence
does not waive any gate or permit public exposure.
