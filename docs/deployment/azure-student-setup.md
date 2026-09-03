# Azure Student environment setup and acceptance

This runbook creates one non-production backend environment in Central US. It
does not deploy the Netlify website, create production Azure resources, or
modify/delete anything in `peso-rg`.

## 1. One-time bootstrap

From an Azure owner session on the Azure Students subscription, preview and then
create the fixed resource group, identities, Key Vault, OIDC credential, and
budget:

```bash
az deployment sub what-if \
  --location centralus \
  --template-file infra/azure/bootstrap.bicep \
  --parameters githubRepository=<owner/repository> \
    budgetContactEmails='["<email>"]'

az deployment sub create \
  --name peso-student-bootstrap \
  --location centralus \
  --template-file infra/azure/bootstrap.bicep \
  --parameters githubRepository=<owner/repository> \
    budgetContactEmails='["<email>"]'
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

Create one protected GitHub environment named `student`. Configure identifiers
as variables, not credentials:

- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- `GHCR_USERNAME`, `SUPABASE_CLI_VERSION`
- `STUDENT_NETLIFY_ORIGIN`: one exact non-production `https://*.netlify.app`
  origin, with no path, port, or trailing slash
- `PRODUCTION_NETLIFY_ORIGIN`: the exact current production origin, used only
  to prove the Student origin is different
- the public `EXPO_PUBLIC_*` validation values and
  `CURRENT_NON_AZURE_BACKEND_URL`

Configure these environment secrets:

- `GHCR_READ_TOKEN`
- `SUPABASE_DB_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_JWT_SECRET`
- `CLEANUP_JOB_TOKEN`
- `AZURE_SCALER_POSTGRES_PASSWORD` and
  `AZURE_SCALER_POSTGRES_CONNECTION`

The scaler connection uses the dedicated `peso_azure_scaler_student` login and
`sslmode=require`; it must not use the database owner or Supabase service-role
credential. Do not create `AZURE_CREDENTIALS`, an Azure client secret, or a
production GitHub environment for this path.

## 3. Existing Supabase project and test users

Use the existing Supabase project. Do not seed shared user rows. Create two
dedicated users through the admin test harness with unique addresses such as
`peso-student+<run>-a@<test-domain>` and `...-b@...`. Record their UUIDs in the
release evidence and use the normal owner-scoped RLS paths for every row and
storage object.

Before applying database changes:

1. Run `supabase db push --db-url "$SUPABASE_DB_URL" --dry-run`.
2. Review every pending migration for additive-only behavior and RLS impact.
3. Run the Supabase security advisor/RLS audit.
4. Apply without `--include-all`, then record `supabase migration list`.

The Azure scaler migration adds one aggregate queue-depth function in the
unexposed, dedicated `azure_scaler` schema. It revokes
execute from `public`, `anon`, `authenticated`, and `service_role`; the setup
script grants execute only to the read-only scaler login. After testing, sign
out/revoke sessions, delete both users through the admin harness, and verify
their owned database rows and storage objects are gone. Never use user-editable
metadata as the isolation boundary.

## 4. Preview and deploy

Run the **Azure Student Backend Deploy** workflow with an immutable lowercase
GHCR digest. Its validation job runs policy tests, type checks, backend tests,
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
6. uploads the exact new resource IDs as evidence.

Review the what-if before accepting the run. Every resource ID must begin with
`/subscriptions/<id>/resourceGroups/peso-student-centralus-rg/`. No workflow in
this path runs a Netlify publish or changes the website backend setting.

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
backend, Supabase project, and `peso-rg` resources unchanged. Do not reverse an
additive migration while queued rows depend on it.

## 7. Separate legacy deletion approval

Only after the full acceptance suite passes, query exact `peso-rg` resource IDs
using the command in `azure-release-evidence.md`. Present the complete list with
replacement and rollback evidence. Delete nothing until Nathan separately
approves those exact IDs.
