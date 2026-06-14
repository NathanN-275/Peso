# Peso Video Analysis Backend

FastAPI backend for Peso, a mobile-first lifting analysis app. The project analyzes uploaded workout videos, estimates pose, segments repetitions, computes technique metrics, and stores the results for the mobile client to display.

## What it does

- Authenticates requests with Supabase JWT bearer tokens
- Reads and updates video records in Supabase
- Downloads uploaded videos from Supabase Storage
- Runs pose estimation with MediaPipe and OpenCV
- Detects repetitions and computes squat-specific technique metrics
- Stores analysis results back in Supabase as structured JSON
- Supports saving or discarding uploaded videos

## Product Scope

The original project proposal describes Peso as a computer-vision coaching tool for lifters. The intended user flow is:

1. Record or upload a lifting video from the mobile app.
2. Send the video to this backend for processing.
3. Extract frames and run pose estimation.
4. Segment repetitions and compute movement metrics.
5. Return feedback, flags, and rep summaries to the client.

The current backend implementation is focused on squat analysis. Side-view squat videos receive the richest analysis. Other exercise or camera-view combinations still produce a limited result so the app can explain the constraint clearly instead of failing silently.

## Requirements

- Python 3.11 or newer
- FFmpeg with `libx264` available on `PATH`, or `FFMPEG_BINARY` pointing to the binary. The backend requires FFmpeg for analyzed exports and for the compressed saved-video playback asset.
- Supabase project with:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `SUPABASE_JWT_SECRET`
- A storage bucket for uploaded videos, defaulting to `videos`
- Video metadata stored in a `videos` table
- Analysis output stored in an `analysis_results` table

## Environment Variables

The backend requires these variables:

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
MODEL_VERSION=mediapipe-rtmpose-v3-pin-assisted
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

Pose analysis samples squat videos at `POSE_TARGET_FPS` and resizes frames so the longest side is at most `POSE_MAX_FRAME_DIMENSION` before pose inference. `POSE_BACKEND=hybrid` runs MediaPipe first and retries hard clips with RTMPose when `POSE_FALLBACK_ENABLED=true` and the `rtmlib`/`onnxruntime` dependencies are installed. `POSE_FALLBACK_MODE` accepts `performance`, `lightweight`, or `balanced`. The original and processed video dimensions are preserved in saved analysis metadata.

Apply `supabase/migrations/202606120001_tracking_setup.sql` to enable optional pin-assisted tracking metadata. Side-view squat uploads may store a user-selected reference frame with shoulder, hip, knee, ankle, and near-side collar anchors. Invalid or unavailable anchor tracks fall back to the automatic pose and barbell pipeline.

`BACKEND_CORS_ORIGINS` supports common Expo web, simulator, and local browser ports used by the mobile client. In `BACKEND_ENV=development`, the API also allows local browser origins matching `localhost`, `127.0.0.1`, `0.0.0.0`, or private LAN IPs on any port so Expo web and Expo Go can still work if they choose a different local port. Set `BACKEND_ENV=production` in deployed environments to disable that local-dev regex and rely only on explicit `BACKEND_CORS_ORIGINS`.
`BACKEND_CORS_ALLOW_PRIVATE_NETWORK=true` supports Chrome's local private-network preflight during development. It is ignored when `BACKEND_ENV=production`.

## Installation

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

For production, install an OS FFmpeg package in the runtime image or set `FFMPEG_BINARY` to the deployed binary path. The binary must support H.264 encoding through `libx264`.

## Running the API

Start the server from the `backend` directory so `app.main:app` resolves correctly:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use `--host 0.0.0.0` for Expo Go on a physical phone. Binding FastAPI to `localhost` only makes it unreachable from another device on the same network.

If you keep environment variables in a file, you can also use:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

For Expo web on the same Mac as the backend:

```bash
EXPO_PUBLIC_BACKEND_URL=http://localhost:8000
npx expo start -c
```

For Expo Go on a physical phone, keep FastAPI bound to `0.0.0.0:8000`. If `EXPO_PUBLIC_BACKEND_URL` is accidentally set to `http://localhost:8000`, the frontend ignores that loopback value on-device and auto-detects the Expo dev server LAN IP for backend requests.

From the project root, `npm start` starts both the local FastAPI backend and Expo. If a backend is already responding on `http://127.0.0.1:8000/health`, the script reuses it instead of starting another copy.

```bash
npm start
```

To run the two processes separately:

```bash
npm run start:backend
npm run start:frontend
```

## Health Check

```bash
GET /health
```

Response:

```json
{"status":"ok"}
```

## API Endpoints

All protected endpoints require:

```http
Authorization: Bearer <supabase_access_token>
```

### `POST /analyze/{video_id}`

Queues a background analysis job for a video owned by the current user.

The backend validates ownership with Supabase before queueing the job. The request returns immediately with `queued`, while the analysis runs asynchronously.

Response:

```json
{
  "video_id": "uuid",
  "status": "queued"
}
```

### `POST /videos/{video_id}/save`

Marks the video as saved by updating metadata only. It does not copy or duplicate the storage object.

### `POST /videos/{video_id}/discard`

Deletes explicit storage objects for the video and marks the row discarded.

### `GET /videos/saved`

Returns saved video metadata, a small analysis summary for card text, and signed thumbnail URLs. It does not return signed full-video URLs or full pose/analysis payloads.

### `GET /videos/{video_id}/playback-url`

Returns a short-lived signed full-video URL for review playback. The backend signs `playback_path` when available and falls back to `storage_path` only when a compressed playback file has not been created yet. The mobile client requests this only after the user opens the playback screen.

### `GET /videos/storage-usage`

Returns the current object-storage inventory and a conservative peak estimate for a proposed upload. Pass `upload_size_bytes` as a query parameter. The estimate includes the source upload, a temporary compressed-playback allowance, and a thumbnail allowance. Uploads warn at 80% projected usage and block at 95%; quota handling never deletes saved videos.

The defaults match the current Supabase plan and can be overridden in the backend environment:

```dotenv
OBJECT_STORAGE_LIMIT_BYTES=1073741824
DATABASE_LIMIT_BYTES=536870912
MONTHLY_EGRESS_LIMIT_BYTES=5368709120
STORAGE_WARNING_RATIO=0.80
STORAGE_BLOCK_RATIO=0.95
PLAYBACK_STORAGE_ESTIMATE_RATIO=1.0
THUMBNAIL_STORAGE_ALLOWANCE_BYTES=1048576
```

### `POST /videos/cleanup-expired`

Dry-runs cleanup by default and reports reclaimable storage without deleting anything. Pass `confirm=true` to delete unnecessary Supabase Storage data and mark eligible rows discarded. Cleanup removes expired pending uploads, stale pending analysis jobs, old analyzed export MP4s, and unreferenced app-owned upload objects. Saved source videos are never deleted.

Outside local development, requests must include:

```http
X-Cleanup-Token: <CLEANUP_JOB_TOKEN>
```

Use `dry_run=true` to inspect reclaimable storage without deleting anything:

```http
POST /videos/cleanup-expired?dry_run=true
```

The local cleanup script also loads `backend/.env` automatically and is dry-run by default:

```bash
backend/.venv/bin/python scripts/cleanup_supabase_storage.py --dry-run
```

### Saved thumbnail backfill

Existing saved videos that predate `thumbnail_path` can be backfilled without copying videos or deleting originals:

```bash
backend/.venv/bin/python scripts/backfill_saved_video_thumbnails.py
backend/.venv/bin/python scripts/backfill_saved_video_thumbnails.py --confirm
backend/.venv/bin/python scripts/backfill_saved_video_thumbnails.py --force --confirm
```

The script loads `backend/.env` automatically and is dry-run by default. With `--confirm`, it downloads only saved videos missing the current thumbnail version, writes one JPEG thumbnail to `thumbnails/`, updates the row, and logs each source and thumbnail path. Add `--force` to regenerate saved thumbnails that already have the current thumbnail path.

Apply `supabase/migrations/202605240001_storage_egress_cleanup.sql` before running confirmed backfill or production optimization. It adds `thumbnail_path`, `playback_path`, `original_storage_path`, saved/discard metadata, and cleanup indexes.

### `GET /videos/{video_id}/status`

Returns the current status and basic metadata for a video.

### `GET /analysis/{video_id}`

Returns the latest stored analysis result for the video. If analysis has not completed yet, the API returns `404`.

The result payload is stored as JSON and includes rep summaries, quality diagnostics, video dimensions, and coaching feedback. For limited-analysis cases, it also includes a reason describing why full analysis was not available.

## Analysis Behavior

The project proposal calls out bar-path tracking, rep counting, coaching cues, and technique flags. The current implementation covers the squat portion of that scope through pose estimation and rule-based metrics.

Current squat analysis includes:

- Rep segmentation
- Depth scoring
- Torso angle tracking
- Velocity stats during each rep
- Quality checks for pose coverage, body visibility, and camera angle

The current analysis pipeline is optimized for squat videos from a side view. For other exercise or camera-view combinations, the backend stores a limited result that records the constraint instead of trying to fake a full report.

If pose detection fails completely, the result includes diagnostics explaining that no pose was detected.

## Development Notes

- CORS defaults to common Expo and local web development origins.
- The backend uses Supabase service-role credentials server-side only.
- Temporary video files are downloaded to the local filesystem during analysis and removed after processing.
- After analysis results are saved, the backend creates one JPEG thumbnail and a 720p H.264 playback copy with long cache-control. The original upload is deleted only after the thumbnail path and playback path are written successfully.
- If thumbnail or playback generation fails, analysis still completes and the original storage path remains available for playback.
- The analysis pipeline is built around `PoseEstimator` and `SquatAnalyzer`, with results written back through `VideoRepository`.
- `model_version` is stored with each analysis result so future analysis passes can coexist with older ones.
- Run storage cleanup from the backend environment with `python -m app.jobs.storage_cleanup --dry-run`, then `python -m app.jobs.storage_cleanup` when the report looks correct. Schedule the real cleanup command daily in production.

## Typical Local Flow

1. Start Supabase and make sure the `videos` table and storage bucket exist.
2. Set the required environment variables.
3. Start this backend on port `8000`.
4. Point the frontend at the backend URL for your platform.

## Project Notes

The project proposal also mentions a future technique coach bot and bar-path visualization. Those pieces are part of the product vision, but the backend in this repository currently supports the video analysis and storage pipeline that the mobile app depends on.
