# ADR 0011: Host isolated staging analysis workloads on Azure Container Apps

## Status

Superseded by ADR 0012

The West US 2 staging design was reconciled into the single Central US Student
environment. Retain this record for history; do not provision or deploy it.

## Context

Peso needs an isolated, externally testable staging API and analysis worker.
Keeping an always-on staging worker on Render would add a fixed service charge
before staging traffic exists. The Azure for Students subscription provides a
small credit fallback, and the Container Apps Consumption plan can scale both
staging workloads to zero.

## Decision

Host only the staging analysis workloads in Azure Container Apps in West US 2:

- `peso-backend-staging` is a public HTTPS Container App with zero minimum and
  one maximum replica.
- `peso-analysis-worker-staging` is an event-driven Container Apps Job with zero
  minimum and one maximum execution. Its PostgreSQL scaler calls the private
  `public.pending_video_analysis_job_count()` database function.
- Both workloads initially use 0.25 vCPU and 0.5 GiB and run the same public
  `ghcr.io/nathann-275/peso-backend` image by immutable digest.
- GitHub Actions authenticates with OIDC. Its custom role is assigned directly
  to the API and job and can update only those resource types.
- Secrets are seeded locally after the disabled bootstrap deployment. Bicep
  references their short names but never declares or stores their values.
- A resource-group-scoped monthly budget alerts at 50%, 80%, and 100% of $1.
  The budget is an alert and not a hard spending limit.

Provisioning requires a current price, credit, quota, and Supabase-capacity
review followed by Nathan's explicit approval. Public Netlify staging visibility
requires a separate action-time approval.

## Scope

This decision applies only to the isolated staging stack. ADR 0010 remains the
authoritative production hosting decision: the production API and worker stay
on Render. The production Supabase project, Netlify production branch, primary
URL, configuration, and visibility are unchanged.

## Consequences

- The idle compute charge is $0 when both workloads are scaled to zero, but
  active replicas, requests, and logs remain usage-billed after their grants.
- The 30-second event-scaler polling interval can add queue-start latency, and
  the API can incur a cold start.
- Azure retries are disabled for the worker job; the application queue remains
  authoritative for leases, failures, and retries.
- The staging scaler login is the only principal that can execute the count
  function. The migration leaves that role inert with `NOLOGIN` everywhere;
  staging activation and its generated password are operational steps.
- A failed or over-budget staging environment can be disabled without changing
  production: stop worker executions, disable API ingress, and close the
  Netlify branch deploy.
