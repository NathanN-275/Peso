# Cloud glossary

| Term | Meaning in Peso |
| --- | --- |
| Public marketing launch | Information-only public website at `/`, `/beta`, `/privacy`, and `/terms`; no signup, uploads, analysis, or email collection. It does not approve the public beta. |
| Marketing hosting project | Dedicated `peso-marketing` Netlify project for marketing-only artifacts; production may become public after acceptance, while previews remain private. |
| Private app hosting project | Existing `peso-webapp` Netlify project, including staging, previews, and historical deploys; stays private with production builds skipped until a separate beta release. |
| Production backend freeze | Live Render auto-deploy off, with its deploy ID and commit retained; no backend deployment, migration, credential change, or service resumption during marketing launch. |
| Public beta launch | Separate release enabling authenticated side-view squat analysis only after every full-beta operational and acceptance gate passes. |
| Student environment | The single non-production Azure environment whose West US 3 workloads live in the legacy-named `peso-student-centralus-rg`; never a synonym for production. |
| Student compute pause | Reversible suspension of only the Student API and worker: API ingress disabled, worker scaler set to `SELECT 0`, active worker executions stopped, and compute verified at zero. It retains Azure infrastructure and does not guarantee a literal $0 bill. |
| Render beta | The isolated non-production pair `peso-beta-api` and `peso-beta-analysis-worker`, backed only by `peso-staging` and the private Netlify `main` branch; never a synonym for the production Render services. |
| Student bootstrap | The retained Central US resource group, identities, Key Vault, OIDC identity, and budget. The group name/location are legacy metadata and do not define the workload region. |
| Student workload region | West US 3 (`westus3`), including the Student-owned Container Apps environment, API, jobs, logs, and future security-foundation resources. |
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
| Budget alert | A Cost Management notification. The 90% Student-credit alert invokes the admission-shutdown workflow; alerts are delayed and are not a hard spending cap. |
| Cost guard | The separate daily workflow that records evidence and pauses student compute at the defined thresholds. |
| CORS origin | One exact scheme, hostname, and port allowed to call the public API from a browser. |
| Additive migration | A forward-compatible database change that does not drop, truncate, rename, or destructively rewrite existing data. |
| Upload Reservation | The owner-bound capacity allocation made before a source-video upload is authorized. |
| Verified Upload | A source video accepted after the server checks its actual bytes, format, duration, dimensions, frame rate, and frame count. |
| Media Validation Job | The bounded verification work performed by upload completion before analysis admission. |
| Create-only SAS | A short-lived, HTTPS-only capability for one new blob; it grants no read, list, delete, or overwrite permission. |
| Admission shutdown | A persistent refusal of new Upload Reservations; existing processing and owner-checked retrieval remain available. |
