#!/usr/bin/env bash
set -euo pipefail

resource_group="${AZURE_RESOURCE_GROUP:-peso-student-centralus-rg}"
subscription_id="$(az account show --query id --output tsv)"
scope="/subscriptions/${subscription_id}/resourceGroups/${resource_group}"
budget_uri="${scope}/providers/Microsoft.Consumption/budgets/peso-student-monthly-10-usd?api-version=2023-11-01"
budget_json="$(az rest --method get --uri "$budget_uri" --output json)"

BUDGET_JSON="$budget_json" node <<'NODE'
const budget = JSON.parse(process.env.BUDGET_JSON);
if (budget.properties?.amount !== 10 || budget.properties?.timeGrain !== 'Monthly') {
  throw new Error('Expected a $10 monthly resource-group budget.');
}

const notifications = Object.values(budget.properties?.notifications ?? {});
const thresholds = notifications
  .filter((notification) => notification.enabled && notification.thresholdType === 'Actual')
  .map((notification) => notification.threshold)
  .sort((left, right) => left - right);

if (JSON.stringify(thresholds) !== JSON.stringify([50, 80, 100])) {
  throw new Error(`Expected enabled actual-cost thresholds 50,80,100; received ${thresholds}.`);
}
NODE

echo "Verified the $10 monthly budget and $5/$8/$10 actual-cost alerts for $scope."
