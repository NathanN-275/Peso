# Azure Student infrastructure

This directory defines one isolated, non-production Azure environment:
`peso-student-centralus-rg` in Central US. It deliberately contains no
production environment, dedicated Container Apps workload profile, VNet,
registry, website hosting, or resource reference to `peso-rg`.

`bootstrap.bicep` is a one-time subscription-scope deployment. It creates the
student resource group, a runtime identity, a GitHub deployment identity with a
federated credential for the protected `student` GitHub environment, Key Vault,
resource-group-scoped roles, and the $10 monthly budget. Run it from an Azure
owner session because creating role assignments is intentionally outside the
GitHub deployment identity's authority.

`student.bicep` is the repeatable resource-group deployment. It creates the
Consumption-only Container Apps environment, Log Analytics workspace, public
scale-to-zero API, and event-triggered worker job. The worker is fixed at 0.25
vCPU/0.5 GiB, permits zero idle and one concurrent execution, and times out at
900 seconds.

Build locally without deploying:

```bash
az bicep build --file infra/azure/bootstrap.bicep
az bicep build --file infra/azure/student.bicep
npm run test:policy
```

Never pass runtime or GHCR secret values as Bicep parameters. The deployment
workflow writes them to Key Vault first and `student.bicep` references those
secret URIs through the runtime managed identity. Run resource-group `what-if`
and retain its JSON artifact before every deployment.

The full operator sequence, required GitHub values, testing, cost controls, and
legacy-resource approval gate are in
`docs/deployment/azure-student-setup.md`.
