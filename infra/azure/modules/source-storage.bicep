targetScope = 'resourceGroup'

param location string
param runtimePrincipalId string
param webOrigin string

var storageName = take('pesosource${uniqueString(subscription().id, resourceGroup().id)}', 24)
var blobContributorRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var blobDelegatorRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a')

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // Exact-blob SAS uploads need a reachable data endpoint. No anonymous or
    // shared-key access is permitted; the API authenticates every reservation.
    publicNetworkAccess: 'Enabled'
    encryption: {
      keySource: 'Microsoft.Storage'
      services: {
        blob: {
          enabled: true
          keyType: 'Account'
        }
        queue: {
          enabled: true
          keyType: 'Account'
        }
      }
    }
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: false
    deleteRetentionPolicy: {
      enabled: false
    }
    containerDeleteRetentionPolicy: {
      enabled: false
    }
    cors: {
      corsRules: [
        {
          allowedOrigins: [webOrigin]
          allowedMethods: ['PUT', 'GET', 'HEAD']
          allowedHeaders: ['content-type', 'x-ms-blob-type', 'if-none-match', 'range']
          exposedHeaders: ['content-length', 'content-range', 'content-type', 'etag']
          maxAgeInSeconds: 300
        }
      ]
    }
  }
}

resource sources 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'source-videos'
  properties: {
    publicAccess: 'None'
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

// Postgres remains the authoritative, transactionally admitted job queue. This
// private queue is reserved for operational dead-letter notifications, not for
// bypassing database verification or admission.
resource operationalQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = {
  parent: queueService
  name: 'media-security-events'
}

resource sourceDataAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sources.id, runtimePrincipalId, blobContributorRole)
  scope: sources
  properties: {
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: blobContributorRole
  }
}

resource sourceDelegation 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, runtimePrincipalId, blobDelegatorRole)
  scope: storage
  properties: {
    principalId: runtimePrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: blobDelegatorRole
  }
}

output accountUrl string = storage.properties.primaryEndpoints.blob
output accountName string = storage.name
output sourceContainerName string = sources.name
output storageResourceId string = storage.id
