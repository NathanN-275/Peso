# ADR 0009: Use one durable analysis queue across clients

## Status

Accepted

## Decision

Native mobile, the Expo web simulator, and the authenticated Netlify Web App
enqueue the same server-owned Analysis Job. PostgreSQL `analysis_jobs` rows are
the source of truth; the API only
enqueues and reports owner-scoped activity, while a separately running Python
worker claims leased jobs, renews leases, and retries failures up to three
times. Clients may leave after queue confirmation and restore Analysis Activity
from the server when they return. This supersedes ADR 0006's web-only boundary
and avoids process-local FastAPI background tasks that can be lost on restart.

Each claimed job runs in an interruptible child process. Normal clips have a
180-second deadline; longer clips scale by duration up to ten minutes. Public
stage transitions and worker heartbeats are persisted with timestamps.
Deterministic invalid-video and timeout failures stop immediately; transient
storage and network failures use the queue's three-attempt retry policy.

## Consequences

- Upload and recording-quality checks still require the client to remain open.
- Worker capacity controls execution concurrency without preventing jobs from waiting in the queue.
- Completed unsaved analyses remain reviewable for the existing 24-hour retention window.
- Production requires the migration, API, and at least one continuously running worker.
- The authenticated Web App does not ship fixture analysis results or fake
  progress timers; marketing preview media remains independent.
- Faster analysis profiles remain flag-controlled and can immediately roll back
  to the 18 FPS/720 px profile.
