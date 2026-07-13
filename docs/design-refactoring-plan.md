# Design Refactoring Implementation Plan

Branch: `design-refactoring`

This plan consolidates the architecture review from both discussions and applies John Ousterhout's principles: deep modules, information hiding, pulling complexity downward, eliminating special cases, and preserving locality.

## Goals

- Keep the application as a modular monolith while its domain is still evolving.
- Make video-analysis lifecycle rules deep, testable, and independent of HTTP.
- Keep Postgres as the system-of-record and object storage as the binary-artifact store.
- Make button actions safe under double taps, retries, timeouts, and app restarts.
- Add read caching without serving stale or invalid signed URLs.
- Make analysis jobs durable and recoverable after process or deployment failure.
- Reduce frontend/backend change fan-out and narrow test/build scopes.
- Make outages diagnosable through explicit errors, readiness checks, correlation IDs, and metrics.

## Non-goals

- Do not introduce microservices yet.
- Do not replace Postgres with NoSQL without measured workload evidence.
- Do not add YOLO or another pose model as part of this refactor.
- Do not rewrite the UI or navigation wholesale before domain seams are stable.

## Phase 0 — Baseline and safety gates

1. Record current branch and worktree state.
2. Run frontend type-checking and existing policy tests.
3. Run the backend test suite from `backend/` using the project virtual environment.
4. Capture current API response shapes and status transitions for upload, analysis, save, export, and discard.
5. Add a short architecture decision record stating: modular monolith, Postgres system-of-record, object storage for binaries, and durable jobs as the target direction.

Exit criteria: all current tests pass and the current behavior is documented before refactoring.

## Phase 1 — Establish backend domain seams

Target structure:

```text
backend/app/video_lifecycle/
  workflow.py
  state_machine.py
  repository.py
  storage.py
  jobs.py
backend/app/analysis/
  workflow.py
backend/app/platform/
  idempotency/
  observability/
```

1. Extract video lifecycle decisions from `backend/app/routes/videos.py` into a workflow module.
2. Keep the route layer responsible only for authentication, request parsing, calling the workflow, and response mapping.
3. Define legal video state transitions in one state-machine module.
4. Hide Supabase queries behind repository methods.
5. Hide storage paths, signed URLs, cleanup, and artifact naming behind storage adapters.
6. Preserve existing HTTP response contracts while moving implementation behind the seam.

Exit criteria: route tests still pass; workflow tests cover save, discard, export, ownership, expired storage, and invalid transitions.

## Phase 2 — Stabilize analysis as a deep computation module

1. Define a stable analysis input contract: video ID, source artifact, exercise, view, tracking setup, and request/model version.
2. Define a stable analysis result contract: metrics, reps, feedback, diagnostics, artifact references, model version, and freshness state.
3. Make pose estimation, pose repair, barbell tracking, rep detection, metrics, and feedback internal stages of the analysis workflow.
4. Keep MediaPipe and RTMPose behind explicit adapters.
5. Persist immutable analysis runs/results rather than treating one mutable JSON document as the only history.
6. Record failure category and diagnostics separately from user-facing feedback.

Likely schema direction:

```text
analysis_runs(id, video_id, model_version, status, attempt, input_hash,
              started_at, completed_at, failure_code, diagnostics_json)
analysis_results(id, analysis_run_id, result_json, created_at)
```

Exit criteria: analysis can be rerun with a new model version, old results remain inspectable, and existing review responses remain compatible.

## Phase 3 — Durable jobs and recovery

1. Replace FastAPI `BackgroundTasks` as the source of truth with persisted analysis jobs.
2. Add job fields for idempotency key, status, attempt count, lease expiry, next retry time, and last error.
3. Claim work atomically so only one worker owns a job lease.
4. Retry transient failures with bounded exponential backoff.
5. Mark permanent failures explicitly and retain the reason.
6. Make analysis completion idempotent so a worker retry cannot duplicate results or corrupt video state.
7. Add a recovery command/job for expired leases and stuck processing videos.

Start with a Postgres-backed worker or managed queue; defer a separate queue service until load requires it.

Exit criteria: killing a worker during processing leaves a recoverable job; retries do not duplicate analysis results.

## Phase 4 — Server-side idempotency for mutating buttons

Add a migration for an idempotency record keyed by `(user_id, idempotency_key)` with request hash, response status/body, timestamps, and expiry.

1. Add an `Idempotency-Key` request header to the backend mutation adapter.
2. Add a reusable backend idempotency module that:
   - claims a new key atomically;
   - returns the stored response for the same key and request hash;
   - returns `409` when the key is reused with a different payload;
   - supports expiry and cleanup.
3. Apply it to start analysis, save, discard/delete, analyzed export, and upload creation.
4. Keep domain-level safeguards too: unique constraints, conditional updates, deterministic export paths, and status checks.
5. Add frontend in-flight guards so double taps get immediate UX feedback, but never rely on them for correctness.

Tests required:

- concurrent duplicate requests;
- retry after a timeout where the first request succeeded;
- same key with changed payload;
- expired key reuse;
- duplicate export and duplicate analysis start.

## Phase 5 — Frontend module and request policy cleanup

Organize by feature rather than file type:

```text
src/features/auth/
src/features/video-intake/
src/features/analysis-review/
src/features/saved-videos/
src/features/tracking/
src/platform/backend-api/
src/platform/cache/
src/platform/navigation/
```

1. Move upload session state from the broad hook into the video-intake feature.
2. Move saved-video loading, opening, deletion, and review state out of `App.tsx`.
3. Keep `App.tsx` as composition and navigation wiring.
4. Keep backend API types close to their feature, with only shared transport policy in the platform module.
5. Add TypeScript project references or package-level test targets only after import direction is enforced.

Do not split into npm packages immediately. First prove the seams inside the existing repository.

## Phase 6 — Caching and invalidation

Implement a small platform cache with explicit TTL and invalidation rather than a global opaque cache.

Cache candidates:

- saved video list: 30–60 seconds;
- video capabilities: 5–15 minutes;
- signed playback URLs: current short TTL behavior;
- analysis result: keyed by video ID plus analysis ID/model version;
- status polling: in-flight request deduplication, not broad long-lived caching.

Mutation invalidation:

- start analysis → invalidate status and result;
- save/discard/delete → invalidate saved-video list;
- new analysis result → invalidate result and status;
- storage pruning → invalidate playback URL.

Cache requirements:

- scope entries by authenticated user and resource ID;
- never cache auth errors or mutation failures;
- honor server expiry for signed URLs;
- deduplicate identical in-flight GET requests;
- expose manual invalidation for logout and account switching.

## Phase 7 — Failure contracts and observability

1. Separate liveness (`/health`) from readiness, including database/storage dependency checks.
2. Add request and job correlation IDs.
3. Normalize backend error responses into stable error codes and retryability.
4. Add timeout budgets for API, storage, and analysis operations.
5. Classify retries as transient, auth/session, quota, invalid input, or permanent model failure.
6. Emit structured logs and metrics for queue age, processing duration, retry count, failure code, storage cleanup, quota, and model version.
7. Add dashboards/alerts only after the event names and dimensions are stable.

## Phase 8 — Build and test scope

1. Add backend package-level test commands for lifecycle, analysis, storage, and platform modules.
2. Add frontend feature-level tests for upload, review, saved videos, cache, and mutation policy.
3. Add import/dependency checks to prevent feature modules from importing each other's internals.
4. Use TypeScript project references or workspace packages only where they reduce measured compile/test time.
5. Keep a full integration/security gate for releases.

Important constraint: Expo/Metro will still bundle the application entry for device builds. Domain modularization reduces change fan-out and test scope; it does not guarantee that every native build compiles only one feature.

## Recommended implementation order

1. Phase 0 baseline.
2. Phase 1 backend lifecycle seam.
3. Phase 2 analysis contract/versioning.
4. Phase 4 server-side idempotency, because button correctness is a direct product risk.
5. Phase 6 frontend cache and invalidation.
6. Phase 3 durable jobs and recovery.
7. Phase 7 failure contracts and observability.
8. Phase 5 frontend feature modularization.
9. Phase 8 measured build/test optimization.

Each phase should be a separately reviewable commit with existing behavior preserved unless the phase explicitly changes the contract.
