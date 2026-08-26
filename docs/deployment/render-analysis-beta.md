# Render analysis beta release

`render.yaml` defines a Starter API and a Standard worker without requiring a
Render Pro workspace. Both use the root Docker image and the same backend code.

Do not add or create the separate staging API/worker until the Render service
costs are explicitly confirmed. Once approved, clone both services with
`-staging` names, staging-only Supabase credentials, a staging CORS origin, and
manual promotion. Never point a staging worker at the production queue.

## Required secrets

Set these as secret environment variables on both services:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`
- `CLEANUP_JOB_TOKEN`
- `BACKEND_CORS_ORIGINS`

Use exact HTTPS origins in `BACKEND_CORS_ORIGINS`, separated by commas. Include
the production Netlify origin and only the preview origins being tested. Never
use `*`, localhost, or a private-network regular expression in production.

## Release order

1. Apply all pending Supabase migrations, including
   `20260713233319_durable_analysis_jobs.sql` and
   `202608170001_analysis_job_observability.sql`.
2. Confirm the database exposes every column selected by
   `AnalysisJobRepository.check_readiness()`.
3. Deploy the Render API and confirm `GET /health/ready` returns `200` with
   `Cache-Control: no-store`.
4. Deploy the worker and confirm it claims a queued representative squat job.
5. Create a Netlify preview with `EXPO_PUBLIC_PRODUCTION_BACKEND_URL` set to the
   Render API URL, then complete upload, processing, review, save, and discard.
6. Promote through `main`, then `production`.

Do not deploy the API or worker before the migration. Render will reject an API
deploy whose readiness endpoint returns `503`, preventing a stale schema from
becoming healthy.

## Worker sizing gate

Start the staging benchmark with the worker on Starter. Process representative
side-view squat recordings, including the longest beta-allowed clip, while
capturing Render's peak memory and processing duration. Repeat the set at least
twice to include model warm-up behavior.

- Peak memory below 400 MB for every run: Starter is eligible for production.
- Any run at or above 400 MB, an out-of-memory restart, or unstable latency: use
  Standard for production.

Keep at least 100 MB below Starter's memory ceiling. Do not infer production
sizing from an idle worker or a synthetic clip.

## Rollback

Set `ANALYSIS_PROFILE_MODE=legacy` if a candidate profile was enabled. Roll the
API and worker back to the last healthy image together. Do not reverse an
additive queue migration while jobs reference its columns. Netlify can publish
the last known-good deploy independently.
