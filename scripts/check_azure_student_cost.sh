#!/usr/bin/env bash
set -euo pipefail

resource_group="${AZURE_RESOURCE_GROUP:-peso-student-centralus-rg}"
worker_name="${AZURE_WORKER_NAME:-peso-student-analysis-worker}"
api_name="${AZURE_API_NAME:-peso-student-api}"
workspace_name="${AZURE_LOG_WORKSPACE_NAME:-peso-student-logs}"
subscription_id="$(az account show --query id --output tsv)"
scope="/subscriptions/${subscription_id}/resourceGroups/${resource_group}"

cost_body='{"type":"Usage","timeframe":"MonthToDate","dataset":{"granularity":"None","aggregation":{"totalCost":{"name":"PreTaxCost","function":"Sum"}}}}'
cost_json="$(az rest \
  --method post \
  --uri "${scope}/providers/Microsoft.CostManagement/query?api-version=2025-03-01" \
  --body "$cost_body" \
  --output json)"

cost_values="$(COST_JSON="$cost_json" node <<'NODE'
const result = JSON.parse(process.env.COST_JSON);
const columns = result.properties?.columns ?? [];
const row = result.properties?.rows?.[0] ?? [];
const indexOf = (name) => columns.findIndex((column) => column.name === name);
const costIndex = indexOf('PreTaxCost');
const currencyIndex = indexOf('Currency');
const cost = costIndex >= 0 && row[costIndex] != null ? Number(row[costIndex]) : 0;
const currency = currencyIndex >= 0 && row[currencyIndex] ? row[currencyIndex] : 'USD';
process.stdout.write(`${cost.toFixed(4)}\t${currency}`);
NODE
)"
IFS=$'\t' read -r month_to_date currency <<< "$cost_values"

projection="$(node - "$month_to_date" <<'NODE'
const spend = Number(process.argv[2]);
const now = new Date();
const elapsedDays = Math.max(1, now.getUTCDate());
const daysInMonth = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0)).getUTCDate();
process.stdout.write((spend / elapsedDays * daysInMonth).toFixed(4));
NODE
)"

execution_json="$(az containerapp job execution list \
  --name "$worker_name" \
  --resource-group "$resource_group" \
  --output json)"
execution_values="$(EXECUTION_JSON="$execution_json" node <<'NODE'
const executions = JSON.parse(process.env.EXECUTION_JSON);
const now = new Date();
const monthStart = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1);
const current = executions.filter((execution) => {
  const started = execution.properties?.startTime;
  return started && Date.parse(started) >= monthStart;
});
const failures = current.filter((execution) => execution.properties?.status === 'Failed').length;
process.stdout.write(`${current.length}\t${failures}`);
NODE
)"
IFS=$'\t' read -r worker_executions worker_failures <<< "$execution_values"

api_fqdn="$(az containerapp show \
  --name "$api_name" \
  --resource-group "$resource_group" \
  --query properties.configuration.ingress.fqdn \
  --output tsv 2>/dev/null || true)"
if [[ -n "$api_fqdn" ]]; then
  api_readiness="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --max-time 75 "https://${api_fqdn}/health/ready" || true)"
else
  api_readiness="paused"
fi

restart_count="unavailable"
workspace_id="$(az monitor log-analytics workspace show \
  --resource-group "$resource_group" \
  --workspace-name "$workspace_name" \
  --query customerId \
  --output tsv 2>/dev/null || true)"
if [[ -n "$workspace_id" ]]; then
  restart_query="ContainerAppSystemLogs_CL | where TimeGenerated >= startofmonth(now()) | where ContainerAppName_s in ('${api_name}', '${worker_name}') | where Log_s has_any ('restarted', 'Restarting', 'Back-off restarting') | summarize RestartCount=count()"
  if restart_json="$(az rest \
    --method post \
    --uri "https://api.loganalytics.io/v1/workspaces/${workspace_id}/query" \
    --resource https://api.loganalytics.io \
    --body "$(node -e 'process.stdout.write(JSON.stringify({query: process.argv[1]}))' "$restart_query")" \
    --output json 2>/dev/null)"; then
    restart_count="$(RESTART_JSON="$restart_json" node <<'NODE'
const result = JSON.parse(process.env.RESTART_JSON);
process.stdout.write(String(result.tables?.[0]?.rows?.[0]?.[0] ?? 0));
NODE
)"
  fi
fi

action="none"
at_least_eight="$(node -e 'process.stdout.write(Number(process.argv[1]) >= 8 ? "true" : "false")' "$month_to_date")"
at_least_ten="$(node -e 'process.stdout.write(Number(process.argv[1]) >= 10 ? "true" : "false")' "$month_to_date")"

if [[ "$at_least_eight" == "true" ]]; then
  worker_id="$(az containerapp job show \
    --name "$worker_name" \
    --resource-group "$resource_group" \
    --query id --output tsv)"
  az resource update \
    --ids "$worker_id" \
    --api-version 2024-03-01 \
    --set 'properties.configuration.eventTriggerConfig.scale.rules[0].metadata.query=SELECT 0' \
    --output none
  az containerapp job stop \
    --name "$worker_name" \
    --resource-group "$resource_group" \
    --output none
  action="worker paused"
fi

if [[ "$at_least_ten" == "true" ]]; then
  az containerapp ingress disable \
    --name "$api_name" \
    --resource-group "$resource_group" \
    --output none
  action="worker and API ingress paused; investigation required"
fi

report="$(printf '%s\n' \
  '## Azure Student daily cost check' \
  '' \
  "- Resource group: \`${resource_group}\`" \
  "- Month-to-date spend: ${month_to_date} ${currency}" \
  "- Projected monthly spend: ${projection} ${currency}" \
  "- Worker executions this month: ${worker_executions}" \
  "- Worker failures this month: ${worker_failures}" \
  "- API readiness: ${api_readiness}" \
  "- Compute restart count this month: ${restart_count}" \
  "- Automatic action: ${action}")"

echo "$report"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  echo "$report" >> "$GITHUB_STEP_SUMMARY"
fi

if [[ "$at_least_ten" == "true" ]]; then
  echo "Student spend reached the $10 investigation threshold." >&2
  exit 1
fi
