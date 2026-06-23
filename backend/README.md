# Peso Backend

FastAPI backend for Peso, a mobile-first lifting analysis app.

The backend receives uploaded workout videos, runs the analysis pipeline, creates playback assets, and stores structured results for the mobile app to display.

## What this backend does

The backend handles the server-side video analysis flow for Peso.

At a high level, it:

* authenticates requests with Supabase JWT bearer tokens
* validates that users own the videos they are analyzing
* downloads uploaded videos from Supabase Storage
* runs pose estimation and barbell tracking
* segments squat repetitions
* computes squat-specific movement metrics
* creates analyzed playback assets
* creates saved-video thumbnails
* stores analysis results back in Supabase
* supports saving, discarding, and cleaning up uploaded videos

## Current analysis scope

The current implementation is focused on squat analysis.

Side-view squat videos receive the richest analysis. Other exercise or camera-view combinations may still return a limited result so the app can explain the constraint clearly instead of failing silently.

Current squat analysis includes:

* rep segmentation
* depth scoring
* torso angle tracking
* velocity statistics during each rep
* pose coverage diagnostics
* body visibility checks
* camera-angle quality checks
* coaching feedback
* analyzed playback generation

If pose detection fails completely, the result includes diagnostics explaining that no pose was detected.

## Requirements

* Python 3.11 or newer
* FFmpeg with `libx264` available on `PATH`
* Supabase project
* Supabase Storage bucket for uploaded videos
* `videos` table for video metadata
* `analysis_results` table for analysis output

FFmpeg is required for analyzed video exports and compressed saved-video playback assets.

## Environment variables

Required variables:

```bash
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
```

Optional variables:

```bash
BACKEND_ENV=development
VIDEO_BUCKET=videos
CLEANUP_JOB_TOKEN=
EXPORT_CACHE_TTL_HOURS=24
ORPHAN_STORAGE_MIN_AGE_HOURS=24
STALE_PROCESSING_HOURS=6
MODEL_VERSION=mediapipe-rtmpose-v2-hip-crease-depth
POSE_TARGET_FPS=18
POSE_MAX_FRAME_DIMENSION=720
POSE_MODEL_COMPLEXITY=2
POSE_MIN_DETECTION_CONFIDENCE=0.6
POSE_MIN_TRACKING_CONFIDENCE=0.6
POSE_BACKEND=hybrid
POSE_FALLBACK_ENABLED=true
POSE_FALLBACK_DEVICE=auto
POSE_FALLBACK_DET_FREQUENCY=3
POSE_FALLBACK_MODE=balanced
POSE_DEBUG_LANDMARK_EXPORT_DIR=
FFMPEG_BINARY=
BACKEND_CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081,http://localhost:8082,http://127.0.0.1:8082,http://localhost:19006,http://127.0.0.1:19006,http://localhost:3000,http://127.0.0.1:3000
BACKEND_CORS_ALLOW_PRIVATE_NETWORK=true
```

## Pose analysis settings

Pose analysis samples squat videos at `POSE_TARGET_FPS` and resizes frames so the longest side is at most `POSE_MAX_FRAME_DIMENSION` before inference.

`POSE_BACKEND=hybrid` runs MediaPipe first and can retry hard clips with RTMPose when:

```bash
POSE_FALLBACK_ENABLED=true
```

and the required `rtmlib` / `onnxruntime` dependencies are installed.

`POSE_FALLBACK_MODE` accepts:

```text
performance
lightweight
balanced
```

The original and processed video dimensions are preserved in saved analysis metadata.

## CORS behavior

`BACKEND_CORS_ORIGINS` supports common Expo web, simulator, and local browser ports used by the mobile client.

In development mode, the API also allows local browser origins matching:

```text
localhost
127.0.0.1
0.0.0.0
private LAN IPs
```

on any port. This helps Expo web and Expo Go work when they choose different local ports.

Set this in production:

```bash
BACKEND_ENV=production
```

Production mode disables the local-development regex and relies only on explicit `BACKEND_CORS_ORIGINS`.

`BACKEND_CORS_ALLOW_PRIVATE_NETWORK=true` supports Chrome local private-network preflight behavior during development. It is ignored when `BACKEND_ENV=production`.

## Installation

From the project root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install FFmpeg for local development:

```bash
brew install ffmpeg
ffmpeg -version
```

For production, install an OS FFmpeg package in the runtime image or set `FFMPEG_BINARY` to the deployed binary path.

The FFmpeg binary must support H.264 encoding through `libx264`.

## Running the API

Start the server from the `backend` directory so `app.main:app` resolves correctly:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use `--host 0.0.0.0` for Expo Go on a physical phone. Binding FastAPI to `localhost` only makes it unreachable from another device on the same network.

If environment variables are stored in a file, you can also run:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

For Expo web on the same Mac as the backend:

```bash
EXPO_PUBLIC_BACKEND_URL=http://localhost:8000
npx expo start -c
```

For Expo Go on a physical phone, keep FastAPI bound to `0.0.0.0:8000`.

If `EXPO_PUBLIC_BACKEND_URL` is accidentally set to `http://localhost:8000`, the frontend ignores that loopback value on-device and auto-detects the Expo dev server LAN IP for backend requests.

## Starting from the project root

From the project root, this command starts both the local FastAPI backend and Expo:

```bash
npm start
```

If a backend is already responding on:

```text
http://127.0.0.1:8000/health
```

the script reuses it instead of starting another copy.

To run the two processes separately:

```bash
npm run start:backend
npm run start:frontend
```

## Health check

```http
GET /health
```

Example response:

```json
{
  "status": "ok"
}
```

## Authentication

Protected endpoints require a Supabase access token:

```http
Authorization: Bearer <supabase_access_token>
```

## API endpoints

### `POST /analyze/{video_id}`

Queues a background analysis job for a video owned by the current user.

The backend validates ownership with Supabase before queueing the job. The request returns immediately with `queued` while the analysis runs asynchronously.

Example response:

```json
{
  "video_id": "uuid",
  "status": "queued"
}
```

### `POST /videos/{video_id}/save`

Marks the video as saved by updating metadata only.

This does not copy or duplicate the storage object.

### `POST /videos/{video_id}/discard`

Deletes explicit storage objects for the video and marks the row discarded.

### `GET /videos/saved`

Returns saved video metadata, a small analysis summary for card text, and signed thumbnail URLs.

This does not return signed full-video URLs or full pose / analysis payloads.

### `GET /videos/{video_id}/playback-url`

Returns a short-lived signed full-video URL for review playback.

The backend signs `playback_path` when available and falls back to `storage_path` only when a compressed playback file has not been created yet.

The mobile client requests this only after the user opens the playback screen.

### `POST /videos/cleanup-expired`

Dry-runs cleanup by default and reports reclaimable storage without deleting anything.

Pass `confirm=true` to delete unnecessary Supabase Storage data and mark eligible rows discarded.

Cleanup removes:

* expired pending uploads
* stale pending analysis jobs
* old analyzed export MP4s
* unreferenced app-owned upload objects

Saved source videos are never deleted.

Outside local development, requests must include:

```http
X-Cleanup-Token: <CLEANUP_JOB_TOKEN>
```

Use `dry_run=true` to inspect reclaimable storage without deleting anything:

```http
POST /videos/cleanup-expired?dry_run=true
```

### `GET /videos/{video_id}/status`

Returns the current status and basic metadata for a video.

### `GET /analysis/{video_id}`

Returns the latest stored analysis result for the video.

If analysis has not completed yet, the API returns `404`.

The result payload is stored as JSON and includes:

* rep summaries
* quality diagnostics
* video dimensions
* coaching feedback
* limited-analysis reasons when full analysis is unavailable

## Saved thumbnail backfill

Existing saved videos that predate `thumbnail_path` can be backfilled without copying videos or deleting originals.

Dry run:

```bash
backend/.venv/bin/python scripts/backfill_saved_video_thumbnails.py
```

Confirmed run:

```bash
backend/.venv/bin/python scripts/backfill_saved_video_thumbnails.py --confirm
```

Force regeneration:

```bash
backend/.venv/bin/python scripts/backfill_saved_video_thumbnails.py --force --confirm
```

The script loads `backend/.env` automatically and is dry-run by default.

With `--confirm`, it:

1. downloads only saved videos missing the current thumbnail version
2. writes one JPEG thumbnail to `thumbnails/`
3. updates the row
4. logs each source and thumbnail path

Add `--force` to regenerate saved thumbnails that already have the current thumbnail path.

Apply this migration before running confirmed backfill or production optimization:

```text
supabase/migrations/202605240001_storage_egress_cleanup.sql
```

It adds:

* `thumbnail_path`
* `playback_path`
* `original_storage_path`
* saved metadata
* discard metadata
* cleanup indexes

## Development notes

* CORS defaults to common Expo and local web development origins.
* The backend uses Supabase service-role credentials server-side only.
* Temporary video files are downloaded to the local filesystem during analysis.
* Temporary files are removed after processing.
* After analysis results are saved, the backend creates one JPEG thumbnail and a 720p H.264 playback copy with long cache-control.
* The original upload is deleted only after the thumbnail path and playback path are written successfully.
* If thumbnail or playback generation fails, analysis still completes and the original storage path remains available for playback.
* The analysis pipeline is built around `PoseEstimator` and `SquatAnalyzer`.
* Results are written back through `VideoRepository`.
* `model_version` is stored with each analysis result so future analysis passes can coexist with older ones.

## Storage cleanup

Run storage cleanup from the backend environment.

Dry run:

```bash
python -m app.jobs.storage_cleanup --dry-run
```

Confirmed cleanup:

```bash
python -m app.jobs.storage_cleanup
```

Schedule the real cleanup command daily in production after the dry-run report looks correct.

## Typical local flow

1. Start Supabase and make sure the `videos` table and storage bucket exist.
2. Set the required environment variables.
3. Start this backend on port `8000`.
4. Point the frontend at the backend URL for your platform.
5. Upload a video from the app.
6. Trigger analysis.
7. Review the stored analysis result and playback asset.

## Project notes

The larger Peso product vision includes a more complete technique coach, bar-path visualization, and support for additional exercises.

This backend currently supports the core video analysis and storage pipeline that the mobile app depends on.
