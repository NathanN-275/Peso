# Azure staging release and rollback

> Superseded by ADR 0012 and `azure-student-setup.md`. This document is retained
> for historical context only. Do not provision or deploy this West US 2 stack.

This runbook provisions and operates only the isolated Peso staging API and
analysis worker. It does not authorize Azure resource creation, provider spend,
public Netlify visibility, or production changes. Complete the approval gates
at the point where each action is taken.

## Locked boundaries

| Concern | Staging value |
| --- | --- |
| Azure subscription | `Azure for Students` |
| Region | West US 2 (`westus2`) |
| Resource group | `rg-peso-staging-westus2` |
| Log workspace | `log-peso-staging-westus2` |
| Container Apps environment | `cae-peso-staging-westus2` |
| API | `peso-backend-staging` |
| Worker job | `peso-analysis-worker-staging` |
| Deploy identity | `id-peso-staging-deploy` |
| Budget | `peso-staging-monthly` |
| Image | `ghcr.io/nathann-275/peso-backend@sha256:<digest>` |
| Supabase project | `iseqgaewjpjcxrndibep` |
| Staging web origin | `https://main--peso-webapp.netlify.app` |

Production remains governed by ADR 0010. Never reuse production secrets or
point either staging workload at the production queue.

## Gate 1: cost, credit, capacity, and explicit approval

Do not create an Azure resource until all of these checks have been refreshed
and Nathan has approved the displayed figures:

1. Verify the active subscription name, ID, state, remaining student credit,
   credit expiry, and spending-limit state. The Azure portal is authoritative
   for the remaining promotional balance when the CLI returns no balance.
2. Verify the West US 2 quota for managed Container Apps environments and the
   relevant consumption cores. Record existing usage and the post-deployment
   remainder.
3. Verify that Supabase staging is healthy and not paused, suspended, read-only,
   or approaching database size, storage, egress, connection, or organization
   free-plan limits. Reconcile conflicting CLI and dashboard health signals
   before continuing.
4. Refresh the primary-source rates and grants recorded in
   `docs/research/azure-staging-primary-sources.md`.
5. Show fixed monthly charges, the exact grants, and this workload forecast:

   ```text
   active replica cost =
     active hours × 3600 × ((0.25 × active vCPU-second rate)
                           + (0.5 × active GiB-second rate))

   maximum concurrent API-plus-worker cost = 2 × active replica cost
   request overage = max(0, requests - request grant) × per-request rate
   log overage = max(0, ingested GB - log grant) × per-GB ingestion rate
   forecast = compute overage + request overage + log overage
   ```

   The agreed envelope must state combined active replica-hours, requests, and
   log ingestion. Do not silently substitute an assumed traffic estimate.
6. Show the incremental cost for one additional active container-hour, one
   million requests, one GB of logs, and one hour with both workloads active.
7. Obtain an explicit approval that names the reviewed envelope and rates.

The `$1` budget sends actual-cost notifications at $0.50, $0.80, and $1.00. It
does not stop resources, may evaluate after usage is incurred, and must not be
treated as a safety cutoff. If paid usage appears unexpectedly, set worker
maximum executions to zero and disable API ingress immediately.

## Gate 2: source and image bootstrap

Before infrastructure bootstrap:

1. Pass `npm run test:policy`, `npm run typecheck`, backend unit tests,
   `npm run web:build:release`, and `npm run web:budget` on the release source.
2. Build `infra/azure/staging/main.bicep` with the repository-pinned Bicep
   version and review its diagnostics.
3. Merge the reviewed release PR while the repository variable
   `AZURE_STAGING_DEPLOY_ENABLED` is absent or exactly `false`.
4. Let the main workflow publish `main` and `sha-<full-commit-sha>`. A new GHCR
   package defaults to private; make only `nathann-275/peso-backend` public,
   confirm anonymous digest access, and rerun the workflow if its public-image
   check stopped the first publication.
5. Record the registry-reported `sha256:` digest. Do not deploy a mutable tag.

Changing the GHCR package to public is an external visibility change. Confirm
the exact package and action before doing it.

## Gate 3: reviewed disabled bootstrap

Use the immutable digest, subscription contact email, and a month-start date.
Do not put credentials in a parameter file. First run a subscription-scope
`what-if` with `enableWorkloads=false`, review every proposed resource, and then
obtain the provisioning approval required by Gate 1 before applying it.

The first deployment creates the resource group, 30-day Log Analytics
workspace, Consumption environment, disabled-ingress API, zero-execution job,
OIDC identity, resource-scoped role assignments, and `$1` budget. It must not
create Application Insights. Confirm after deployment that:

- the API has no public FQDN and zero minimum replicas;
- the worker has `minExecutions=0` and `maxExecutions=0`;
- the identity role is assigned only on the API and worker resource IDs;
- the role cannot list secrets, execute the job, delete resources, change the
  environment, or manage role assignments; and
- no runtime secret exists yet.

## Gate 4: staging database activation

Apply all tracked migrations through
`202608270001_add_analysis_job_scaler_signal.sql` to staging only. The migration
creates an inert `NOLOGIN` role and the fixed-search-path, `SECURITY DEFINER`
count function. It grants the role schema usage and function execution only.

In a direct staging database session, use PostgreSQL's interactive `\password`
command so the generated value is not placed in shell history or SQL text, then
enable login for that role. Do not commit the password or run this activation
against production.

Verify as an administrator and then as the scaler login:

- the function returns an integer;
- it counts only due, non-discarded `video_analysis` rows in `queued` or
  `retry_wait`;
- `PUBLIC`, `anon`, and `authenticated` cannot execute it;
- the scaler can execute only this function and cannot select or mutate any
  table, use a sequence, or execute another routine; and
- the staging session-pooler connection works with SSL.

Run the repository Supabase security audit, live ownership/RLS checks, and the
Supabase Security Advisor after applying the migration. Investigate new
warnings or errors before enabling Azure.

## Gate 5: local secret seeding and enabled deployment

Seed secrets directly from an interactive local session. Use hidden prompts or
another input mechanism that keeps values out of shell history, command output,
logs, and committed files. Never use `--debug` or command tracing during this
step.

Seed these names on both the API and worker:

- `sb-url`
- `sb-service`
- `sb-jwt`
- `cleanup-token`

Seed `scaler-db-url` only on the worker. It contains the SSL staging
session-pooler connection string for `analysis_job_scaler`; the API must never
receive it.

The enabled Bicep deployment intentionally omits the `configuration.secrets`
collection. Azure documents that removing that section during an update leaves
existing secrets unaltered; listing incomplete secret objects can delete or
replace values. Run and review a second `what-if` with `enableWorkloads=true`,
then apply it. The resulting revision references only the pre-seeded names.

Confirm no secret values appear in deployment operations, template exports,
GitHub, Netlify, the browser bundle, or logs. Confirm the API exposes HTTPS only
and exact-origin CORS, and that the job's PostgreSQL scaler is the only consumer
of `scaler-db-url`.

## GitHub OIDC deployment

Configure these repository variables after bootstrap:

- `AZURE_STAGING_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_STAGING_DEPLOY_ENABLED=false`

Leave the gate false until the disabled and enabled Bicep states, secret
readback by name, readiness, and role assignments have passed review. Then set
the gate to `true` and manually dispatch `Publish and deploy Azure staging`.
The workflow must update only the API and worker image references and verify
both read back as the same registry digest. Future `main` merges may deploy
automatically while the gate remains true.

## Authentication and Netlify

Follow `docs/deployment/auth-staging-release.md`. In summary:

- use real staging-only Turnstile keys restricted to
  `main--peso-webapp.netlify.app`;
- keep the secret only in staging Supabase Auth and the site key only in the
  Netlify branch-deploy context;
- keep Netlify's production branch, production values, primary URL, and
  production visibility unchanged;
- enable only the `main` branch deploy and disable PR Deploy Previews; and
- keep the branch deploy private until Nathan separately approves the exact
  change to Public immediately before it occurs.

## Verification

Record evidence for each gate:

1. `GET /health/ready` returns `200` with `Cache-Control: no-store` after a cold
   start. Record cold-start duration and any readiness failures.
2. One due queued staging job produces one worker execution, is exclusively
   claimed, completes once, and returns to zero executions.
3. Run two representative longest permitted side-view squat videos. Record API
   latency, processing duration, peak memory, retry/lease state, and output.
4. Keep 0.25 vCPU/0.5 GiB unless a run OOMs, exceeds 400 MiB, times out, has
   unstable readiness, or has unacceptable measured latency. Re-run the full
   cost approval before increasing either workload to 0.5 vCPU/1 GiB.
5. Run staging `npm run release:verify`, the native Maestro auth and release
   suites, and the complete upload, analysis, review, save, export, and deletion
   flow.
6. Verify `/`, `/app/`, signup, confirmation, login, logout, reset, session
   restoration, and deep-link refresh.
7. Verify two-user ownership isolation, exact CORS rejection, signed URL expiry,
   security headers, cache behavior, staging-only rows, and no production
   traffic or mutations.
8. Inspect Container Apps consumption and Log Analytics ingestion after the
   benchmark. Recalculate the monthly forecast and proceed only inside the
   approved $0 envelope.
9. After the separate visibility approval, make only the Netlify `main` branch
   deploy public and repeat unauthenticated-route and authentication smoke
   tests.

## Rollback and decommissioning

Rollback must never deploy or reconfigure production:

1. Make Netlify branch deploys private and disable the `main` branch deploy.
2. Set `AZURE_STAGING_DEPLOY_ENABLED=false`.
3. Apply the disabled Bicep state so the worker maximum is zero and API ingress
   is absent. If a release image is faulty, keep the workloads disabled while
   restoring the last known-good immutable digest to both resources.
4. Rotate every staging secret after suspected exposure.
5. For decommissioning, revoke login with
   `ALTER ROLE analysis_job_scaler NOLOGIN;` before deleting its Azure-held
   password. Leave the additive migration in place while queued jobs or code
   reference it.
6. Preserve evidence and verify that the production Render services, production
   branch, primary Netlify URL, production Supabase project, and production data
   remain unchanged.
