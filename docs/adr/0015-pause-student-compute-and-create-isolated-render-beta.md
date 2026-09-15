# ADR 0015: Pause Student compute and create an isolated Render beta

## Status

Accepted

## Context

The Azure Students subscription cannot currently provide the intended Student
compute path within the desired quota and cost envelope. Student compute can be
suspended without deleting the resource group or any supporting resources that
already exist. At the time of this decision, the Student API and worker have
not been deployed, so their absence is the verified zero-compute state.
Production already runs on Render, but changing or reusing either production
service would mix beta data and release risk with production.

The private Netlify `main` branch and `peso-staging` already form an isolated
non-production client and data boundary. They can be paired with separate
Render services while preserving production Render and Netlify configuration.

## Decision

Perform a **Student compute pause**: disable ingress on `peso-student-api`, set
the `peso-student-analysis-worker` scaler query to `SELECT 0`, and stop active
worker executions. Verify the API reaches zero replicas and the worker reaches
zero active executions. If either workload is absent, record that absence as
zero compute instead of fabricating ingress, scaler, or replica evidence. Keep
`peso-student-centralus-rg` and every existing identity, Key Vault, Log
Analytics, budget, or storage resource intact. Never modify `peso-rg`,
`peso-env-centralus`, `peso-api`, or `peso-analysis-worker` as part of this
decision.

Create an isolated **Render beta** from `render-beta.yaml` with
`peso-beta-api` and `peso-beta-analysis-worker`. Both build from the root
`Dockerfile`, use manual deploys, run with production hardening, and set
`PESO_DEPLOYMENT_ENVIRONMENT=student` so the backend refuses any Supabase
project except `peso-staging`. Render alone stores the staging service-role
key, staging JWT secret, and beta cleanup token. The only browser origin is
`https://main--peso-webapp.netlify.app`. Upload reservations remain disabled
and no Azure Blob settings are configured.

The private Netlify `main` branch changes from the paused Azure Student API to
the accepted Render beta API. A tracked, fail-closed release binding must match
the exact Render API origin and verified Blueprint/source evidence before the
branch can build. Production `render.yaml`, production Render services,
production Netlify configuration, and the production Supabase project remain
unchanged.

The beta worker starts on Starter. It remains there only if the longest
accepted clip completes twice with no OOM or restart and every observed peak
memory value is below 400 MB. Any failure upgrades only
`peso-beta-analysis-worker` to Standard.

## Consequences

- The pause is reversible and is not an Azure teardown. Retained services can
  still incur small charges, so it does not promise a literal $0 bill.
- A missing Student API or worker is recorded as absent and zero compute; pause
  remains idempotent, while resume fails closed when either workload is absent.
- A future Azure resume must use the reviewed compute-control workflow and
  re-enable only the Student API and Student worker scaler.
- Render beta has its own paid compute and secrets. Its staging queue must not
  be consumed concurrently by a resumed Azure Student worker.
- Migration history comparison and a dry run are required before any beta
  deploy; applying migrations remains a separate reviewed write.
- The pending release binding intentionally blocks the private branch until
  the Render API deployment and evidence have been accepted.
- Deleting Student-only Azure infrastructure requires a separate destructive
  decision and explicit approval.
