#!/usr/bin/env bash
set -euo pipefail

action="${1:-${ACTION:-}}"
resource_group="${AZURE_RESOURCE_GROUP:-peso-student-centralus-rg}"
worker_name="${AZURE_WORKER_NAME:-peso-student-analysis-worker}"
api_name="${AZURE_API_NAME:-peso-student-api}"

case "$action" in
  pause-worker|resume-worker|pause-all|resume-all) ;;
  *)
    echo "Action must be pause-worker, resume-worker, pause-all, or resume-all." >&2
    exit 2
    ;;
esac

worker_query='SELECT azure_scaler.analysis_queue_depth()'
if [[ "$action" == "pause-worker" || "$action" == "pause-all" ]]; then
  worker_query='SELECT 0'
fi

worker_id="$(az containerapp job show \
  --name "$worker_name" \
  --resource-group "$resource_group" \
  --query id --output tsv 2>/dev/null || true)"
api_id="$(az containerapp show \
  --name "$api_name" \
  --resource-group "$resource_group" \
  --query id --output tsv 2>/dev/null || true)"

if [[ -n "$worker_id" ]]; then
  az resource update \
    --ids "$worker_id" \
    --api-version 2024-03-01 \
    --set "properties.configuration.eventTriggerConfig.scale.rules[0].metadata.query=$worker_query" \
    --output none
elif [[ "$action" == "resume-worker" || "$action" == "resume-all" ]]; then
  echo "Cannot resume absent Student worker $worker_name." >&2
  exit 1
fi

if [[ -n "$worker_id" && ( "$action" == "pause-worker" || "$action" == "pause-all" ) ]]; then
  az containerapp job stop \
    --name "$worker_name" \
    --resource-group "$resource_group" \
    --output none
fi

if [[ "$action" == "pause-all" ]]; then
  if [[ -n "$api_id" ]]; then
    az containerapp ingress disable \
      --name "$api_name" \
      --resource-group "$resource_group" \
      --output none
  fi
elif [[ "$action" == "resume-all" ]]; then
  if [[ -z "$api_id" ]]; then
    echo "Cannot resume absent Student API $api_name." >&2
    exit 1
  fi
  az containerapp ingress enable \
    --name "$api_name" \
    --resource-group "$resource_group" \
    --type external \
    --target-port 10000 \
    --transport http \
    --allow-insecure false \
    --output none
fi

actual_query="resource absent"
if [[ -n "$worker_id" ]]; then
  actual_query="$(az containerapp job show \
    --name "$worker_name" \
    --resource-group "$resource_group" \
    --query 'properties.configuration.eventTriggerConfig.scale.rules[0].metadata.query' \
    --output tsv)"
fi
if [[ -n "$worker_id" && "$actual_query" != "$worker_query" ]]; then
  echo "Worker trigger update did not persist." >&2
  exit 1
fi

active_worker_executions="0"
if [[ -n "$worker_id" ]]; then
  active_worker_executions="$(az containerapp job execution list \
    --name "$worker_name" \
    --resource-group "$resource_group" \
    --query "[?properties.status=='Running'] | length(@)" \
    --output tsv)"
fi

if [[ -n "$worker_id" && ( "$action" == "pause-worker" || "$action" == "pause-all" ) ]]; then
  for attempt in {1..12}; do
    active_worker_executions="$(az containerapp job execution list \
      --name "$worker_name" \
      --resource-group "$resource_group" \
      --query "[?properties.status=='Running'] | length(@)" \
      --output tsv)"
    [[ "$active_worker_executions" == "0" ]] && break
    sleep 10
  done
  if [[ "$active_worker_executions" != "0" ]]; then
    echo "Student worker still has $active_worker_executions running execution(s)." >&2
    exit 1
  fi
fi

api_ingress_fqdn=""
if [[ -n "$api_id" ]]; then
  api_ingress_fqdn="$(az containerapp show \
    --name "$api_name" \
    --resource-group "$resource_group" \
    --query properties.configuration.ingress.fqdn \
    --output tsv)"
fi

count_api_replicas() {
  local total=0
  local count
  while IFS= read -r revision; do
    [[ -z "$revision" ]] && continue
    count="$(az containerapp replica list \
      --name "$api_name" \
      --resource-group "$resource_group" \
      --revision "$revision" \
      --query 'length(@)' \
      --output tsv)"
    total=$((total + count))
  done < <(az containerapp revision list \
    --name "$api_name" \
    --resource-group "$resource_group" \
    --query '[?properties.active].name' \
    --output tsv 2>/dev/null || true)
  echo "$total"
}

api_replicas="$(count_api_replicas)"
if [[ "$action" == "pause-all" ]]; then
  if [[ -n "$api_ingress_fqdn" ]]; then
    echo "Student API ingress is still configured." >&2
    exit 1
  fi
  for attempt in {1..30}; do
    api_replicas="$(count_api_replicas)"
    [[ "$api_replicas" == "0" ]] && break
    sleep 10
  done
  if [[ "$api_replicas" != "0" ]]; then
    echo "Student API still has $api_replicas replica(s)." >&2
    exit 1
  fi
fi

report="$(printf '%s\n' \
  '## Azure Student compute control' \
  '' \
  "- Action: ${action}" \
  "- Resource group: \`${resource_group}\`" \
  "- API: \`${api_name}\`" \
  "- Worker: \`${worker_name}\`" \
  "- API resource present: $([[ -n "$api_id" ]] && echo true || echo false)" \
  "- Worker resource present: $([[ -n "$worker_id" ]] && echo true || echo false)" \
  "- API ingress configured: $([[ -n "$api_ingress_fqdn" ]] && echo yes || echo no)" \
  "- API replicas: ${api_replicas}" \
  "- Worker active executions: ${active_worker_executions}" \
  "- Worker scaler query: \`${actual_query}\`")"

echo "$report"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  echo "$report" >> "$GITHUB_STEP_SUMMARY"
fi
