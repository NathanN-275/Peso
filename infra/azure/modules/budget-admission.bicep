targetScope = 'resourceGroup'

param location string
param keyVaultName string
param apiUrl string
param contactEmails array
param budgetStartDate string
param studentCreditAmount int = 100
param failureActionGroupId string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}
resource budgetToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: 'budget-shutdown-token'
}

resource shutdown 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'peso-student-budget-admission'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      triggers: {
        budget_alert: {
          type: 'Request'
          kind: 'Http'
          inputs: {
            schema: {
              type: 'object'
            }
          }
        }
      }
      actions: {
        Read_budget_token: {
          type: 'Http'
          inputs: {
            method: 'GET'
            uri: '${vault.properties.vaultUri}secrets/budget-shutdown-token?api-version=7.4'
            authentication: {
              type: 'ManagedServiceIdentity'
              audience: 'https://${substring(environment().suffixes.keyvaultDns, 1)}'
            }
          }
          runtimeConfiguration: {
            secureData: {
              properties: ['inputs', 'outputs']
            }
          }
          runAfter: {}
        }
        Disable_uploads: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: '${apiUrl}/internal/budget-admission/disable'
            headers: {
              'X-Budget-Token': '@body(\'Read_budget_token\')?[\'value\']'
            }
            retryPolicy: {
              type: 'exponential'
              count: 6
              interval: 'PT30S'
            }
          }
          runtimeConfiguration: {
            secureData: {
              properties: ['inputs', 'outputs']
            }
          }
          runAfter: {
            Read_budget_token: ['Succeeded']
          }
        }
      }
      outputs: {}
    }
  }
}

resource tokenReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(budgetToken.id, shutdown.id, 'budget-token-reader')
  scope: budgetToken
  properties: {
    principalId: shutdown.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

resource budgetActionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'peso-student-budget-admission'
  location: 'global'
  properties: {
    groupShortName: 'peso-budget'
    enabled: true
    logicAppReceivers: [
      {
        name: 'disable-new-upload-reservations'
        resourceId: shutdown.id
        callbackUrl: listCallbackURL('${shutdown.id}/triggers/budget_alert', '2016-06-01').value
        useCommonAlertSchema: true
      }
    ]
  }
}

resource creditBudget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'peso-student-credit'
  properties: {
    amount: studentCreditAmount
    category: 'Cost'
    timeGrain: 'Annually'
    timePeriod: {
      startDate: budgetStartDate
      endDate: dateTimeAdd(budgetStartDate, 'P1Y')
    }
    notifications: {
      credit50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      credit75: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 75
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      credit90: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 90
        thresholdType: 'Actual'
        contactEmails: contactEmails
        contactGroups: [budgetActionGroup.id]
      }
    }
  }
}

output budgetActionGroupId string = budgetActionGroup.id

resource shutdownFailureAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'peso-student-budget-shutdown-failed'
  location: 'global'
  properties: {
    description: 'The credit alert did not successfully disable upload admission; operator action is required.'
    severity: 1
    enabled: true
    scopes: [shutdown.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT1H'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'failed-shutdown-run'
          metricNamespace: 'Microsoft.Logic/workflows'
          metricName: 'RunsFailed'
          operator: 'GreaterThanOrEqual'
          threshold: 1
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: failureActionGroupId
      }
    ]
  }
}
