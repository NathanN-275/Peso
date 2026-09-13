# Azure Student release evidence

Copy this checklist for each Student deployment and replace every `TBD`. A
deployment is not accepted while any required item remains `TBD`.

## Scope and identity

| Evidence | Value |
| --- | --- |
| Commit SHA | TBD |
| Immutable GHCR digest | TBD |
| Subscription ID (Azure Students only) | TBD |
| Resource group ID (`peso-student-centralus-rg`) | TBD |
| Legacy group name/location retained; no bootstrap recreation or deletion | TBD |
| Workload region is West US 3 (`westus3`) | TBD |
| Subscription location check confirms `westus3` is allowed | TBD |
| GitHub run and protected `student` environment | TBD |
| OIDC federated subject | TBD |
| Deployment role assignments scoped to Student RG/Key Vault | TBD |
| Confirmation that GitHub has no Azure client secret | TBD |

## Preview and configuration

| Evidence | Value |
| --- | --- |
| Bicep build output | TBD |
| Policy-test output | TBD |
| Resource-group what-if artifact | TBD |
| What-if contains only `peso-student-centralus-rg` IDs | TBD |
| What-if creates `peso-student-westus3-cae` as a Student-owned environment | TBD |
| What-if contains no `peso-rg` reference, modification, or deletion | TBD |
| Key Vault RBAC query | TBD |
| Exact non-production Netlify CORS origin | TBD |
| Unknown-origin CORS rejection | TBD |
| $10 budget query | TBD |
| $5/$8/$10 alert query | TBD |

## Supabase isolation

| Evidence | Value |
| --- | --- |
| Permanent project | peso-staging (`iseqgaewjpjcxrndibep`) |
| Production exclusion | PesoDatabase (`jfgiydtrskpqxyorvvbc`) never receives Student writes |
| Remote vs repository migration history comparison | TBD |
| Every migration dry-run and reviewer | TBD |
| Existing staging data preserved | TBD |
| Student URL, public key, runtime key and scaler identity verified | TBD |
| Auth redirect and private storage configuration | TBD |
| Applied migration list | TBD |
| Security advisor/RLS review | TBD |
| Test user A ID and cleanup result | TBD |
| Test user B ID and cleanup result | TBD |
| Cross-owner access rejection | TBD |

## Runtime acceptance

| Evidence | Value |
| --- | --- |
| Full application Trivy scan: zero HIGH/CRITICAL, unfixed included | TBD |
| Offline UID 10001 inference, imports, media and export checks | TBD |
| Published image security artifact (digest + raw Trivy JSON) | TBD |
| Reviewed real squat old/new comparison (not synthetic fixtures) | TBD |
| Branch main Netlify configuration and production unchanged | TBD |
| `/health/ready` response | TBD |
| API hostname matches `peso-student-api.*.westus3.azurecontainerapps.io` | TBD |
| `peso-student-analysis-worker` exists in the Student group with Event trigger enabled | TBD |
| Pause/resume worker control restores the event scaler query | TBD |
| `peso-analysis-worker` in `peso-rg` remains unchanged and out of scope | TBD |
| Signup-through-deletion test, user A | TBD |
| Signup-through-deletion test, user B | TBD |
| Longest accepted clip run 1: start latency/duration/peak memory/restarts | TBD |
| Longest accepted clip run 2: start latency/duration/peak memory/restarts | TBD |
| API scales to zero | TBD |
| Worker returns to zero executions | TBD |
| Daily cost artifact: spend/projection/executions/readiness/failures/restarts | TBD |

Both long-clip runs require start within 60 seconds, completion under 600
seconds, peak memory below 400 MiB (80% of 0.5 GiB), and zero restarts.

## Legacy resource deletion gate

`peso-analysis-worker` in `peso-rg` is out of scope for the regional move. It is
not the Student worker and must not be used as evidence that
`peso-student-analysis-worker` was deployed successfully.

Do not fill this section until every acceptance item above passes. Inventory the
old group without deleting anything:

```bash
az resource list --resource-group peso-rg --query "[].id" --output tsv
```

Paste every exact ID below, describe its replacement and rollback dependency,
and request separate deletion approval. This evidence file is not deletion
authorization.

| Existing `peso-rg` resource ID | Replacement verified | Rollback dependency | Delete approved by/date |
| --- | --- | --- | --- |
| TBD | TBD | TBD | TBD |
