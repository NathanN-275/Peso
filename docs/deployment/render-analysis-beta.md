# Isolated Render beta deployment runbook

This runbook creates and accepts the non-production Render beta authorized by
ADR 0015. It does not change or deploy production `render.yaml`,
`Peso-backend`, `peso-analysis-worker`, the production Netlify site, or the
production Supabase project.

## 1. Prerequisites and fixed boundaries

- Use only `peso-staging` (`iseqgaewjpjcxrndibep`) and two dedicated staging
  users. Record both user UUIDs in private release evidence.
- Keep the Netlify `main` branch private. Its only accepted browser origin is
  `https://main--peso-webapp.netlify.app`.
- Confirm Azure has completed a Student compute pause before queue testing. A
  resumed Azure Student worker and the Render beta worker must never consume
  the staging queue concurrently.
- Review current Render pricing before creating paid services. Do not select or
  modify an existing production service when importing the Blueprint.

## 2. Validate code, Blueprint, and database history

Run the **Render Beta Release Validation** workflow from `main`. It performs
policy and release-environment tests, application type checking, backend tests,
a root-Dockerfile build, offline Docker runtime checks, Render Blueprint
validation, and the `peso-staging` migration-history check and dry run. Download
and review the `render-beta-migration-plan-<run-id>` artifact.
Configure `RENDER_WORKSPACE_ID` as a non-secret repository variable and
`RENDER_API_KEY` as a protected repository secret first. They are used only by
the validation command to check schema, semantics, and conflicts; the workflow
contains no Render deploy command. Runtime Supabase and cleanup secrets remain
Render-only.

The equivalent local Blueprint command requires Render CLI 2.7.1 or newer:

```bash
render blueprints validate render-beta.yaml --workspace <non-production-workspace-id>
```

Stop if migration history contains remote-only or out-of-order versions. Review
every pending SQL file, its RLS impact, and rollback. The validation workflow
does not apply migrations or deploy anything. Apply only the reviewed plan to
`peso-staging` in a separately approved database change, then record the final
migration list.

## 3. Create the isolated Blueprint

In Render, create a new Blueprint that points specifically to
`render-beta.yaml` on `main`. Disable Blueprint Auto Sync in the dashboard in
addition to the service-level `autoDeployTrigger: off` safeguards. Confirm the
preview names only these new services:

- `peso-beta-api` on Starter, with `/health/ready` as its health check;
- `peso-beta-analysis-worker` on Starter, with
  `python -m app.jobs.analysis_worker` as its command.

Do not continue if Render proposes adopting or modifying `Peso-backend` or
`peso-analysis-worker`.

Before the first manual deploy, enter these values separately on both beta
services in Render. Do not put them in Netlify, GitHub, or the repository:

- `SUPABASE_URL`: exact `peso-staging` URL;
- `SUPABASE_SERVICE_ROLE_KEY`: staging service-role key;
- `SUPABASE_JWT_SECRET`: staging JWT secret;
- `CLEANUP_JOB_TOKEN`: dedicated beta cleanup token.

The Blueprint fixes `BACKEND_ENV=production`,
`PESO_DEPLOYMENT_ENVIRONMENT=student`, exact CORS, and
`UPLOAD_RESERVATIONS_ENABLED=false`. Confirm neither service has
`AZURE_BLOB_ACCOUNT_URL`, `AZURE_BLOB_SOURCE_CONTAINER`, an Azure identity, or
a budget-shutdown token inherited from an environment group.

## 4. Manual deploy and release binding

Deploy the API manually from the reviewed commit. Do not deploy the worker
until the migration list matches the reviewed evidence and API readiness is
`200`. Verify readiness has `Cache-Control: no-store`; an allowed preflight
echoes only the exact private-main origin; an unknown origin is denied without
`Access-Control-Allow-Origin`.

Deploy the worker manually from the same commit. Record the two Render service
IDs, exact source commit, and SHA-256 of `render-beta.yaml`. Update
`config/render-beta-release-binding.json` in a reviewed commit:

```json
{
  "schema_version": 1,
  "status": "accepted",
  "api_url": "https://peso-beta-api.onrender.com",
  "blueprint_sha256": "<64 lowercase hex characters>",
  "source_commit": "<40 lowercase hex characters>",
  "api_service_id": "srv-...",
  "worker_service_id": "srv-..."
}
```

The pending or malformed binding blocks the private-main Netlify build. Never
copy the beta URL into production Netlify configuration.

## 5. Acceptance and owner isolation

With the accepted binding deployed to the private `main` client:

1. Sign in as dedicated staging user A; upload the longest accepted clip and
   confirm queueing, worker claim, completion, review, and save.
2. Sign in as user B and prove A's row, source, playback, thumbnail, result,
   and export cannot be listed, read, signed, modified, or deleted.
3. Upload and discard a separate clip as B; prove A cannot observe it.
4. Verify login, logout, expired/invalid bearer rejection, exact CORS, readiness,
   upload, save, discard, and cleanup behavior.
5. Process the same longest accepted clip a second time. For both runs, record
   start/finish times, peak memory, restarts, deploy ID, job ID, and user UUID.

Starter passes only if both runs finish with no OOM, no restart, and peak
memory strictly below 400 MB. Otherwise change only the beta worker plan to
Standard, manually redeploy it, and repeat both runs. Never infer sizing from
idle memory or a shorter synthetic clip.

After acceptance, remove both dedicated users through the admin harness and
verify their rows and storage objects are gone.

## 6. Rollback

Disable the private-main branch build or restore its prior reviewed binding,
then suspend `peso-beta-analysis-worker` before taking the beta API out of
service. Preserve migration and acceptance evidence. Do not roll back an
additive migration while queued or saved records depend on it, do not resume
Azure Student compute automatically, and do not modify production Render or
Netlify services.
