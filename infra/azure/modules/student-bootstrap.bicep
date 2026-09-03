targetScope = 'resourceGroup'

@allowed([
  'centralus'
])
param location string

param githubRepository string
param budgetContactEmails array
param budgetStartDate string

var contributorRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b24988ac-6180-42a0-ab88-20f7382dd24c'
)
var costManagementReaderRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '72fafb9e-0641-4937-9268-a91bfd8191a3'
)
var keyVaultSecretsOfficerRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
)
var logAnalyticsReaderRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '73c42c96-874c-492b-b04d-ab87d138a893'
)
var keyVaultSecretsUserRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)
var keyVaultName = take('peso-student-${uniqueString(subscription().id, resourceGroup().id)}', 24)

resource deploymentIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'peso-student-github-deploy'
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    purpose: 'github-oidc-deployment'
  }
}

resource githubEnvironmentCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: deploymentIdentity
  name: 'github-student-environment'
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepository}:environment:student'
  }
}

resource deploymentContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, deploymentIdentity.id, contributorRoleDefinitionId)
  properties: {
    principalId: deploymentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: contributorRoleDefinitionId
  }
}

resource deploymentCostReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, deploymentIdentity.id, costManagementReaderRoleDefinitionId)
  properties: {
    principalId: deploymentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: costManagementReaderRoleDefinitionId
  }
}

resource deploymentLogReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, deploymentIdentity.id, logAnalyticsReaderRoleDefinitionId)
  properties: {
    principalId: deploymentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: logAnalyticsReaderRoleDefinitionId
  }
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'peso-student-runtime'
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    purpose: 'container-apps-key-vault'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    purpose: 'student-backend-secrets'
  }
  properties: {
    enablePurgeProtection: true
    enableRbacAuthorization: true
    enableSoftDelete: true
    publicNetworkAccess: 'Enabled'
    sku: {
      family: 'A'
      name: 'standard'
    }
    softDeleteRetentionInDays: 30
    tenantId: tenant().tenantId
  }
}

resource deploymentSecretsAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, deploymentIdentity.id, keyVaultSecretsOfficerRoleDefinitionId)
  scope: keyVault
  properties: {
    principalId: deploymentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: keyVaultSecretsOfficerRoleDefinitionId
  }
}

resource runtimeSecretsAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, runtimeIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
  }
}

resource studentBudget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'peso-student-monthly-10-usd'
  properties: {
    amount: 10
    category: 'Cost'
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
      endDate: dateTimeAdd(budgetStartDate, 'P10Y')
    }
    notifications: {
      actualCost5: {
        contactEmails: budgetContactEmails
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
      }
      actualCost8: {
        contactEmails: budgetContactEmails
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
      }
      actualCost10: {
        contactEmails: budgetContactEmails
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
      }
    }
  }
}

output deploymentClientId string = deploymentIdentity.properties.clientId
output deploymentPrincipalId string = deploymentIdentity.properties.principalId
output runtimeIdentityName string = runtimeIdentity.name
output keyVaultName string = keyVault.name
