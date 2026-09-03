# ADR 0012: Define the Student environment

## Status

Accepted

## Context

Azure Students is the only approved Azure subscription. Peso needs a cheap,
isolated backend proving ground without implying a production cutover or moving
the Netlify website. Central US (`centralus`) is selected because the Azure
Students subscription has Container Apps Consumption quota there; the older
West US 2 staging design in ADR 0011 is superseded.

## Decision

“Student environment” means exactly one non-production Azure environment in
`peso-student-centralus-rg`. It contains a Consumption-only Container Apps
environment, a public test API, an event-triggered analysis job, Key Vault, Log
Analytics, one runtime managed identity, and one GitHub OIDC deployment
identity scoped to that resource group.

The API accepts only the exact staging/test Netlify HTTPS origin and scales from
zero to one replica. The worker has zero idle executions, at most one concurrent
execution, 0.25 vCPU, 0.5 GiB, and a 900-second execution timeout. Runtime,
scaler, and GHCR credentials live in Key Vault. GitHub uses OIDC and stores no
long-lived Azure credential.

The existing Supabase project remains authoritative. Student tests use two
dedicated test users whose owner-scoped rows and storage objects are cleaned up
after the run. Database changes must be additive, reviewed, previewed, and
verified; Student does not authorize a second Supabase project or destructive
migration.

The resource-group budget is $10/month with actual-cost email alerts at $5, $8,
and $10. Budget alerts do not stop Azure resources. A daily workflow records
month-to-date and projected spend, worker executions and failures, API
readiness, and restart count. It pauses the worker at $8 and disables the
student API ingress as well at $10, then fails for investigation.

Netlify remains the website host. Student deployment automation must not
publish, reconfigure, or cut over the website. A paid production environment
requires explicit subscription approval and a separate ADR.

## Consequences

- Cold starts are accepted because both API and worker scale to zero.
- Azure documents no resource-consumption charge while a Consumption app is at
  zero replicas, while usage beyond monthly free grants is billed against the
  subscription; see [scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
  and [billing](https://learn.microsoft.com/en-us/azure/container-apps/billing).
- The small worker is a hard cost boundary; a clip that cannot pass the memory
  and duration gate blocks acceptance rather than silently increasing size.
- Re-running Bicep restores the declared worker trigger and API ingress, so an
  operator must review current spend before deployment after an automatic
  pause.
- `peso-rg` is not a deployment or deletion target in this path.
