targetScope = 'resourceGroup'

param location string
param imageRepository string
param imageDigest string
param enableWorkloads bool
param githubRepository string
param imageDeployerRoleDefinitionId string

var logWorkspaceName = 'log-peso-staging-westus2'
var containerEnvironmentName = 'cae-peso-staging-westus2'
var apiName = 'peso-backend-staging'
var workerJobName = 'peso-analysis-worker-staging'
var deployIdentityName = 'id-peso-staging-deploy'
var imageReference = '${imageRepository}@${imageDigest}'

var sharedEnvironment = [
  {
    name: 'BACKEND_ENV'
    value: 'production'
  }
  {
    name: 'BACKEND_CORS_ORIGINS'
    value: 'https://main--peso-webapp.netlify.app'
  }
  {
    name: 'BACKEND_CORS_ALLOW_PRIVATE_NETWORK'
    value: 'false'
  }
  {
    name: 'VIDEO_BUCKET'
    value: 'videos'
  }
  {
    name: 'MAX_USER_IN_PROGRESS_VIDEOS'
    value: '3'
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

var runtimeSecretEnvironment = [
  {
    name: 'SUPABASE_URL'
    secretRef: 'sb-url'
  }
  {
    name: 'SUPABASE_SERVICE_ROLE_KEY'
    secretRef: 'sb-service'
  }
  {
    name: 'SUPABASE_JWT_SECRET'
    secretRef: 'sb-jwt'
  }
  {
    name: 'CLEANUP_JOB_TOKEN'
    secretRef: 'cleanup-token'
  }
]

var workerEnvironment = concat(sharedEnvironment, [
  {
    name: 'ANALYSIS_WORKER_LEASE_SECONDS'
    value: '3600'
  }
  {
    name: 'ANALYSIS_WORKER_POLL_SECONDS'
    value: '2'
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
], enableWorkloads ? runtimeSecretEnvironment : [])

resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
    workspaceCapping: {
      dailyQuotaGb: -1
    }
  }
}

resource containerEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: containerEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: deployIdentityName
  location: location
}

resource githubMainCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: deployIdentity
  name: 'github-main'
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepository}:ref:refs/heads/main'
  }
}

resource api 'Microsoft.App/containerApps@2025-01-01' = {
  name: apiName
  location: location
  properties: {
    managedEnvironmentId: containerEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: enableWorkloads ? {
        allowInsecure: false
        external: true
        targetPort: 10000
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
        transport: 'auto'
      } : null
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imageReference
          env: concat(sharedEnvironment, enableWorkloads ? runtimeSecretEnvironment : [])
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 10000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 1
              periodSeconds: 5
              failureThreshold: 30
              successThreshold: 1
              timeoutSeconds: 2
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 10000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 20
              failureThreshold: 3
              successThreshold: 1
              timeoutSeconds: 2
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
              failureThreshold: 3
              successThreshold: 1
              timeoutSeconds: 5
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
        rules: []
      }
    }
  }
}

resource workerJob 'Microsoft.App/jobs@2025-01-01' = {
  name: workerJobName
  location: location
  properties: {
    environmentId: containerEnvironment.id
    configuration: {
      triggerType: 'Event'
      replicaTimeout: 900
      replicaRetryLimit: 0
      eventTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
        scale: {
          pollingInterval: 30
          minExecutions: 0
          maxExecutions: enableWorkloads ? 1 : 0
          rules: enableWorkloads ? [
            {
              name: 'pending-video-analysis'
              type: 'postgresql'
              metadata: {
                query: 'SELECT public.pending_video_analysis_job_count()'
                targetQueryValue: '1'
                activationTargetQueryValue: '0'
              }
              auth: [
                {
                  secretRef: 'scaler-db-url'
                  triggerParameter: 'connection'
                }
              ]
            }
          ] : []
        }
      }
    }
    template: {
      containers: [
        {
          name: 'analysis-worker'
          image: imageReference
          command: [
            'python'
            '-m'
            'app.jobs.analysis_worker'
            '--once'
          ]
          env: workerEnvironment
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}

resource apiImageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(api.id, deployIdentity.id, imageDeployerRoleDefinitionId)
  scope: api
  properties: {
    description: 'Allow the GitHub OIDC identity to update only the staging API resource.'
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: imageDeployerRoleDefinitionId
  }
}

resource workerImageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(workerJob.id, deployIdentity.id, imageDeployerRoleDefinitionId)
  scope: workerJob
  properties: {
    description: 'Allow the GitHub OIDC identity to update only the staging worker job resource.'
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: imageDeployerRoleDefinitionId
  }
}

output apiFqdn string = enableWorkloads ? api.properties.configuration.ingress.fqdn : ''
output deployIdentityClientId string = deployIdentity.properties.clientId
output deployIdentityPrincipalId string = deployIdentity.properties.principalId
