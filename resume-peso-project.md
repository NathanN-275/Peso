# Peso Resume Insert

Use this under a **Projects** section. This version is written for a portfolio prototype and uses only repo-derived metrics.

## Project Header

**Peso - Full-Stack AI Lifting Analysis App**  
React Native, Expo, TypeScript, FastAPI, Supabase, OpenCV, MediaPipe, RTMPose

## Recommended 3-Bullet Version

- Built a full-stack mobile lifting analysis app spanning 8 authenticated FastAPI endpoints, 26 React Native/Expo frontend modules, and Supabase-backed auth/storage by implementing video upload, queued analysis, saved-video review, export, and discard workflows.
- Implemented a squat-analysis computer vision pipeline that generates 10+ per-rep and clip-level metrics by sampling videos at up to 18 FPS, running MediaPipe/RTMPose pose estimation, segmenting reps, scoring depth, tracking torso angle, estimating velocity, and producing coaching feedback.
- Improved reliability of core squat analysis flows, validated by 64 passing backend tests, by adding pose-quality checks, landmark validation, fallback model selection, uncertain-depth handling, idempotent queueing, and analysis versioning.

## Shorter 2-Bullet Version

- Built a full-stack AI mobile app across 72 source/test files and 8 authenticated FastAPI endpoints by integrating a React Native/Expo frontend with Supabase auth/storage and an async video-analysis backend.
- Implemented squat analysis that produces 10+ rep and video metrics, validated by 64 passing core backend tests, by combining MediaPipe/RTMPose pose estimation, rep segmentation, depth scoring, velocity estimates, quality diagnostics, and coaching feedback.

## Optional Backend-Focused Bullet

- Designed a video persistence workflow covering queued, completed, saved, discarded, expired, and exported videos by integrating Supabase database rows, storage objects, signed URLs, JWT ownership checks, cleanup logic, and H.264 analyzed-video exports.

## Metrics Used

- Scope: 8 FastAPI routes, 26 frontend modules, 72 source/test files, about 17.2k LOC.
- Analysis output: rep count, depth score/status/confidence, duration, rep speed, average/peak velocity, torso angle change, pose coverage, lower-body visibility, side-view confidence, landmark jitter, and coaching feedback.
- Reliability: 64 passing core backend tests. Avoid claiming full-suite reliability until the current barbell tracker test failures are resolved.

## Claims To Avoid For Now

- Do not claim production usage, uptime, user counts, storage scale, or accuracy percentages without logs or a benchmark dataset.
- Do not claim the full backend test suite is passing while the current barbell tracker tests fail in the dirty worktree.
