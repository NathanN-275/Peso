# Production Render analysis beta release

Render remains the current hosted backend while the isolated Azure Student
environment is tested. ADR 0012 does not authorize a paid Azure production
cutover or a Netlify backend change.

`render.yaml` defines a Starter API and a Standard worker without requiring a
Render Pro workspace. Both use the root Docker image and the same backend code.
This runbook applies only to production under ADR 0010.

Do not clone these Render services for staging. Isolated Student analysis is
governed by ADR 0012 and `docs/deployment/azure-student-setup.md`. Never apply
the Azure runbook to either production Render service.

## Required secrets

Set these as secret environment variables on both services:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`
- `CLEANUP_JOB_TOKEN`
- `BACKEND_CORS_ORIGINS`

Use exact HTTPS origins in `BACKEND_CORS_ORIGINS`, separated by commas. Include
the production Netlify origin and only explicitly approved production-preview
origins. Never use `*`, localhost, or a private-network regular expression in
production.

## Release order

1. Apply all pending Supabase migrations, including
   `20260713233319_durable_analysis_jobs.sql` and
   `202608170001_analysis_job_observability.sql`.
2. Confirm the database exposes every column selected by
   `AnalysisJobRepository.check_readiness()`.
3. Deploy the Render API and confirm `GET /health/ready` returns `200` with
   `Cache-Control: no-store`.
4. Deploy the worker and confirm it claims a queued representative production
   smoke-test job without touching staging data.
5. Validate the production-bound client release with
   `EXPO_PUBLIC_PRODUCTION_BACKEND_URL` set to the existing Render API URL, then
   complete the approved upload, processing, review, save, and discard checks.
6. Promote through the existing production release path.

Do not deploy the API or worker before the migration. Render will reject an API
deploy whose readiness endpoint returns `503`, preventing a stale schema from
becoming healthy.

## Worker sizing gate

Run the sizing benchmark in the isolated Azure Student environment first. A
later, separately approved Render sizing check may use representative side-view
squat recordings, including the longest beta-allowed clip, while capturing
Render's peak memory and processing duration. Repeat the set at least twice to
include model warm-up behavior.

- Peak memory below 400 MB for every run: Starter is eligible for production.
- Any run at or above 400 MB, an out-of-memory restart, or unstable latency: use
  Standard for production.

Keep at least 100 MB below Starter's memory ceiling. Do not infer production
sizing from an idle worker or a synthetic clip.

## Rollback

If Student testing interferes with the shared queue, pause the Student worker
and verify one current hosted job completes on Render. Do not change the
Netlify production backend, delete Azure resources, or reverse an additive
queue migration while jobs reference it.
