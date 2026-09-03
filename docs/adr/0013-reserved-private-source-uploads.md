---
status: accepted
---

# Reserve private source uploads before analysis

Peso will keep Supabase Auth and Postgres while moving new source videos to private Azure Blob Storage. A server-owned Upload Reservation atomically allocates user/global capacity before issuing an exact-blob, HTTPS-only, create-only user-delegation SAS; completion establishes a Verified Upload from actual media metadata before a Container Apps Analysis Job may be queued. This replaces direct client writes to the Supabase video bucket because storage ownership alone did not enforce capacity or actual media limits before work was admitted.

## Consequences

- The Student environment remains a controlled, non-production proving ground; this decision does not switch the production frontend or authorize uncapped growth. A paid subscription and separate production acceptance remain required.
- Create-only permission permits a single new-blob PUT but not overwrite, preventing an upload-token replay from modifying already verified bytes. SAS cannot enforce a byte ceiling at the storage edge: oversized objects are rejected on completion and expiry cleanup removes abandoned objects. Small capacity limits, short SAS expiry, and delayed-cost alerts are complementary controls, not a guaranteed hard spending cap.
- Media Validation Jobs run during the completion request, with database validation leases capped at two, a bounded download, and a bounded local-only ffprobe invocation. They are distinct from technique-quality preflight and from the separate Container Apps Analysis Job.
- Postgres remains the authoritative durable analysis queue so reservation consumption, per-user limits, and enqueue are transactional. Container Apps Jobs retain the existing Postgres scaler and are capped at one execution by default, configurable only to two. The provisioned private operational queue is not an alternate analysis-admission path.
- Existing private playback derivatives and exports remain in Supabase; all video URLs still go through owner-checked backend routes. Legacy source paths remain readable for migration/rollback, but unverified legacy videos cannot start a new analysis after the new enqueue migration is applied.
- One-time storage/delegation and budget-workflow RBAC is provisioned by a privileged operator, separately from routine image deployment. Neither runtime nor deployment requires Azure account keys.
- Budget admission shutdown is latched in Postgres. Redeploying or restarting the API does not re-enable it; resumption requires an explicit operator review and database change.

Azure documents [create versus overwrite permissions](https://learn.microsoft.com/en-us/rest/api/storageservices/put-blob) and [user-delegation SAS authorization](https://learn.microsoft.com/en-us/rest/api/storageservices/create-user-delegation-sas). See the [staging acceptance and rollback gate](../deployment/production-security.md).
