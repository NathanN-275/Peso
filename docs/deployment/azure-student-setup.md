# Azure Student environment setup and acceptance

This runbook creates one non-production backend environment in Central US. It
changes only the test branch website configuration, never production Azure resources or
modify/delete anything in `peso-rg`.

## 1. One-time bootstrap

From an Azure owner session on the Azure Students subscription, preview and then
create the fixed resource group, identities, Key Vault, OIDC credential, and
budget:

```bash
az deployment sub what-if \
  --location centralus \
  --template-file infra/azure/bootstrap.bicep \
  --parameters githubRepository=NathanN-275/Peso \
    budgetContactEmails='["nathanngau27@gmail.com"]'

az deployment sub create \
  --name peso-student-bootstrap \
  --location centralus \
  --template-file infra/azure/bootstrap.bicep \
  --parameters githubRepository=NathanN-275/Peso \
    budgetContactEmails='["nathanngau27@gmail.com"]'
```

Confirm the output resource group is exactly
`/subscriptions/<subscription-id>/resourceGroups/peso-student-centralus-rg`.
The deployment identity receives Contributor, Cost Management Reader, and Log
Analytics Reader only at that group, plus Key Vault Secrets Officer only at the
student vault. The runtime identity receives Key Vault Secrets User only at the
student vault.

The $10 monthly budget sends actual-cost email alerts at $5, $8, and $10. Azure
Budget alerts only; they do not stop resources. The daily workflow implements
the separate pause policy.

## 2. GitHub `student` environment

Create one protected GitHub environment named `student`, with a custom deployment
branch rule allowing only `main` (no tags). Require review of migration previews,
what-if and expected costs before the deployment job. Configure identifiers
as variables, not credentials:

- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- `GHCR_USERNAME`, `SUPABASE_CLI_VERSION`
- `STUDENT_NETLIFY_ORIGIN`: `https://main--peso-webapp.netlify.app`
- `PRODUCTION_NETLIFY_ORIGIN`: the exact current production origin, used only
  to prove the Student origin is different
- the public `EXPO_PUBLIC_*` validation values, except for the backend URL. The
  backend URL is bound by the generated, reviewed release-evidence file below.

Configure these environment secrets:

- `GHCR_READ_TOKEN`
- `SUPABASE_DB_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_JWT_SECRET`
- `CLEANUP_JOB_TOKEN`, `BUDGET_SHUTDOWN_TOKEN`
- `AZURE_SCALER_POSTGRES_PASSWORD` and
  `AZURE_SCALER_POSTGRES_CONNECTION`

The scaler connection uses the dedicated `peso_azure_scaler_student` login and
`sslmode=require`; it must not use the database owner or Supabase service-role
credential. Do not create `AZURE_CREDENTIALS`, an Azure client secret, or a
production GitHub environment for this path.

## 3. Permanent peso-staging database and test users

Use only `peso-staging` (`iseqgaewjpjcxrndibep`). Never use production
`PesoDatabase` (`jfgiydtrskpqxyorvvbc`), its credentials, or the repository
CLI link when it targets production. Use an isolated CLI workdir or an explicit
validated database URL. Preserve existing staging data. Create two
dedicated users through the admin test harness with unique addresses such as
`peso-student+<run>-a@<test-domain>` and `...-b@...`. Record their UUIDs in the
release evidence and use the normal owner-scoped RLS paths for every row and
storage object.

Before applying database changes:

1. Run `node scripts/student-environment.js --database-only`, then compare
   `supabase migration list --db-url "$SUPABASE_DB_URL"` with the local filenames.
   Stop on remote-only or out-of-order versions; never repair history blindly.
2. Run `supabase db push --db-url "$SUPABASE_DB_URL" --dry-run`.
3. Review every pending migration and its RLS impact. The reservation migration
   replaces the enqueue RPC signature; drain the queue and retain the old
   function definition for rollback. It is not additive-only.
4. Run the Supabase security advisor/RLS audit.
5. Apply without `--include-all`, then record `supabase migration list`.

The Azure scaler migration adds one aggregate queue-depth function in the
unexposed, dedicated `azure_scaler` schema. It revokes
execute from `public`, `anon`, `authenticated`, and `service_role`; the setup
script grants execute only to the read-only scaler login. After testing, sign
out/revoke sessions, delete both users through the admin harness, and verify
their owned database rows and storage objects are gone. Never use user-editable
metadata as the isolation boundary.

## 4. Preview and deploy

Run the **Azure Student Backend Deploy** workflow from `main` with an immutable
lowercase `ghcr.io/nathann-275/peso-backend@sha256:...` digest and
`preview_only=true` first. After reviewing the saved
what-if, migration preview and expected costs, rerun the same candidate with
`preview_only=false`. `pose_comparison_approved` must remain false until the
reviewed real-clip comparison and local acceptance pass. Supply the same digest
as `pose_comparison_image_reference`; deployment rejects evidence for any other
image. Its validation job runs policy tests, type checks, backend tests,
both Bicep builds, and the Supabase migration dry-run before Azure
authentication. The preview job then:

1. verifies the fixed resource-group ID;
2. records a group-scope `what-if` artifact.

Inspect both previews before approving the protected deploy job. That job:

1. applies the reviewed Supabase migrations;
2. configures the least-privileged scaler login;
3. writes runtime and GHCR credentials into Key Vault;
4. deploys `infra/azure/student.bicep`;
5. verifies readiness, exact allowed CORS, unknown-origin rejection, and budget
   configuration; and
6. uploads the exact new resource IDs and generated frontend API binding as
   immutable run evidence.

Review the what-if before accepting the run. Every resource ID must begin with
`/subscriptions/<id>/resourceGroups/peso-student-centralus-rg/`. The backend
workflow does not publish Netlify. Only after acceptance, download
`azure-student-release-evidence-<run-id>` and verify its deployment output hash.
In a reviewed PR, replace `config/student-api-release-binding.json` with the
generated `student-api-release-binding.json` unchanged. A pending or malformed
tracked binding keeps the Student Netlify build blocked.

## 5. Acceptance suite

Use only the two isolated users:

1. Verify Key Vault RBAC, the OIDC subject, resource-group role scopes, and the
   absence of long-lived Azure credentials in GitHub.
2. Verify `/health/ready`, the exact approved origin, and rejection of an
   unknown origin without `Access-Control-Allow-Origin`.
3. Run signup, confirmation, login, upload, processing, review, save, ownership
   isolation, discard/delete, logout, and user deletion for both users.
4. Process the longest accepted test clip twice. Each run must start within 60
   seconds, finish under 600 seconds, remain below 400 MiB peak memory, and have
   zero restarts. The fixed small worker is not automatically upsized on failure.
5. After idle time, query the API revision replicas and worker executions and
   confirm both are zero.
6. Run **Azure Student Daily Cost Check** manually once and retain its report.
7. Query the budget and confirm amount `10`, Monthly grain, and enabled actual
   thresholds `50`, `80`, and `100`.

## 6. Cost response and rollback

The daily workflow records month-to-date spend, a linear monthly projection,
worker executions and failures, API readiness, and API restart count.

- Below $8: record only.
- At or above $8: set the worker queue query to `SELECT 0` and stop running
  executions.
- At or above $10: also disable API ingress, fail the workflow, and investigate.

Use **Azure Student Compute Control** for a reviewed manual pause or resume.
Re-running Bicep can undo an automatic pause, so check current spend first.

If acceptance fails, pause Student compute and keep the existing website,
production backend, PesoDatabase, and `peso-rg` resources unchanged. Do not reverse an
additive migration while queued rows depend on it.

## 7. Separate legacy deletion approval

Only after the full acceptance suite passes, query exact `peso-rg` resource IDs
using the command in `azure-release-evidence.md`. Present the complete list with
replacement and rollback evidence. Delete nothing until Nathan separately
approves those exact IDs.

## 8. Test website configuration

Netlify `context.main` fixes the public Supabase URL and `PESO_RELEASE_ENV=student`.
Set these remaining values **only for branch `main`** in peso-webapp:

- `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: peso-staging public key; remove any
  inherited production anon-key fallback from this branch.
- `EXPO_PUBLIC_PRODUCTION_BACKEND_URL`: the accepted Student API HTTPS origin
  from the generated binding. The build requires an exact match with the
  reviewed file tracked in `config/student-api-release-binding.json`; two
  matching Netlify variables cannot override it.
- `EXPO_PUBLIC_AUTH_CHALLENGE_URL`: `https://main--peso-webapp.netlify.app/auth/turnstile/`.
- `EXPO_PUBLIC_TURNSTILE_SITE_KEY`: the test site's approved challenge key.

Despite its legacy variable name, this branch's backend URL is Student. The
release validator rejects a pending binding, production database, unrelated
API, or challenge hosted outside the exact test site.
Configure peso-staging auth site URL and exact redirects for
`https://main--peso-webapp.netlify.app/app` and the application's auth callback
paths. Verify both test users can authenticate before testing storage RLS.
Do not edit global Netlify values, production context, or production hosting.

## 9. Runtime release gate

Run `python scripts/fetch_pose_models.py` for local/CI backend setup. The image
fetches and verifies all three models while building; runtime networking is not
needed. `./scripts/verify_container_runtime.sh IMAGE` exercises UID 10001 with
network disabled and a read-only root filesystem. Its image fixture checks
native inference and media contracts, never real-clip model equivalence.
Record the separately reviewed real squat comparison before deploying. The
complete application image must pass Trivy with zero HIGH/CRITICAL findings,
including unfixed findings. Never publish an image that failed either check.
The publication workflow uploads one evidence artifact containing the final
registry digest, local image identity, runtime result, strict scan policy and
raw Trivy JSON; retain it with the copied release checklist.
The retired West US automatic deployment has been removed; publication on main
produces a candidate, and the Student deployment workflow handles rollout.
