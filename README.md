# Peso

Peso is a mobile-first lifting analysis app that turns a workout video into visual feedback, rep summaries, and technique cues.

The current version focuses on side-view squat analysis. A user uploads or records a squat video, Peso processes the movement, tracks the lifter and barbell, and returns an analyzed playback view with movement overlays and coaching feedback.

## Demo

<p align="center">
  <img src="assets/demo/peso-pin-assisted-tracking.gif" alt="Peso pin-assisted tracking demo" width="280">
  &nbsp;
  <img src="assets/demo/peso-pose-overlay.gif" alt="Peso pose overlay demo" width="280">
</p>

<p align="center">
  <em>Animated previews of Peso’s squat tracking and analysis playback.</em>
</p>

## What it does

Peso helps lifters review their form from a regular phone video.

At a high level, the app:

* lets a user upload or record a lifting video
* sends the video to a backend analysis pipeline
* tracks the lifter’s movement and bar path across the video
* identifies squat reps and movement phases
* generates visual overlays for playback
* returns technique feedback and rep-level summaries
* saves analyzed videos so the user can review progress later

The goal is to make lifting analysis easier to understand without requiring expensive motion-capture equipment or a coach standing next to the lifter every session.

## Current focus

Peso currently works best with side-view squat videos.

The main analysis pipeline is focused on:

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

For videos that do not match the current supported setup, Peso should return a clear, limited-analysis result instead of failing silently or pretending the analysis is more complete than it is.

Apply `supabase/migrations/202606120001_tracking_setup.sql` to enable optional pin-assisted tracking metadata. Side-view squat uploads may store a user-selected reference frame with upper back, hip, knee, ankle, and near-side collar anchors. The upper-back anchor is stored under the existing `shoulder` key for compatibility. Invalid or unavailable anchor tracks fall back to the automatic pose and barbell pipeline.

`BACKEND_CORS_ORIGINS` supports common Expo web, simulator, and local browser ports used by the mobile client. In `BACKEND_ENV=development`, the API also allows local browser origins matching `localhost`, `127.0.0.1`, `0.0.0.0`, or private LAN IPs on any port so Expo web and Expo Go can still work if they choose a different local port. Set `BACKEND_ENV=production` in deployed environments to disable that local-dev regex and rely only on explicit `BACKEND_CORS_ORIGINS`.
`BACKEND_CORS_ALLOW_PRIVATE_NETWORK=true` supports Chrome's local private-network preflight during development. It is ignored when `BACKEND_ENV=production`.

I am actively improving the tracking and playback experience.

Current priorities:

* making pin-assisted tracking more reliable
* keeping the upper-back marker stable across frames
* smoothing the barbell path overlay
* improving pose landmark consistency during squats
* refining the coaching feedback shown after analysis


## Tech stack

### Mobile app

* React Native
* Expo
* TypeScript
* NativeWind / Tailwind styling
* Supabase client
* Expo video and media tools

### Backend

* Python
* FastAPI
* OpenCV
* MediaPipe
* RTMPose fallback support
* FFmpeg
* Supabase Auth, Database, and Storage

## How the app works

1. The user records or uploads a lifting video.
2. The app stores the video through Supabase.
3. The backend receives an analysis request.
4. The backend downloads the video and processes it frame by frame.
5. Pose and barbell tracking are used to estimate movement quality.
6. Rep summaries, diagnostics, overlays, and coaching feedback are saved.
7. The mobile app displays the analyzed result to the user.

## Local development

### Requirements

* Node.js
* npm
* Python 3.11 or newer
* FFmpeg with H.264 support
* Supabase project
* Expo development environment

### Environment variables

Create a `.env` file from `.env.example` and fill in the required Supabase values.

Frontend variables include:

```bash
EXPO_PUBLIC_SUPABASE_URL=
EXPO_PUBLIC_SUPABASE_ANON_KEY=
EXPO_PUBLIC_BACKEND_TARGET=auto
EXPO_PUBLIC_BACKEND_PORT=8000
EXPO_PUBLIC_MAX_VIDEO_UPLOAD_BYTES=52428800
```

Backend variables include:

```bash
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
```

### Install frontend dependencies

```bash
npm install
```

### Install backend dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start the app locally

From the project root:

```bash
npm start
```

To run the frontend and backend separately:

```bash
npm run start:frontend
npm run start:backend
```

For Expo Go on a physical phone, the backend must bind to `0.0.0.0` so another device on the same network can reach it.

### Static web hosting

Expo web can be exported as static assets:

```bash
EXPO_PUBLIC_BACKEND_URL=https://api.example.com npm run web:export
```

The static build writes to `dist/`. `netlify.toml` publishes that folder, falls routes back to `index.html`, and marks immutable assets cacheable. Production web builds must set `EXPO_PUBLIC_BACKEND_URL` or `EXPO_PUBLIC_PRODUCTION_BACKEND_URL` to the deployed FastAPI backend.

## Backend API overview

Protected routes require a Supabase bearer token.

```http
Authorization: Bearer <supabase_access_token>
```

Main endpoints:

* `POST /analyze/{video_id}` — queues analysis for an uploaded video
* `GET /videos/{video_id}/status` — checks video processing status
* `GET /analysis/{video_id}` — returns the latest analysis result
* `POST /videos/{video_id}/save` — saves a video for later review
* `POST /videos/{video_id}/discard` — discards a video
* `GET /videos/saved` — lists saved videos
* `GET /videos/{video_id}/playback-url` — returns a signed playback URL
* `POST /videos/cleanup-expired` — cleans up expired or unused storage objects.

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

### `GET /videos/capabilities`

Returns authenticated video-upload capabilities. Pin-assisted uploads call this before compression or storage upload and require `pin_assisted_tracking: true` with tracking setup version `1`. Missing schema support blocks the upload without creating a row or storage object.

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

## Project status

Peso is under active development.

The current version demonstrates the core product idea: upload a lifting video, analyze the movement, and return useful visual feedback. The next major step is improving tracking reliability so the app can handle more real-world gym videos with clutter, occlusion, and imperfect camera angles.

## Repository structure

```text
.
├── assets/                 # App assets and README demo media
├── backend/                # FastAPI video-analysis backend
├── lib/                    # Shared frontend utilities
├── scripts/                # Development scripts
├── src/                    # Mobile app source code
├── supabase/migrations/    # Database migrations
├── App.tsx                 # App entry point
├── package.json            # Frontend scripts and dependencies
└── README.md
```

## Notes

Peso is a coaching and analysis tool, not a medical or professional training replacement. The app is meant to help lifters review movement patterns and better understand their own training videos.
