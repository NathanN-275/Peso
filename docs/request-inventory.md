# Request Provenance Inventory

This document tracks client-to-backend and client-to-Supabase request sources that should be reviewed during security or performance changes.

## Backend API Requests

All FastAPI calls flow through `lib/backendApi.ts`, which adds bearer auth when an access token is provided and uses `lib/backendConfig.ts` for the base URL.

- `GET /health`: unauthenticated backend reachability check.
- `GET /videos/storage-usage`: authenticated quota check before upload.
- `GET /videos/capabilities`: authenticated pin-tracking capability check.
- `POST /videos`: authenticated upload registration. Client payload is built by `buildRegisterUploadedVideoPayload`; backend owns lifecycle/status/storage metadata.
- `POST /analyze/{video_id}`: authenticated analysis queueing. Backend revalidates video ownership and storage path ownership.
- `GET /videos/{video_id}/status`: authenticated polling for owned video status.
- `GET /analysis/{video_id}`: authenticated owned analysis result fetch.
- `POST /videos/{video_id}/save`: authenticated saved-library transition. Accepts optional `performed_reps` (integer, at least 1) and optional load details (`load_value`, a number at least 0, paired with `load_unit`, `lb` or `kg`). The backend stores any supplied workout facts in the same update as the saved state.
- `GET /videos/saved`: authenticated legacy saved list. Kept for compatibility; analysis is batch-loaded.
- `GET /videos/saved-page`: authenticated paginated saved-library list. Frontend folder screens use this endpoint.
- `GET /videos/saved-overview`: authenticated lightweight Home/Profile overview. Only preview thumbnails are signed.
- `GET /videos/{video_id}/playback-url`: authenticated, short-lived signed playback URL. Backend validates ownership immediately before signing.
- `POST /videos/{video_id}/analyzed-export`: authenticated export render/sign. Client payload is built by `buildAnalyzedVideoExportPayload`.
- `POST /saved-lift-exports`: authenticated, owner-checked background creation of one deduplicated Saved Lift ZIP.
- `GET /saved-lift-exports/{job_id}`: authenticated owner-scoped job polling; a short-lived signed archive URL is returned only while a completed job remains unexpired.
- `POST /saved-lifts/delete`: authenticated permanent deletion of a prevalidated set of owned Saved Lifts and their video/analysis data.
- `POST /videos/{video_id}/discard`: authenticated cleanup/delete for owned saved or pending videos.
- `POST /videos/{video_id}/upload-failed`: authenticated upload failure cleanup for owned rows.
- `DELETE /account`: authenticated account/profile/video cleanup.
- `POST /videos/cleanup-expired`: cleanup job route protected by `CLEANUP_JOB_TOKEN` unless explicit development-only cleanup is enabled.

## Supabase Client Requests

- Auth session management is centralized in `context/AuthContext.tsx`.
- Direct profile reads/writes are in `lib/profile.ts`; these depend on profile RLS and must only send profile-owned fields.
- Profile avatar upload is in `lib/profile.ts`; client validates MIME/size for UX, while storage policies must enforce bucket/folder ownership.
- Video upload to Supabase Storage is in `lib/videoUpload.ts`; client uploads only under the authenticated user folder, then registers through `POST /videos`.

## Production HTTP Policy

- Local development may use plaintext `http://localhost`, emulator, simulator, and LAN URLs.
- Production frontend backend URLs must be HTTPS and must not point at localhost, loopback, link-local, `.local`, or private IPv4 ranges.
- Production backend CORS must be explicitly configured and must not allow wildcard, localhost, private-network origins, private-network CORS, or debug landmark export settings.

## Swallowed Field Boundary

- Backend request models use fail-closed schemas for unknown fields.
- Frontend request payload builders intentionally send only minimum client-owned fields.
- Server-owned fields include lifecycle, retention, status, size, storage state, playback, thumbnail, export, error, and analysis metadata.
