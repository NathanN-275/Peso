# ADR 0012: Define the Student environment

## Status

Accepted

## Context

Azure Students is the only approved Azure subscription. Peso needs a cheap,
isolated backend proving ground without implying a production cutover or moving
the Netlify website. The initial decision selected Central US for all Student
resources. ADR 0014 amends the regional placement after a live quota check found
no usable managed-environment slot there and confirmed one available slot in
West US 3.

## Decision

“Student environment” means exactly one non-production Azure environment in
`peso-student-centralus-rg`. The group name and Central US location are retained
legacy bootstrap metadata. Its existing Key Vault, runtime managed identity,
GitHub OIDC deployment identity, and budget remain in Central US and scoped to
that group. The Student-owned Consumption-only Container Apps environment,
public test API, event-triggered analysis job, Log Analytics workspace, and
future security-foundation resources are deployed in West US 3.

The API accepts only the exact staging/test Netlify HTTPS origin and scales from
zero to one replica. The worker has zero idle executions, at most one concurrent
execution, 0.25 vCPU, 0.5 GiB, and a 900-second execution timeout. Runtime,
scaler, and GHCR credentials live in Key Vault. GitHub uses OIDC and stores no
long-lived Azure credential.

The permanent Student database is the existing isolated `peso-staging` project
(`iseqgaewjpjcxrndibep`). Production `PesoDatabase`
(`jfgiydtrskpqxyorvvbc`) is never a Student target. Student runtime, public
frontend, migration owner, scaler, authentication, and storage credentials must
all belong to peso-staging. Dedicated test users and owner-scoped RLS remain
required within this separate project.

Compare remote migration history with the repository before any write. Preview
every pending migration, review its SQL and rollback, and apply only to
peso-staging. Preserve existing staging data. No production identifier or
credential may be copied into the Student environment.

The resource-group budget is $10/month with actual-cost email alerts at $5, $8,
and $10. Budget alerts do not stop Azure resources. A daily workflow records
month-to-date and projected spend, worker executions and failures, API
readiness, and restart count. It pauses the worker at $8 and disables the
student API ingress as well at $10, then fails for investigation.

Netlify remains the website host. Only branch-specific settings for `main--peso-webapp.netlify.app` may connect
the test site to Student and peso-staging after acceptance. Production Netlify
settings and production hosting remain unchanged. A paid production environment
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
- The unrelated `peso-analysis-worker` in `peso-rg` is not the Student worker;
  acceptance requires a newly deployed `peso-student-analysis-worker` in the
  fixed Student group.
- The existing Central US managed environment is not shared because a managed
  environment is a network and logging boundary for its contained apps.
