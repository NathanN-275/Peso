targetScope = 'resourceGroup'

param location string
param contactEmails array

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: 'peso-student-logs'
}

resource securityActionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'peso-student-security-operations'
  location: 'global'
  properties: {
    groupShortName: 'peso-sec'
    enabled: true
    emailReceivers: [for (email, index) in contactEmails: {
      name: 'operator-${index}'
      emailAddress: email
      useCommonAlertSchema: true
    }]
  }
}

var signals = [
  {
    name: 'auth-failures'
    query: 'ContainerAppConsoleLogs_CL | where Log_s has "Rejected authenticated request" or Log_s has "budget_webhook_auth_failure"'
    threshold: 5
  }
  {
    name: 'reservation-failures'
    query: 'ContainerAppConsoleLogs_CL | where Log_s has_any ("reservation_capacity_denial", "media_validation_rejected", "reservation_issuance_failure", "reservation_verification_failure")'
    threshold: 5
  }
  {
    name: 'unusual-upload-volume'
    query: 'ContainerAppConsoleLogs_CL | where Log_s has "reservation_issued"'
    threshold: 30
  }
  {
    name: 'job-or-cleanup-failures'
    query: 'ContainerAppConsoleLogs_CL | where Log_s has_any ("analysis_job_failure", "Storage retention cleanup did not finish", "Traceback")'
    threshold: 1
  }
]

resource alerts 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = [for signal in signals: {
  name: 'peso-student-${signal.name}'
  location: location
  kind: 'LogAlert'
  properties: {
    displayName: 'Peso Student ${signal.name}'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    scopes: [logs.id]
    criteria: {
      allOf: [
        {
          query: signal.query
          timeAggregation: 'Count'
          operator: 'GreaterThanOrEqual'
          threshold: signal.threshold
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: true
    actions: {
      actionGroups: [securityActionGroup.id]
    }
  }
}]

output actionGroupId string = securityActionGroup.id
