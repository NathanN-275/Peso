# ADR 0014: Move Student workloads to West US 3

## Status

Accepted as the placement rule for any future Student compute resume. ADR 0015
pauses those workloads and supersedes their active frontend binding.

## Context

The Student bootstrap already exists as `peso-student-centralus-rg` with its
managed identities, Key Vault, GitHub OIDC credential, scoped role assignments,
and budget. A live Azure quota check found zero of zero usable Container Apps
managed-environment capacity in Central US. West US 3 is both explicitly allowed
for this subscription and supported by Azure Container Apps.

An older managed environment exists in `peso-rg`, but reusing it would join the
Student API and jobs to a network and Log Analytics boundary owned by unrelated
legacy resources. That conflicts with the Student isolation policy. Azure
documents the managed environment as the secure boundary around a group of
Container Apps and jobs; see [Azure Container Apps environments](https://learn.microsoft.com/en-us/azure/container-apps/environment).

## Decision

Deploy the Student workload resources in West US 3 (`westus3`):

- the Student-owned `peso-student-westus3-cae` managed environment;
- `peso-student-api`;
- `peso-student-analysis-worker` and optional cleanup jobs;
- the Student Log Analytics workspace; and
- future source storage and related security-foundation resources.

Keep the deployment scope fixed to `peso-student-centralus-rg`. Its name and
location are legacy bootstrap metadata and do not determine the location of
resources inside it. Keep the existing identities, Key Vault, OIDC credential,
role assignments, and budget unchanged. No Central US Student bootstrap
resource is deleted or recreated as part of this move.

Do not reuse, modify, or delete `peso-rg`. In particular,
`peso-analysis-worker` in that group remains out of scope. It is not a substitute
for the intended `peso-student-analysis-worker`, which is currently absent and
must be confirmed in the Student group after the first successful deployment.

Accept frontend release bindings only when the API hostname matches
`peso-student-api.*.westus3.azurecontainerapps.io` and all other existing
binding evidence checks pass.

## Consequences

- The first reviewed deployment must create a new isolated managed environment
  rather than attach workloads to an existing environment.
- Operators must distinguish the fixed group scope from workload region when
  reading Azure inventory and deployment evidence.
- What-if review must show only resources in the fixed Student group, must
  create `peso-student-westus3-cae`, and must contain no `peso-rg` changes.
- Cross-region access from West US 3 workloads to the retained Central US Key
  Vault and identities is intentional; availability, latency, and cost remain
  part of Student acceptance.
- After deployment, readiness/CORS, the Student worker Event trigger, generated
  release binding, and pause/resume controls must all be verified.
