// Container Apps environment hosting the DRG API, dashboard and the nightly
// retraining job. All three mount the same Azure Files share, so the batch job
// publishes data / models that the two services immediately serve.
param location string
param tags object
param environmentAppName string
param baseName string
param imageTag string
param registryLoginServer string
param identityId string
param identityClientId string
param logAnalyticsCustomerId string

@secure()
param logAnalyticsKey string

@secure()
param appInsightsConnectionString string

param storageAccountName string

@secure()
param storageAccountKey string

param fileShareName string
param apiMinReplicas int = 0
param pipelineCron string = '0 2 * * *'
param latitude string
param longitude string
param carbonRegionId string
param keyVaultName string

@description('Whether an OpenWeatherMap key was stored in Key Vault. When false the apps run on the key-free Open-Meteo fallback and no secret reference is created.')
param hasOpenWeatherKey bool = false

var volumeName = 'drg-data'
var mountPath = '/app/shared'

var keyVaultSecret = {
  name: 'openweather-key'
  keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/openweather-api-key'
  identity: identityId
}
var appSecrets = concat(
  [ { name: 'appinsights-connection', value: appInsightsConnectionString } ],
  hasOpenWeatherKey ? [ keyVaultSecret ] : []
)

var baseEnv = [
  { name: 'DRG_DATA_DIR', value: '${mountPath}/data' }
  { name: 'DRG_ARTIFACT_DIR', value: '${mountPath}/artifacts' }
  { name: 'DRG_LATITUDE', value: latitude }
  { name: 'DRG_LONGITUDE', value: longitude }
  { name: 'DRG_REGION_ID', value: carbonRegionId }
  { name: 'DRG_KEY_VAULT_NAME', value: keyVaultName }
  { name: 'AZURE_CLIENT_ID', value: identityClientId }
  { name: 'DRG_AZURE_STORAGE_ACCOUNT', value: storageAccountName }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
]
var commonEnv = concat(
  baseEnv,
  hasOpenWeatherKey ? [ { name: 'DRG_OPENWEATHER_API_KEY', secretRef: 'openweather-key' } ] : []
)

resource environmentApp 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentAppName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsKey
      }
    }
    zoneRedundant: false
  }
}

// Shared read/write volume for processed data + trained models.
resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environmentApp
  name: volumeName
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

// ---------------------------------------------------------------------------
// FastAPI decision-support service
// ---------------------------------------------------------------------------
resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${baseName}-api'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentApp.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'OPTIONS']
          allowedHeaders: ['*']
        }
      }
      registries: [
        {
          server: registryLoginServer
          identity: identityId
        }
      ]
      secrets: appSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${registryLoginServer}/drg-api:${imageTag}'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: commonEnv
          volumeMounts: [
            { volumeName: volumeName, mountPath: mountPath }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 20
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      volumes: [
        { name: volumeName, storageType: 'AzureFile', storageName: volumeName }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: 5
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '40'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [envStorage]
}

// ---------------------------------------------------------------------------
// Streamlit dashboard
// ---------------------------------------------------------------------------
resource dashboard 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${baseName}-dash'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentApp.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8501
        transport: 'auto'
        allowInsecure: false
        stickySessions: {
          affinity: 'sticky'          // Streamlit keeps per-session state
        }
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
      }
      registries: [
        {
          server: registryLoginServer
          identity: identityId
        }
      ]
      secrets: appSecrets
    }
    template: {
      containers: [
        {
          name: 'dashboard'
          image: '${registryLoginServer}/drg-dashboard:${imageTag}'
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: concat(commonEnv, [
            { name: 'DRG_API_URL', value: 'https://${api.properties.configuration.ingress.fqdn}' }
          ])
          volumeMounts: [
            { volumeName: volumeName, mountPath: mountPath }
          ]
          probes: [
            {
              type: 'Readiness'
              httpGet: { path: '/_stcore/health', port: 8501 }
              initialDelaySeconds: 20
              periodSeconds: 15
            }
          ]
        }
      ]
      volumes: [
        { name: volumeName, storageType: 'AzureFile', storageName: volumeName }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
  dependsOn: [envStorage]
}

// ---------------------------------------------------------------------------
// Nightly retraining job (Container Apps Job, cron triggered)
// ---------------------------------------------------------------------------
resource pipeline 'Microsoft.App/jobs@2024-03-01' = {
  name: 'cj-${baseName}-pipeline'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environmentApp.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 7200
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: pipelineCron
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registryLoginServer
          identity: identityId
        }
      ]
      secrets: appSecrets
    }
    template: {
      containers: [
        {
          name: 'pipeline'
          image: '${registryLoginServer}/drg-pipeline:${imageTag}'
          command: ['python', '-m', 'drg.cli']
          args: ['run-all', '--force']
          resources: {
            cpu: json('2.0')
            memory: '4Gi'
          }
          env: commonEnv
          volumeMounts: [
            { volumeName: volumeName, mountPath: mountPath }
          ]
        }
      ]
      volumes: [
        { name: volumeName, storageType: 'AzureFile', storageName: volumeName }
      ]
    }
  }
  dependsOn: [envStorage]
}

output apiFqdn string = api.properties.configuration.ingress.fqdn
output dashboardFqdn string = dashboard.properties.configuration.ingress.fqdn
output environmentId string = environmentApp.id
output pipelineJobName string = pipeline.name
