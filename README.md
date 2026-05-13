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
VIDEO_BUCKET=videos
MODEL_VERSION=mediapipe-pose-v1
BACKEND_CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081,http://localhost:8082,http://127.0.0.1:8082,http://localhost:19006,http://127.0.0.1:19006,http://localhost:3000,http://127.0.0.1:3000
```

`BACKEND_CORS_ORIGINS` exists to support the common Expo web, simulator, and local browser ports used by the mobile client.

## Installation

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the API

Start the server from the `backend` directory so `app.main:app` resolves correctly:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If you keep environment variables in a file, you can also use:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
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

Marks the video as saved.

### `DELETE /videos/{video_id}`

Deletes the video record and removes the underlying file from Supabase Storage.

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
- The analysis pipeline is built around `PoseEstimator` and `SquatAnalyzer`, with results written back through `VideoRepository`.
- `model_version` is stored with each analysis result so future analysis passes can coexist with older ones.

## Typical Local Flow

1. Start Supabase and make sure the `videos` table and storage bucket exist.
2. Set the required environment variables.
3. Start this backend on port `8000`.
4. Point the frontend at the backend URL for your platform.

## Project Notes

The project proposal also mentions a future technique coach bot and bar-path visualization. Those pieces are part of the product vision, but the backend in this repository currently supports the video analysis and storage pipeline that the mobile app depends on.
