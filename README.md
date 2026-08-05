# Peso

Peso is a web and mobile lifting analysis product that turns a workout video into visual feedback, rep summaries, and technique cues.

The current version focuses on side-view squat analysis. A front view is in development but still needs improvement to be more accurate. A user uploads or records a squat video, Peso processes the movement, tracks the lifter and barbell, and returns an analyzed playback view with movement overlays and coaching feedback.

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

Peso is moving from a working mobile-first prototype toward a product that lifters can use through the web. The immediate goal is to launch a focused web beta while continuing to strengthen the analysis behind every result.

### Launch the web beta

The web beta is the clearest path to getting Peso into users' hands and learning from real lifting videos. Current work is focused on turning the browser experience into a complete product flow: introducing Peso through the public Marketing Site, bringing users into the Web App, accepting side-view squat videos, showing analysis progress, and making results easy to review and save.

The first release is intentionally narrow. It is designed to make one supported workflow dependable before expanding to more exercises, camera angles, and coaching features.

### Improve tracking reliability

Peso currently works best with side-view squat videos. The analysis pipeline is being improved to preserve the identity of the lifter's joints and visible barbell collar across frames, especially when gym equipment, motion blur, or partial occlusion makes tracking difficult.

Current tracking priorities include:

* making pin-assisted tracking more reliable
* keeping the upper-back marker stable across frames
* smoothing the barbell path overlay without hiding uncertain observations
* improving pose landmark consistency throughout each squat
* returning a clear limited-analysis result when a video cannot be analyzed confidently

Front-view videos are also supported, but that analysis is still in development and needs further accuracy improvements.

### Continue developing the mobile app

Launching the web beta does not replace the mobile app. The Expo app remains in active development and will continue to evolve alongside the web product. The web beta provides a practical way to ship Peso and validate the core experience, while mobile development continues to improve recording, uploading, and reviewing lifts directly from a phone.

## Tech stack

### Marketing Site

* Astro
* Static HTML and CSS
* Netlify hosting

### Web App

* React
* React Native Web and Expo
* TypeScript
* React Router
* Supabase client
* Netlify hosting under `/app`

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
7. The Web App or mobile app displays the analyzed result to the user.

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
CLEANUP_JOB_TOKEN=replace-with-random-cleanup-secret
```

Additional backend analysis and local-development variables include:

```bash
BACKEND_ENV=development
VIDEO_BUCKET=videos
MAX_VIDEO_DURATION_MS=300000
SIGNED_URL_TTL_SECONDS=300
STORAGE_DOWNLOAD_SIGNED_URL_TTL_SECONDS=120
FFMPEG_TIMEOUT_SECONDS=120
MAX_GLOBAL_VIDEO_WORKERS=2
EXPORT_COOLDOWN_SECONDS=30
EXPORT_CACHE_TTL_HOURS=24
MAX_SAVED_LIFT_EXPORT_BYTES=52428800
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
POSE_REPAIR_ENABLED=true
POSE_REPAIR_MAX_GAP_FRAMES=3
POSE_REPAIR_VELOCITY_GAP_FRAMES=2
POSE_REPAIR_RECOVERY_HYSTERESIS_FRAMES=2
YOLO_TRACKING_MODE=off
YOLO_TRACKING_MODEL_PATH=
YOLO_TRACKING_CLASS_NAMES=barbell_collar,rack_upright,j_hook,safety_arm,storage_peg,sleeve,plate_face
YOLO_TRACKING_CONFIDENCE_THRESHOLD=0.45
YOLO_TRACKING_NMS_IOU_THRESHOLD=0.45
YOLO_TRACKING_INPUT_SIZE=640
YOLO_TRACKING_MAX_COAST_SECONDS=0.25
FFMPEG_BINARY=
BACKEND_CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081,http://localhost:8082,http://127.0.0.1:8082,http://localhost:19006,http://127.0.0.1:19006,http://localhost:3000,http://127.0.0.1:3000
BACKEND_CORS_ALLOW_PRIVATE_NETWORK=true
```

Apply `supabase/migrations/202606120001_tracking_setup.sql` to enable optional pin-assisted tracking metadata. Side-view squat uploads may store a user-selected reference frame with upper back, hip, knee, ankle, and near-side collar anchors. The upper-back anchor is stored under the existing `shoulder` key for compatibility. Invalid or unavailable anchor tracks fall back to the automatic pose and barbell pipeline.

`BACKEND_CORS_ORIGINS` supports common Expo web, simulator, and local browser ports used by the mobile client. In `BACKEND_ENV=development`, the API also allows local browser origins matching `localhost`, `127.0.0.1`, `0.0.0.0`, or private LAN IPs on any port so Expo web and Expo Go can still work if they choose a different local port. Set `BACKEND_ENV=production` in deployed environments to disable that local-dev regex and rely only on explicit `BACKEND_CORS_ORIGINS`.
`BACKEND_CORS_ALLOW_PRIVATE_NETWORK=true` supports Chrome's local private-network preflight during development. It is ignored when `BACKEND_ENV=production`.

Production backend deployments must also set `BACKEND_ENV=production`, `CLEANUP_JOB_TOKEN`, and an explicit non-local `BACKEND_CORS_ORIGINS` value.

### Supabase profile infrastructure

Profile editing depends on the `public.profiles` table and the private `profile-avatars` storage bucket. If Settings shows `Profile editing needs the user profile migration to be applied.` or avatar upload returns `Bucket not found`, apply the latest Supabase migrations to the hosted project before testing profile changes.

This repo does not include a linked Supabase CLI config by default. Link the project and push migrations:

```bash
npx supabase link --project-ref <project-ref>
npx supabase db push
```

If the project cannot be linked locally, run `supabase/migrations/202607120001_profile_infrastructure_repair.sql` in the Supabase Dashboard SQL editor. The repair migration creates or updates:

* `public.profiles` with owner-scoped RLS
* the private `profile-avatars` bucket
* avatar storage policies scoped to the authenticated user's folder
* avatar MIME limits for JPG, PNG, and WebP
* a 512 KB per-avatar storage limit

Avatar bytes are stored in Supabase Storage, not on the FastAPI backend filesystem. The app keeps one active avatar path on the profile row and best-effort deletes the user's previous avatar after a successful replacement.

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

Press `i` in the Expo terminal to open the iOS Simulator or `w` to open web.
Both clients use the same FastAPI process: the simulator connects to
`localhost:8000`, while web uses a same-origin Metro proxy at `/__peso_api` so
local browser previews do not need direct access to port 8000.

The start scripts set the web surface explicitly. `npm start` uses
`EXPO_PUBLIC_WEB_SURFACE=native-preview`, so pressing `w` renders the reusable
mobile root without React Router. `npm run web` uses
`EXPO_PUBLIC_WEB_SURFACE=web-app` with a local `/` router base. Production Expo
exports use the same Web App surface at `/app`.

To open web immediately while still starting FastAPI:

```bash
npm run web
```

To run the frontend and backend separately:

```bash
npm run start:frontend
npm run start:backend
```

### Local analysis observability dashboard

The desktop dashboard is a development-only tool for diagnosing a local analysis run without exposing diagnostics in the athlete app. It stores the most recent 20 traces under `backend/.peso/analysis-traces/`, which is ignored by Git. Production startup rejects `ANALYSIS_TRACE_ENABLED=true`.

With the backend running locally, start it in a second terminal from the project root:

```bash
npm --prefix dashboard install
npm run dashboard
```

Sign in with the same Supabase account used in Peso. The dashboard reads only traces owned by that account and retrieves playback through the existing owner-checked playback endpoint. It shows raw pose, pin/manual tracks, repaired pose, barbell path, stage timings, frame-level source and rejection decisions, and lift-specific diagnostics.

Use **Feedback annotations** to review a time interval and selected keyframes as good, bad, or uncertain; identify affected systems and landmarks; record expected fallback behavior; and place optional ground-truth pose or barbell corrections on a frame. Annotations are owner-scoped local files under `backend/.peso/analysis-feedback/`, not Supabase data. **Export feedback bundle** produces the redacted trace files plus `feedback.json` and a readable `feedback-summary.md`; it still excludes user/video IDs, storage paths, URLs, bearer credentials, source video, and still-frame media.

Tracing is enabled by default only when `BACKEND_ENV` is `development`, `dev`, or `local`. These optional backend variables make the behavior explicit:

```dotenv
ANALYSIS_TRACE_ENABLED=true
ANALYSIS_TRACE_DIR=.peso/analysis-traces
ANALYSIS_TRACE_MAX_RUNS=20
```

For Expo Go on a physical phone, the backend must bind to `0.0.0.0` so another device on the same network can reach it.

### Static web hosting

The public beta website is split into two browser surfaces:

* Astro owns `/`, `/privacy`, and `/terms` under `web/`.
* `App.web.tsx` selects either the Expo Web App or the reusable native root,
  while `App.tsx` remains the native entry point.

Start the marketing site while editing public pages:

```bash
npm run web:marketing
```

Build both surfaces and preview the combined Netlify output locally:

```bash
npm run web:build
npm run web:preview
```

The build writes the static Astro pages to `dist/` and the Expo single-page app
to `dist/app/`. `netlify.toml` serves existing marketing files first and rewrites
only unknown `/app/*` paths to `/app/index.html`. Demo Analysis remains a
browser-local simulation. Peso Account authentication, the shared Saved Lift
Library, deletion, and export jobs use the authenticated backend.

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
* `POST /saved-lift-exports` — queues one owner-checked Saved Lift ZIP
* `GET /saved-lift-exports/{job_id}` — polls export status and refreshes its temporary download
* `POST /saved-lifts/delete` — permanently deletes a selected Saved Lift set
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

Dry-runs cleanup by default and reports reclaimable storage without deleting anything. Pass `confirm=true` to delete unnecessary Supabase Storage data and mark eligible rows discarded. Cleanup removes expired pending uploads, stale pending analysis jobs, old analyzed export MP4s, expired Saved Lift ZIPs, and unreferenced app-owned upload objects. Saved source videos are never deleted by retention cleanup.

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

The current version demonstrates the core product idea: upload a lifting video, analyze the movement, and return useful visual feedback. The next major milestone is launching the web beta while improving tracking reliability across real-world gym videos with clutter, occlusion, and imperfect camera angles. The mobile app remains in active development alongside that work.

## Repository structure

```text
.
├── assets/                 # App assets and README demo media
├── backend/                # FastAPI video-analysis backend
├── dashboard/              # Local development-only analysis trace dashboard
├── lib/                    # Shared frontend utilities
├── scripts/                # Development scripts
├── src/                    # Native app and Web App source code
├── web/                    # Astro Marketing Site
├── supabase/migrations/    # Database migrations
├── App.tsx                 # Native app entry point
├── App.web.tsx             # Web App entry point
├── package.json            # Frontend scripts and dependencies
└── README.md
```

## Notes

Peso is a coaching and analysis tool, not a medical or professional training replacement. The app is meant to help lifters review movement patterns and better understand their own training videos.
