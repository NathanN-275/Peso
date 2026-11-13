# Analysis metadata publication fence

Private media remains disabled. This migration and worker revision require a
coordinated deployment after recovery and migration acceptance; they are not a
hosted rollout. Old workers lose EXECUTE on unbound lease control functions and
must be drained before the replacement runs.

## Implemented boundary

The worker validates a claimed canonical job/video ID, processing state and
positive integer attempt count before starting its heartbeat or child. The
worker ID and the exact claim attempt travel through the runner and spawned
child into the pipeline. `analyze_video` requires those fields. Its repository
is bound before loading or writing media metadata. There is no unleased result
upsert fallback.

Every pipeline video status, duration, frame rate, thumbnail/playback path and
analysis result write calls service-only `publish_video_analysis`. Its shared
invoker helper locks video then job NOWAIT, and requires the exact video/job,
worker and attempt, processing state, finite unexpired lease, no discard,
pruning, expired/nonfinite media deadline or deletion outbox. Wall-clock expiry
is checked after locks; result writes check expiry again after a possible
unique-index wait and roll back if it elapsed. Publication has a two-second lock
timeout; lock contention fails closed and may require a later queue retry.

The RPC rejects arbitrary video fields and invalid values or owner-bound paths.
It preserves one analysis result per video/model and its ID across transport
retries. Repository responses must identify the requested video/result, and
lease control requires real booleans or an exact one-row/name envelope. Missing
RPCs, malformed responses and denial cannot invoke legacy table writes.

Renewal, stage reporting, completion and failure all require the same generation
and live-video proof. Reusing a worker ID cannot authorize an earlier attempt
against a later claim. Old unbound renewal, progress, completion and both failure
RPCs have EXECUTE revoked from service_role and client roles. Claim and expired
lease recovery lock video before job with SKIP LOCKED and recheck the resource;
claim cancels unusable queued/retry jobs (including future backoff) so they
cannot pin active quotas or retention, and recovery cancels unusable jobs without rewriting
their video. Recovery's existing retry/failed counters exclude those cancelled
jobs. Live-media retry/backoff, limits and return shapes remain.

Publication first commits legitimate metadata that a later revoker can tombstone;
revocation first makes the waiting publisher deny. A failed pipeline attempts
only the same fenced failed-status write and preserves its original exception
if that write is unavailable. Final asset generation remains best effort, with
all metadata assignments still fenced.

## Remaining launch work

This change does not make Storage and Postgres atomic. Current thumbnail,
playback, rendered export and archive object names can be reused, and uploads
can finish after a cleanup snapshot was acknowledged. Best-effort removal after
a denied metadata assignment does not provide a durable cleanup guarantee.
The thumbnail backfill and ordinary upload/preflight/API `update_video` callers
are outside the bound pipeline. Arbitrary direct service-role SQL is trusted
and retains table privileges. These boundaries must be completed before launch.

The next object protocol must register a durable owner/video/bucket/path upload
intent before uploading; use a unique publication generation in the object
name with create-only upload; atomically assign the accepted intent under the
same video/attempt lock; and retain rejected/uncertain intents for durable
cleanup. A losing writer must never delete another generation's valid object.
A cleanup acknowledgement cannot discard unresolved in-flight intent merely
because its local timer elapsed or a listing was empty. Process death and
ambiguous network completion need explicit reconciliation; an unverifiable
upload must keep deletion pending. Intent records must survive metadata removal.

Reanalysis currently upserts the same analysis ID while changing its payload.
Rendered export keys and private grants use that ID, so the object protocol must
also bind a content fingerprint or publication generation. A stale artifact or
grant must not silently authorize a different analysis or mutable bytes.

Direct analyzed exports, archive members and backfill must use the same live
resource admission and durable upload protocol. Their current read-then-upload
checks and deterministic names do not close the race. Account-level admission
fencing, Saved Lift deletion receipts, all client media paths, legacy URL
retirement, real provider/browser/native tests and protected release acceptance
remain separate launch prerequisites.


## Required database CI

The security workflow runs provider-session, grant, revocation, archive and
analysis publication suites in separate PostgreSQL17 matrix jobs. Each uses its
own exact localhost database and environment variable. The runner rejects zero
cases, skipped cases and failures. The existing required
`reservation-database-security` job always evaluates the matrix result and
fails unless every matrix job succeeded, then runs the reservation suite.
A failed dependency cannot be accepted as a skipped required job. PostgreSQL
health probes use TCP so the temporary initialization server is not mistaken
for the final ready server.

This follows [GitHub's job dependency behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs).
Local workflow/runner checks do not prove a protected GitHub run on the release
SHA. The active production ruleset still requires the existing database,
container, backend, frontend, secret, source, marketing and historical Netlify
checks. The new combined target and final release checks remain unverified.
