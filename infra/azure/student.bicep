targetScope = 'resourceGroup'

@description('The only Azure region approved for the Student environment.')
@allowed([
  'centralus'
])
param location string = 'centralus'

@description('Immutable GHCR image reference including @sha256:<64 lowercase hex characters>.')
param imageReference string

@description('GHCR username that can read the image package.')
param ghcrUsername string

@description('Exact HTTPS origin of the staging/test Netlify deploy. No wildcard or production origin is accepted by policy.')
param netlifyTestOrigin string

var keyVaultName = take('peso-student-${uniqueString(subscription().id, resourceGroup().id)}', 24)
var runtimeIdentityName = 'peso-student-runtime'
var commonEnvironmentVariables = [
  {
    name: 'BACKEND_ENV'
    value: 'production'
  }
  {
    name: 'BACKEND_CORS_ORIGINS'
    value: netlifyTestOrigin
  }
  {
    name: 'BACKEND_CORS_ALLOW_PRIVATE_NETWORK'
    value: 'false'
  }
  {
    name: 'SUPABASE_URL'
    secretRef: 'supabase-url'
  }
  {
    name: 'SUPABASE_SERVICE_ROLE_KEY'
    secretRef: 'supabase-service-role-key'
  }
  {
    name: 'SUPABASE_JWT_SECRET'
    secretRef: 'supabase-jwt-secret'
  }
  {
    name: 'CLEANUP_JOB_TOKEN'
    secretRef: 'cleanup-job-token'
  }
  {
    name: 'VIDEO_BUCKET'
    value: 'videos'
  }
  {
    name: 'MAX_USER_IN_PROGRESS_VIDEOS'
    value: '2'
  }
  {
    name: 'ANALYSIS_PROFILE_MODE'
    value: 'legacy'
  }
  {
    name: 'ANALYSIS_TRACE_ENABLED'
    value: 'false'
  }
]

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: runtimeIdentityName
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'peso-student-logs'
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    production: 'false'
  }
  properties: {
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
    workspaceCapping: {
      dailyQuotaGb: json('0.25')
    }
  }
}

// No dedicated profile is declared, so this remains a Consumption-only environment.
resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'peso-student-centralus-cae'
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    region: location
    production: 'false'
  }
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'peso-student-api'
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    imageDigest: last(split(imageReference, '@'))
    production: 'false'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runtimeIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 10000
        transport: 'http'
      }
      registries: [
        {
          passwordSecretRef: 'ghcr-token'
          server: 'ghcr.io'
          username: ghcrUsername
        }
      ]
      secrets: [
        {
          name: 'ghcr-token'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/ghcr-token'
          identity: runtimeIdentity.id
        }
        {
          name: 'supabase-url'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-url'
          identity: runtimeIdentity.id
        }
        {
          name: 'supabase-service-role-key'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-service-role-key'
          identity: runtimeIdentity.id
        }
        {
          name: 'supabase-jwt-secret'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-jwt-secret'
          identity: runtimeIdentity.id
        }
        {
          name: 'cleanup-job-token'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/cleanup-job-token'
          identity: runtimeIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imageReference
          env: commonEnvironmentVariables
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 10000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 10000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
              successThreshold: 1
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

resource worker 'Microsoft.App/jobs@2024-03-01' = {
  name: 'peso-student-analysis-worker'
  location: location
  tags: {
    application: 'peso'
    environment: 'student'
    imageDigest: last(split(imageReference, '@'))
    production: 'false'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runtimeIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    configuration: {
      triggerType: 'Event'
      replicaRetryLimit: 0
      replicaTimeout: 900
      eventTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
        scale: {
          minExecutions: 0
          maxExecutions: 1
          pollingInterval: 30
          rules: [
            {
              name: 'supabase-analysis-queue'
              type: 'postgresql'
              metadata: {
                activationTargetQueryValue: '0'
                connectionFromEnv: 'AZURE_SCALER_POSTGRES_CONNECTION'
                query: 'SELECT azure_scaler.analysis_queue_depth()'
                targetQueryValue: '1'
              }
            }
          ]
        }
      }
      registries: [
        {
          passwordSecretRef: 'ghcr-token'
          server: 'ghcr.io'
          username: ghcrUsername
        }
      ]
      secrets: [
        {
          name: 'ghcr-token'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/ghcr-token'
          identity: runtimeIdentity.id
        }
        {
          name: 'supabase-url'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-url'
          identity: runtimeIdentity.id
        }
        {
          name: 'supabase-service-role-key'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-service-role-key'
          identity: runtimeIdentity.id
        }
        {
          name: 'supabase-jwt-secret'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/supabase-jwt-secret'
          identity: runtimeIdentity.id
        }
        {
          name: 'cleanup-job-token'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/cleanup-job-token'
          identity: runtimeIdentity.id
        }
        {
          name: 'scaler-postgres-connection'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/scaler-postgres-connection'
          identity: runtimeIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'analysis-worker'
          image: imageReference
          command: [
            'python'
          ]
          args: [
            '-m'
            'app.jobs.analysis_worker'
            '--once'
          ]
          env: concat(commonEnvironmentVariables, [
            {
              name: 'AZURE_SCALER_POSTGRES_CONNECTION'
              secretRef: 'scaler-postgres-connection'
            }
            {
              name: 'ANALYSIS_WORKER_LEASE_SECONDS'
              value: '900'
            }
            {
              name: 'ANALYSIS_WORKER_RECOVERY_SECONDS'
              value: '60'
            }
            {
              name: 'ANALYSIS_NORMAL_TIMEOUT_SECONDS'
              value: '180'
            }
            {
              name: 'ANALYSIS_MAX_TIMEOUT_SECONDS'
              value: '600'
            }
            {
              name: 'ANALYSIS_LONG_CLIP_TIMEOUT_MULTIPLIER'
              value: '3'
            }
          ])
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}

output apiHostname string = api.properties.configuration.ingress.fqdn
output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output apiResourceId string = api.id
output workerName string = worker.name
output workerResourceId string = worker.id
output containerAppsEnvironmentResourceId string = containerAppsEnvironment.id
output logAnalyticsResourceId string = logs.id
output runtimeIdentityResourceId string = runtimeIdentity.id
output keyVaultResourceId string = keyVault.id
