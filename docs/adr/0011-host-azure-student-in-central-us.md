# ADR 0011: Host the Azure Student environment in Central US

## Status

Accepted

## Decision

Use Central US (`centralus`) for the single Azure Student environment because
the Azure Students subscription currently has Container Apps Consumption quota
there. Do not create dedicated workload profiles, a second Azure environment,
a VNet, or production compute under this decision.

The resource group is fixed as `peso-student-centralus-rg`. Existing resources
in `peso-rg` remain unchanged until the Student replacement passes its complete
acceptance suite and their exact resource IDs receive separate deletion
approval.

## Consequences

- Region and resource-group names are policy-tested rather than workflow
  inputs, which prevents an accidental deployment into `peso-rg`.
- A future paid production environment needs a new ADR and infrastructure path;
  it is not an expansion of Student.
- Region migration requires a reviewed ADR update and replacement deployment.
