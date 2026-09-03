# Cloud glossary

| Term | Meaning in Peso |
| --- | --- |
| Student environment | The single non-production Azure environment in `peso-student-centralus-rg`; never a synonym for production. |
| Consumption-only | Azure Container Apps serverless consumption capacity with no dedicated workload profile. |
| Scale to zero | The API may have zero replicas and the job zero executions while idle; the next request or queue event can cold-start compute. |
| Container App | The public FastAPI test service. |
| Container Apps job | A finite worker execution triggered by queued analysis work. |
| Managed environment | The shared Container Apps boundary that connects the API, job, and logs. |
| Runtime identity | The user-assigned managed identity used by API and worker to read Key Vault secrets. |
| Deployment identity | The user-assigned identity trusted by GitHub OIDC and scoped to the student resource group. |
| OIDC | Short-lived GitHub-to-Azure authentication; no Azure client secret is stored in GitHub. |
| Key Vault | Azure store for runtime, scaler, and GHCR credentials. |
| What-if | Azure preview showing the resource changes a Bicep deployment would make. |
| Budget alert | A Cost Management notification. It alerts only and does not shut down resources. |
| Cost guard | The separate daily workflow that records evidence and pauses student compute at the defined thresholds. |
| CORS origin | One exact scheme, hostname, and port allowed to call the public API from a browser. |
| Additive migration | A forward-compatible database change that does not drop, truncate, rename, or destructively rewrite existing data. |
