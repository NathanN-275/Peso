targetScope = 'subscription'

@description('Azure region locked for the Peso staging environment.')
@allowed([
  'westus2'
])
param location string = 'westus2'

@description('Immutable sha256 digest for ghcr.io/nathann-275/peso-backend.')
@minLength(71)
@maxLength(71)
param imageDigest string

@description('Subscription email that receives the staging budget notifications.')
param budgetContactEmail string

@description('First day of the monthly budget period in ISO 8601 format.')
param budgetStartDate string = utcNow('yyyy-MM-01')

@description('Keep ingress and event executions disabled until secrets and release gates are ready.')
param enableWorkloads bool = false

@description('GitHub repository whose main branch may exchange an OIDC token for the deploy identity.')
param githubRepository string = 'NathanN-275/Peso'

var resourceGroupName = 'rg-peso-staging-westus2'
var imageRepository = 'ghcr.io/nathann-275/peso-backend'
var imageDeployerRoleId = guid(subscription().id, 'peso-staging-image-deployer')

resource stagingResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    environment: 'staging'
    application: 'peso'
    owner: 'nathan'
  }
}

resource imageDeployerRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: imageDeployerRoleId
  properties: {
    roleName: 'Peso Staging Image Deployer'
    description: 'Updates only the Peso staging Container App and Job resources; cannot list secrets, manage the environment, delete resources, execute jobs, or change role assignments.'
    type: 'CustomRole'
    assignableScopes: [
      subscription().id
    ]
    permissions: [
      {
        actions: [
          'Microsoft.App/containerApps/read'
          'Microsoft.App/containerApps/write'
          'Microsoft.App/jobs/read'
          'Microsoft.App/jobs/write'
        ]
        notActions: []
        dataActions: []
        notDataActions: []
      }
    ]
  }
}

module stagingWorkloads './workloads.bicep' = {
  name: 'peso-staging-workloads'
  scope: stagingResourceGroup
  params: {
    enableWorkloads: enableWorkloads
    githubRepository: githubRepository
    imageDeployerRoleDefinitionId: imageDeployerRole.id
    imageDigest: imageDigest
    imageRepository: imageRepository
    location: location
  }
}

resource stagingBudget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'peso-staging-monthly'
  properties: {
    amount: 1
    category: 'Cost'
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    filter: {
      dimensions: {
        name: 'ResourceGroupName'
        operator: 'In'
        values: [
          resourceGroupName
        ]
      }
    }
    notifications: {
      Actual_GreaterThanOrEqualTo_50_Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [
          budgetContactEmail
        ]
        contactGroups: []
        contactRoles: []
        locale: 'en-us'
      }
      Actual_GreaterThanOrEqualTo_80_Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [
          budgetContactEmail
        ]
        contactGroups: []
        contactRoles: []
        locale: 'en-us'
      }
      Actual_GreaterThanOrEqualTo_100_Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [
          budgetContactEmail
        ]
        contactGroups: []
        contactRoles: []
        locale: 'en-us'
      }
    }
  }
}

output apiFqdn string = stagingWorkloads.outputs.apiFqdn
output deployIdentityClientId string = stagingWorkloads.outputs.deployIdentityClientId
output deployIdentityPrincipalId string = stagingWorkloads.outputs.deployIdentityPrincipalId
output resourceGroupName string = stagingResourceGroup.name
output subscriptionId string = subscription().subscriptionId
output tenantId string = tenant().tenantId
