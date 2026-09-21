# Azure student staging: primary-source cost and control evidence

Research snapshot: 2026-08-27 (USD, Azure public cloud). This note separates Microsoft/KEDA public facts from read-only observations of Nathan's accounts. Retail rates are estimates before any account-specific offer, tax, discount, or credit; Azure says the Retail Prices API returns Microsoft retail prices and that signed-in pricing can vary by program or offer. [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)

## Decision summary

- The proposed Consumption-only staging resources have **$0.00 in modeled fixed monthly Azure resource charges**. Compute, requests, and logs remain usage-based. This does not mean the subscription is currently at $0: a pre-existing Basic registry and Central US workload are already present and accruing usage.
- At the 2026-08-27 West US 2 retail meters, one configured 0.25-vCPU/0.5-GiB replica costs **$0.0378 per active hour** after grants. API plus worker active concurrently cost **$0.0756 per wall-clock hour** after grants.
- The documented monthly Container Apps grants support exactly **200 combined active replica-hours** at that size, provided no idle usage or other Container Apps workloads consume the same subscription grants. Two simultaneous replicas therefore exhaust that compute envelope in 100 wall-clock hours.
- Staying at or below 200 combined active replica-hours, 2 million HTTP requests, and 5 GB of eligible Analytics Logs ingestion produces a modeled Azure charge of **$0.00/month only when those shared allowances have not already been consumed**.
- That condition is not currently met. A pre-existing 1-vCPU/2-GiB worker held one replica for approximately 46 hourly metric samples between 2026-08-25 23:00 UTC and 2026-08-27 20:00 UTC. At that allocation, the published CPU and memory grants each cover only 50 active hours. The requested 50-combined-hour staging envelope would therefore cost up to **$1.89** if no compute grant remains, before unrelated existing charges.
- Provisioning is **not yet approved by this evidence**. The Azure Student credit balance/expiry remains unknown, ownership of the pre-existing Azure workload must be resolved, and Supabase staging's Free-plan quota warning still requires usage monitoring.

## Official public facts

### Live West US 2 Container Apps retail meters

The action-time query used the official unauthenticated API with `serviceName = Azure Container Apps`, `armRegionName = westus2`, and USD. [Direct West US 2 Container Apps API result](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=serviceName%20eq%20%27Azure%20Container%20Apps%27%20and%20armRegionName%20eq%20%27westus2%27)

| Consumption meter | West US 2 retail rate | Unit | Effective date returned |
| --- | ---: | --- | --- |
| Standard vCPU Active Usage | $0.000034 | vCPU-second | 2022-06-01 |
| Standard Memory Active Usage | $0.000004 | GiB-second | 2022-06-01 |
| Standard vCPU Idle Usage | $0.000004 | vCPU-second | 2022-06-01 |
| Standard Memory Idle Usage | $0.000004 | GiB-second | 2022-06-01 |
| Standard Requests | $0.40 | 1 million requests | 2022-06-01 |

Microsoft documents that the Consumption plan bills per-second allocation and requests; the monthly grants are 180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests **per subscription**. A scaled-to-zero app has no usage charge. Jobs are charged at active rates from execution start to completion, have no usage charge while not executing, and do not incur request charges. An inactive minimum replica is billed at the reduced idle rate. [Azure Container Apps pricing and billing semantics](https://azure.microsoft.com/en-us/pricing/details/container-apps/)

At the configured 0.25 vCPU/0.5 GiB allocation:

```text
vCPU grant:   180,000 / (0.25 * 3,600) = 200 replica-hours
memory grant: 360,000 / (0.50 * 3,600) = 200 replica-hours
```

Both resource dimensions reach their grant together, so this is **200 combined replica-hours across API and worker, not 200 hours for each**. Idle usage and other Container Apps consumption in the subscription draw from the same resource grants and reduce that active envelope.

Overage arithmetic at the action-time retail meters:

| Increment after the relevant grant | Calculation | Cost |
| --- | --- | ---: |
| One active 0.25-vCPU/0.5-GiB replica-hour | `(0.25 * 3,600 * $0.000034) + (0.5 * 3,600 * $0.000004)` | **$0.0378** |
| One idle 0.25-vCPU/0.5-GiB replica-hour | `(0.25 * 3,600 * $0.000004) + (0.5 * 3,600 * $0.000004)` | **$0.0108** |
| API and worker both active for one hour | `2 * $0.0378` | **$0.0756** |
| One million additional app requests | published Standard Requests meter | **$0.40** |

The present API has `minReplicas: 0`; the worker job has `minExecutions: 0`. Their intended steady-state at no demand is therefore scaled to zero, not a paid idle minimum. Short scale-down intervals can still create metered usage, and the worker's entire execution is active usage.

### Log Analytics

The selected `PerGB2018` workspace has no creation or maintenance fee; Microsoft says it is billed for ingestion and retention. [Log Analytics workspace cost model](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-analytics-workspace-overview) The Analytics Logs pay-as-you-go tier includes the first **5 GB per billing account per month**. [Azure Monitor pricing](https://azure.microsoft.com/en-us/pricing/details/monitor/)

The action-time West US 2 retail response returns the `Analytics Logs Data Ingestion` meter at $0 for the tier beginning at 0 GB and **$2.30/GB beginning at 5 GB**. [Direct West US 2 Log Analytics API result](https://prices.azure.com/api/retail/prices?currencyCode=USD&%24filter=armRegionName%20eq%20%27westus2%27%20and%20contains%28productName%2C%20%27Log%20Analytics%27%29)

The Bicep configures **30-day workspace retention**. Microsoft documents 30 days as the default for most tables and notes that 31 days of Analytics retention are included in the ingestion price, so this configuration adds no retention overage by itself. [Manage Log Analytics retention](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure)

| Increment after allowance | Cost |
| --- | ---: |
| One additional GB of eligible Analytics Logs ingestion after the billing account's first 5 GB | **$2.30** |
| Retaining those logs for the configured 30 days | **$0 additional retention charge** |

The 5 GB benefit is billing-account-wide, not reserved for this workspace. Other eligible ingestion can consume it first.

### Fixed-charge conclusion

The modeled fixed Azure charge is **$0.00/month** because the template selects Consumption rather than a Dedicated workload profile, the Log Analytics workspace is pay-as-you-go with no creation/maintenance charge, and a user-assigned managed identity is available at no extra cost. [Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/) [Log Analytics workspace overview](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-analytics-workspace-overview) [Managed identities overview](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview)

The template also declares no Application Insights resource, Azure Container Registry, Key Vault, virtual network, private endpoint, dedicated workload profile, or other fixed-capacity service. The $0 conclusion excludes usage meters, taxes, unrelated resources, and future pricing changes.

### Azure for Students and budgets

Microsoft's public offer is **$100 of Azure credit usable within 12 months** for Azure for Students, with annual renewal available while eligible. Exhausting credit can disable the subscription/products unless the account is moved to pay-as-you-go. [Azure for Students offer](https://azure.microsoft.com/en-us/free/students/) [Azure for Students offer details](https://azure.microsoft.com/en-us/pricing/offers/ms-azr-0170p/)

That public offer does not establish Nathan's current remaining balance or expiration. Those values require an authenticated account check immediately before provisioning.

The `$1` budget in the template is an alerting control, not a spending cap. Microsoft states that resources are not affected and consumption is not stopped when a budget threshold is crossed. Cost data is typically available after 8–24 hours, budgets evaluate it every 24 hours, and notification normally follows within an hour of evaluation. [Create and manage Azure budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets)

Therefore the 50%, 80%, and 100% notifications can lag spend materially. They do not replace scale limits, the disabled-by-default deployment gate, post-benchmark cost inspection, or manual shutdown.

## Read-only account observations on 2026-08-27

These are action-time observations from authenticated Azure/Supabase CLI and dashboard reads. They are not public-plan guarantees and should be rechecked before a state-changing action.

### Azure

- The active subscription was shown as **Azure for Students** and enabled.
- West US 2 Container Apps usage reported **`ManagedEnvironmentCount` 0/1**: none currently consumed, with an account-visible limit of one. The proposed environment would consume the only currently reported slot.
- Read-only inventory found a pre-existing Central US resource group, `peso-rg`, containing Log Analytics workspace `workspace-pesorgdGSo`, managed environment `peso-env-centralus`, Basic registry `pesoappacr20260825`, public-ingress Container App `peso-api`, and always-on Container App `peso-analysis-worker`.
- `peso-api` was configured at 0.5 vCPU/1 GiB with min 0/max 10 replicas and reported zero requests in the available metric series. `peso-analysis-worker` was configured at 1 vCPU/2 GiB with min 1/max 1 and reported one average replica for approximately 46 hourly samples. Both used `BACKEND_ENV=production` and the production Netlify origin in CORS, so they must not be modified until Nathan identifies their intended role.
- The current private Netlify production deployment was read-only verified to use `https://peso-backend-3u4u.onrender.com`, not the Azure API. This narrows the conflict but does not rule out another Azure consumer, such as a native build.
- Azure Cost Management reported **$0.2837184672 USD** month-to-date. Usage records included **1.702992 Basic Registry unit-days** and **0.035140725 GB Analytics Logs ingestion**. A resource-level cost breakdown could not be refreshed because the Cost Management endpoint repeatedly returned HTTP 429.
- At the published active rates, the existing 1-vCPU/2-GiB worker costs **$0.1512 per active hour** after shared grants, or **$3.6288 per 24 hours**. Its allocation exhausts both documented compute grants after 50 active hours. The metric history therefore indicates the subscription's Container Apps compute grants are close to exhausted or already exhausted; exact billable seconds still require the authenticated credit/usage view.
- If no compute grant remains, the agreed proposed staging envelope of 50 combined active hours costs **$1.89** (`50 * $0.0378`). Its 250,000 requests and 1 GB of logs remain within their separate published allowances only if other subscription or billing-account use does not consume those allowances first. Existing registry and old-workload charges continue independently.
- No Azure resource was created by these checks.

### Supabase staging project `iseqgaewjpjcxrndibep`

- The Supabase CLI/API reported **`ACTIVE_HEALTHY`**.
- A later dashboard refresh reported **Healthy** on the `nano` compute tier with 2% CPU, 14% disk, 51% RAM, 7/60 connections, 100% request success, and no advisor issues. The earlier `Unhealthy` label was stale.
- The dashboard still reports that the **fair-use grace period ended**. This means the project can stop serving requests if the organization exhausts a Free-plan quota; it is a capacity warning, not a current health failure.
- A direct read-only database check at 2026-08-27 18:10 UTC succeeded against the writable primary, reporting 12 open connections and one active connection. The Security Advisor returned only the two expected informational notices for backend-only job tables with RLS enabled and no client policies. This confirms operational database access and agrees with the later Healthy dashboard state; it does not remove the Free-plan quota risk.
- Organization free-plan usage shown in the dashboard was **46% storage**, **17% database**, **6% egress**, and **1% cached egress**.
- The same view showed **zero MAU, Realtime, and Functions usage**.
- No Supabase setting, schema, role, or credential was changed by these checks.

## Remaining account-specific unknowns and approval gates

1. **Azure Student credit balance and expiration remain unknown.** The CLI billing balance response did not expose a credit amount; check the authenticated portal credit view immediately before provisioning and record the remaining amount and expiry date.
2. **The pre-existing Central US workload needs an ownership decision.** Its worker is consuming the shared Container Apps compute grant and will incur active-usage charges after the grant. Do not stop, disable, or delete it until Nathan confirms it is not production or otherwise authorizes the action.
3. **Exact current-month allowance reconciliation remains unavailable.** Metrics show approximately 46 hours of one 1-vCPU/2-GiB replica and Cost Management shows current charges, but the published grants do not report a direct remaining-unit balance through the checked CLI surfaces.
4. **Supabase usage must be rechecked before enablement.** The project is healthy, but the expired grace period means a Free-plan quota breach can stop requests without an additional grace window.
5. **Pricing must be refreshed at approval time.** The API snapshot is dated 2026-08-27 and can change.
6. **Nathan's explicit provisioning approval is still required** after the preceding checks; the `$1` budget must not be treated as a hard stop.

## Current Bicep/ARM resource contract

Repository sources: [`main.bicep`](../../infra/azure/staging/main.bicep), [`workloads.bicep`](../../infra/azure/staging/workloads.bicep), and [`azure-staging.yml`](../../.github/workflows/azure-staging.yml). Microsoft documents the selected 2025-01-01 shapes for [Container Apps](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/containerapps), [Container Apps jobs](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/jobs), and [managed environments](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/managedenvironments).

| Declared resource | Name / scope | Material contract |
| --- | --- | --- |
| Resource group | `rg-peso-staging-westus2` | Subscription deployment; staging-only tags; West US 2 |
| Log Analytics workspace | `log-peso-staging-westus2` | `PerGB2018`; 30-day retention; Container Apps log destination |
| Managed environment | `cae-peso-staging-westus2` | Consumption environment; no dedicated profile; no zone redundancy |
| Container App | `peso-backend-staging` | Immutable GHCR digest; 0.25 vCPU/0.5 GiB; single revision; min 0/max 1; HTTPS ingress to port 10000 only when enabled; startup/liveness `/health`, readiness `/health/ready` |
| Event-driven Container Apps job | `peso-analysis-worker-staging` | Immutable GHCR digest; 0.25 vCPU/0.5 GiB; `python -m app.jobs.analysis_worker --once`; 900-second timeout; Azure retry limit 0; maximum one trigger-created execution and one replica per execution |
| User-assigned managed identity | `id-peso-staging-deploy` | GitHub deployment identity |
| Federated identity credential | `github-main` | GitHub issuer; audience `api://AzureADTokenExchange`; subject only `repo:NathanN-275/Peso:ref:refs/heads/main` |
| Custom role definition | `Peso Staging Image Deployer` | Four Microsoft.App read/write actions only |
| Role assignments | API resource and job resource separately | Custom role is assigned at each exact resource, not the resource group |
| Cost budget | `peso-staging-monthly` | $1/month; actual-cost emails at 50%, 80%, and 100%; filtered to the staging resource group |

`enableWorkloads` defaults to `false`. In that state, API ingress is absent, the job has `maxExecutions: 0`, scaling rules are absent, and runtime secret references are not attached. The tracked Bicep contains no secret values. In enabled state it references the short pre-seeded secret names, while intentionally omitting the `configuration.secrets` collection so an update preserves their locally seeded values.

### PostgreSQL/KEDA scaler contract

Repository source: [`202608270001_add_analysis_job_scaler_signal.sql`](../../supabase/migrations/202608270001_add_analysis_job_scaler_signal.sql). Microsoft confirms Container Apps and event jobs use KEDA scalers and that event-job rules are evaluated at a polling interval to decide how many executions to create. [Azure Container Apps jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs)

When enabled, the worker polls every 30 seconds with:

```text
type: postgresql
query: SELECT public.pending_video_analysis_job_count()
targetQueryValue: 1
activationTargetQueryValue: 0
authentication: triggerParameter=connection, secretRef=scaler-db-url
minExecutions: 0
maxExecutions: 1
parallelism: 1
replicaCompletionCount: 1
```

KEDA's PostgreSQL scaler requires the query to return one numeric value, defines `targetQueryValue` as the scaling threshold, supports `activationTargetQueryValue`, and supports a full PostgreSQL connection string through the `connection` authentication parameter. [KEDA PostgreSQL scaler](https://keda.sh/docs/latest/scalers/postgresql/)

The migration satisfies that contract with an integer-returning, stable, `SECURITY DEFINER` function whose search path is fixed to `pg_catalog`. It counts only due, non-discarded `video_analysis` jobs in `queued` or `retry_wait`. The `analysis_job_scaler` role is `NOLOGIN`, `NOINHERIT`, non-superuser, cannot bypass RLS, and has all table/sequence/routine/schema privileges revoked before receiving only schema usage plus execution of this one function. `PUBLIC`, `anon`, and `authenticated` cannot execute it. Activating LOGIN and setting a generated password is intentionally a staging-only operation outside the migration; the session-pooler connection string belongs only in the worker secret `scaler-db-url`.

With `activationTargetQueryValue: 0`, a zero count is inactive and a positive count activates scaling toward the target of one. `maxExecutions: 1` limits trigger-created executions to one, while `parallelism: 1` limits each execution to one replica; application queue claiming and retry state remain authoritative.

### GitHub OIDC and deploy permissions

The workflow grants `id-token: write` only to the deploy job and uses `azure/login` with client, tenant, and subscription identifiers; it stores no client secret. Microsoft documents this user-assigned-managed-identity plus federated-credential flow for GitHub OIDC. [Authenticate Azure from GitHub Actions with OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)

The custom role allows exactly:

```text
Microsoft.App/containerApps/read
Microsoft.App/containerApps/write
Microsoft.App/jobs/read
Microsoft.App/jobs/write
```

Azure defines these as getting or creating/updating the Container App and job. The role omits delete, start/stop, execution, log-stream/exec, managed-environment, role-assignment, and `listSecrets/action` permissions. [Microsoft.App permission catalog](https://learn.microsoft.com/en-us/azure/role-based-access-control/permissions/compute#microsoftapp)

Important precision: Azure RBAC's `write` action is resource-level, not property-level. The checked-in workflow updates only `properties.template.containers[0].image` and then verifies both immutable digest references, while resource-scoped role assignments prevent access to sibling resources. The RBAC action itself can update other mutable properties of those two resources; “image-only” is therefore a workflow constraint plus review/branch protection, not a field-level guarantee enforced by Azure RBAC.
