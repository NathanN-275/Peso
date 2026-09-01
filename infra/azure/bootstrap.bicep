targetScope = 'subscription'

@description('The only Azure region approved for the Student environment.')
@allowed([
  'centralus'
])
param location string = 'centralus'

@description('GitHub owner/repository used in the student environment OIDC subject.')
param githubRepository string

@description('Email addresses that receive student resource-group budget alerts.')
@minLength(1)
param budgetContactEmails array

@description('First day of the current Azure billing month.')
param budgetStartDate string = utcNow('yyyy-MM-01')

var resourceGroupName = 'peso-student-centralus-rg'

resource studentResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    region: location
    managedBy: 'bicep'
    production: 'false'
  }
}

module studentBootstrap './modules/student-bootstrap.bicep' = {
  name: 'student-bootstrap'
  scope: studentResourceGroup
  params: {
    location: location
    githubRepository: githubRepository
    budgetContactEmails: budgetContactEmails
    budgetStartDate: budgetStartDate
  }
}

output resourceGroupName string = studentResourceGroup.name
output resourceGroupId string = studentResourceGroup.id
output deploymentClientId string = studentBootstrap.outputs.deploymentClientId
output deploymentPrincipalId string = studentBootstrap.outputs.deploymentPrincipalId
output runtimeIdentityName string = studentBootstrap.outputs.runtimeIdentityName
output keyVaultName string = studentBootstrap.outputs.keyVaultName
