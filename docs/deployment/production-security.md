# Production-security staging gate

This branch implements the controlled Student-credit beta path. It does not deploy Azure resources, apply remote migrations, change Supabase provider settings, or switch production clients. Do not enable reservation clients until every gate below has evidence from real Azure resources.

See [local verification evidence and unresolved release blockers](production-security-verification.md).

## Deployment order

1. Drain existing analysis work and record the current image digest, frontend build, database backup, migration list, source-object inventory, and restore destination. The enqueue signature change is a coordinated contract change, not an additive-only migration.
2. In the isolated Student environment, apply `202609030001_upload_reservations.sql`. It preserves existing videos and legacy storage policies but rejects new analysis for legacy videos without a verified reservation. Do not apply it to the shared production database until that compatibility impact is accepted and old work is drained.
3. Create a random `budget-shutdown-token` in Key Vault and the matching protected GitHub environment secret. Never place its value or an Azure account key in a source file, app environment file, log, or build artifact.
4. Deploy `student.bicep` with reservations disabled (the default). The API and analysis worker retain their bounded, scale-to-zero settings.
5. A privileged operator reviews and runs `security-foundation.bicep` in exactly `peso-student-centralus-rg`, supplying the exact test web origin, alert recipients, and a stable first-of-month credit-budget start date. This creates private source storage, container-scoped data access, account-scoped delegation permission, the operational queue, the admission Logic App, and 50/75/90% annual-credit alerts. Routine CI has no RBAC-assignment permission.
6. Verify the Storage account has `allowBlobPublicAccess=false`, `allowSharedKeyAccess=false`, HTTPS-only transport, and the exact browser CORS origin. Confirm the runtime identity can delegate only the required blob operations and that an unrelated identity cannot read source blobs.
7. Enable reservations only in Student, build a test client against that API, and run the acceptance matrix below. The scheduled cleanup job is enabled with reservations and runs every five minutes.
8. Apply `supabase/security-cutover.sql` only when reservation-capable clients are the supported minimum version and rollback has been rehearsed. It removes direct video-bucket write/delete policies without changing avatar policies.
9. Production cutover is a separate approval after migration, rollback, retention, capacity, and budget evidence is recorded. Student credit is a beta constraint; paid subscription approval precedes uncapped public growth.

## Required acceptance evidence

| Test | Required result |
| --- | --- |
| Concurrent reservations from two API replicas | User/global count and byte caps are never exceeded; denied requests receive no SAS. |
| Concurrent completion and retry | One video row per reservation; at most two validation leases; repeated completion is idempotent. |
| Foreign-user reservation, playback, export, and deletion | No URL, bytes, or mutation is returned to the other user. |
| SAS inspection | One exact blob, HTTPS, short expiry, `sp=c`; no read/list/delete/overwrite permission. Do not retain the token in evidence. |
| SAS replay before expiry | A second PUT cannot overwrite an existing blob; GET/list/delete are denied. |
| Expired SAS and abandoned upload | PUT fails after expiry; cleanup removes the blob and confirms capacity release. |
| Malformed/renamed media, empty file, false MIME, oversize upload | Completion rejects it; no analysis job is created. |
| Long-but-small video, 4K, 120fps, excessive frame count | Actual ffprobe metadata rejects it even with small/false client hints. |
| Queue saturation and simultaneous enqueue | Database caps hold across API instances; existing jobs remain idempotent. |
| Worker kill, lease expiry, transient failure, exhausted retry | Existing durable retry/recovery behavior holds with no duplicate active job or cross-owner result. |
| 90% alert/action-group test | Logic App calls the authenticated shutdown route; subsequent reservations fail across restarts/deployments. Existing owner retrieval still works. |
| Wrong webhook secret | 401 and no admission-state change. |
| Delete then replay before SAS expiry | Scheduled post-expiry cleanup removes any recreated object; capacity is not released before confirmation. |
| Account deletion during upload | Reservation becomes an ownerless cleanup tombstone; no new access is granted and post-expiry cleanup completes. |
| Private playback/export expiry | URLs expire and can only be reissued by the owner-checked API. |
| Restore and rollback | Metadata/object mapping, RLS, revoked access, and supported client contract are verified in an isolated restore target. |

Store timestamps, resource IDs, image digests, migration IDs, sanitized test outcomes, and measured worker memory/latency. Never store SAS URLs, auth tokens, video bytes, raw ffprobe output, or user profile data in release evidence.

## Rollback

- Pause new reservations using the persistent admission switch before changing a deployed client or API. Keep cleanup running.
- Retain both providers' source-path routing during the rollback window. Do not rewrite or delete legacy source paths until a copied object's byte count/hash, owner access, playback, retention, and rollback have been verified.
- Roll back client/API together. The new enqueue RPC signature is not compatible with the old repository call: restore the prior RPC definition from the previous migration only in a reviewed rollback, or retain the new backend while rolling back the UI. Do not blindly run an old image against the new contract.
- Restoring legacy direct-upload policies is an explicit emergency action, not an automatic rollback. It reopens the retired trust boundary; keep public admission paused until reviewed.
- Database restore does not restore deleted video bytes. Source videos are temporary; saved playback/export retention and backups must be validated separately. Never claim recovery of a deleted object without verifying it.

## Known operational boundaries

- The $100 annual budget is scoped to the isolated Student resource group. It is not an authoritative balance of the whole Student subscription. Keep the subscription's own credit notifications enabled and include other-resource spending in the operator review.
- Cost Management alerts have reporting delay and do not create a hard cap. The existing stricter $10/month daily cost controls remain in force.
- The default API/worker resources are unchanged from the Student baseline. Passing real 1080p/60fps memory, latency, and cost tests is mandatory; do not silently increase resource sizes to pass.
- Reservation admission accounts for source bytes, including deleted/rejected blobs until post-SAS-expiry cleanup confirmation. It does not promise a storage-edge byte limit or cover every derivative/egress charge.
