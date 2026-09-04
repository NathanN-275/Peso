targetScope = 'resourceGroup'

@allowed(['centralus'])
param location string = 'centralus'
param netlifyTestOrigin string
@minLength(1)
param budgetContactEmails array
@description('First day of the Student credit budget period; keep stable across deployments.')
param creditBudgetStartDate string

var keyVaultName = take('peso-student-${uniqueString(subscription().id, resourceGroup().id)}', 24)

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'peso-student-runtime'
}
resource api 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: 'peso-student-api'
}

// Run this reviewed, one-time foundation with a privileged operator. The normal
// GitHub deployment identity remains unable to create role assignments.
module sourceStorage './modules/source-storage.bicep' = {
  name: 'student-private-source-storage'
  params: {
    location: location
    runtimePrincipalId: runtimeIdentity.properties.principalId
    webOrigin: netlifyTestOrigin
  }
}

module budgetAdmission './modules/budget-admission.bicep' = {
  name: 'student-credit-admission-guard'
  params: {
    location: location
    keyVaultName: keyVaultName
    apiUrl: 'https://${api.properties.configuration.ingress.fqdn}'
    contactEmails: budgetContactEmails
    budgetStartDate: creditBudgetStartDate
    failureActionGroupId: securityAlerts.outputs.actionGroupId
  }
}

module securityAlerts './modules/security-alerts.bicep' = {
  name: 'student-security-alerts'
  params: {
    location: location
    contactEmails: budgetContactEmails
  }
}

output sourceStorageAccountName string = sourceStorage.outputs.accountName
output budgetActionGroupId string = budgetAdmission.outputs.budgetActionGroupId
