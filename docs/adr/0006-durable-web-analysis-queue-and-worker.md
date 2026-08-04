# ADR 0006: Deliver web analysis through a durable queue and worker

## Status

Accepted for post-prototype implementation

## Decision

The API will create a `WebAnalysisJob`, charge the rolling slot, and enqueue a
Supabase Queue message in one database transaction. Anonymous and authenticated
clients cannot read or write the queue directly. A separately deployed Python
worker consumes one job at a time from the same pinned API/worker Docker image.

The database job record is the source of truth. The worker claims jobs with an
atomic status transition, persists attempts and failure classification, and can
resume safely after restart. System failures retry at most three times and
restore quota after final failure. A queued cancellation removes the unsaved
upload and restores quota; losing a race to processing returns `409`.

## Context

Video analysis can outlive an HTTP request and must survive API or worker
restarts. Browser polling also needs stable state after queue messages are
claimed or retried. Quota restoration rules require an auditable, transactional
record rather than best-effort coordination between services.

## Consequences

- Mobile analysis endpoints and behavior remain unchanged.
- Web endpoints operate on server-owned job IDs and owner-scoped projections.
- Accepted jobs consume one of three rolling 24-hour slots.
- Invalid user submissions remain charged; system failures and queued
  cancellations restore their slot.
- Completed unsaved results expire after 24 hours and are removed by scheduled
  cleanup.
- Queue isolation, idempotency, retries, cancellation races, expiry, and each
  quota refund rule require integration coverage before staging promotion.
