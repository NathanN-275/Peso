# Peso Technical Design Document

**Status:** Current beta architecture | **Updated:** 2026-08-25

## Architecture overview

Peso has four cooperating surfaces:

1. **Marketing Site:** static public site hosted on Netlify.
2. **Web App:** authenticated React Native Web / Expo experience under `/app`.
3. **Mobile App:** Expo and React Native client for capture, upload, and review.
4. **Backend:** FastAPI API and durable worker using Supabase, OpenCV, MediaPipe, optional RTMPose, and FFmpeg.

Both clients use the same Peso Account, Saved Lift Library, and Analysis Job model.

## Request and data flow

1. The client authenticates with Supabase and uploads source media to owner-scoped Storage.
2. The client requests analysis; the API validates ownership and creates a durable Analysis Job.
3. The worker leases queued work, downloads the source through signed access, and processes sampled frames.
4. Pose estimation and visible-collar tracking produce observations, gaps, diagnostics, rep segmentation, and metrics.
5. FFmpeg creates review/playback assets; structured results are stored in Supabase.
6. The client polls Analysis Activity only while foregrounded work is active and loads the Review Projection for review.
7. Save writes user-owned workout facts separately from model observations.

## Main data concepts

- **Analysis Job:** durable server-owned lifecycle for one submitted video.
- **Analysis Run:** completed processing pass and its observations.
- **Review Projection:** bounded payload for interactive review.
- **Playback Session:** independently refreshed signed media access.
- **Saved Lift:** explicit user decision to keep an analyzed result.
- **Performed Reps / Load:** user-owned workout facts; never silently replaced by detected values.

## Analysis strategy

The side-view path is the highest-confidence path. It combines pose landmarks, visible-collar tracking, identity-preserving repair/recovery, rep segmentation, depth and torso measurements, velocity estimates, quality diagnostics, and explainable coaching rules. A Recording Quality Advisory warns about risky footage; it does not convert weak evidence into a confident result.

Frontal squat analysis is a separate capability with different evidence and limits. It must not inherit side-view depth or torso assumptions.

## API boundaries

The backend currently exposes endpoints for analysis submission, activity/status, analysis results, save/discard, saved lifts, playback URLs, export jobs, deletion, and cleanup. Endpoint details and request contracts live in [`backend/README.md`](../../backend/README.md).

## Security and reliability

- Supabase JWT bearer authentication and owner-scoped authorization protect API operations.
- Storage access uses signed URLs with short lifetimes.
- Database-backed jobs use leases, heartbeats, recovery, and timeout handling.
- Upload quotas, duration limits, CORS rules, cleanup jobs, and dependency audits are part of deployment configuration.
- Analysis outputs retain diagnostics so a limited result can be explained instead of silently overstating confidence.

## Testing strategy

- Frontend TypeScript checks and policy tests run from the root package scripts.
- Dashboard tests cover view logic, annotations, and configuration behavior.
- Backend unit tests cover API, analysis, migrations, security boundaries, and worker behavior.
- Pose and barbell evaluation fixtures provide reviewed evidence for tracking changes.
- CI runs backend tests, frontend checks, dependency audits, migration/RLS audits, and secret scanning.

## Key trade-offs

- Durable database jobs are preferred over client-owned progress because analysis can outlive a browser or phone session.
- Rules plus history are preferred before personalized ML because current coaching must be inspectable and feedback data is still being gathered.
- User facts and model observations remain separate so a correction does not rewrite what the model actually saw.
- Static marketing and authenticated product surfaces remain separate to keep public delivery small and product state protected.

## Related decisions

See `docs/adr/0006-durable-web-analysis-queue-and-worker.md`, `0009-durable-analysis-jobs-across-clients.md`, `0008-treat-recording-quality-as-advisory.md`, `0004-separate-workout-facts-from-model-observations.md`, and `0005-separate-static-marketing-and-web-app.md`.
