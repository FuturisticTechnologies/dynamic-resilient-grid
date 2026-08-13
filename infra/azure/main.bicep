// ===========================================================================
// Dynamic Resilient Grid (DRG) -- Azure reference architecture
//
//   Container Registry  -> holds the api / dashboard / pipeline images
//   Storage (ADLS Gen2) -> raw + processed smart-meter data, model artifacts
//   Key Vault           -> OpenWeatherMap key and any other secret
//   Log Analytics + App Insights -> logs, traces, metrics
//   Container Apps Env  -> serverless hosting with scale-to-zero
//     - drg-api         -> FastAPI decision-support service (public)
//     - drg-dashboard   -> Streamlit dashboard (public)
//     - drg-pipeline    -> scheduled Container Apps Job (nightly retrain)
//   Azure ML workspace  -> optional managed training + model registry
//
// Deploy:
//   az group create -n rg-drg-dev -l uksouth
//   az deployment group create -g rg-drg-dev -f infra/azure/main.bicep \
//      -p infra/azure/main.parameters.json
// ===========================================================================

targetScope = 'resourceGroup'

@description('Short name used to derive every resource name (3-11 chars).')
@minLength(3)
@maxLength(11)
param namePrefix string = 'drg'

@description('Deployment environment tag and name suffix.')
@allowed(['dev', 'test', 'prod'])
param environmentName string = 'dev'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Container image tag to deploy (e.g. a git SHA).')
param imageTag string = 'latest'

@description('Deploy the Azure Machine Learning workspace for managed training.')
param deployMachineLearning bool = true

@description('OpenWeatherMap API key. Leave empty to rely on the key-free Open-Meteo fallback.')
@secure()
param openWeatherApiKey string = ''

@description('Latitude of the modelled network area (default: central London).')
param latitude string = '51.5072'

@description('Longitude of the modelled network area.')
param longitude string = '-0.1276'

@description('National Grid ESO Carbon Intensity region id (13 = London).')
param carbonRegionId string = '13'

@description('Minimum replicas for the API. 0 enables scale-to-zero.')
@minValue(0)
param apiMinReplicas int = 0

@description('Cron expression for the nightly retraining job (UTC).')
param pipelineCron string = '0 2 * * *'

@description('Tags applied to every resource.')
param tags object = {
  project: 'dynamic-resilient-grid'
  environment: environmentName
  workload: 'electrification-stress-analysis'
  dataClassification: 'anonymised-research'
}

var suffix = uniqueString(resourceGroup().id, namePrefix, environmentName)
var baseName = '${namePrefix}-${environmentName}'

// ---------------------------------------------------------------------------
// observability
// ---------------------------------------------------------------------------
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    tags: tags
    workspaceName: 'log-${baseName}'
    appInsightsName: 'appi-${baseName}'
  }
}

// ---------------------------------------------------------------------------
// identity used by every compute resource (no secrets in app settings)
// ---------------------------------------------------------------------------
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${baseName}'
  location: location
  tags: tags
}

// ---------------------------------------------------------------------------
// data plane
// ---------------------------------------------------------------------------
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    tags: tags
    storageAccountName: take(toLower('st${namePrefix}${environmentName}${suffix}'), 24)
    principalId: identity.properties.principalId
  }
}

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    tags: tags
    keyVaultName: take('kv-${namePrefix}-${environmentName}-${suffix}', 24)
    principalId: identity.properties.principalId
    openWeatherApiKey: openWeatherApiKey
  }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  params: {
    location: location
    tags: tags
    registryName: take(toLower('cr${namePrefix}${environmentName}${suffix}'), 50)
    principalId: identity.properties.principalId
  }
}

// ---------------------------------------------------------------------------
// compute
// ---------------------------------------------------------------------------
module apps 'modules/containerapps.bicep' = {
  name: 'containerapps'
  params: {
    location: location
    tags: tags
    environmentAppName: 'cae-${baseName}'
    baseName: baseName
    imageTag: imageTag
    registryLoginServer: registry.outputs.loginServer
    identityId: identity.id
    identityClientId: identity.properties.clientId
    logAnalyticsCustomerId: monitoring.outputs.customerId
    logAnalyticsKey: monitoring.outputs.primarySharedKey
    appInsightsConnectionString: monitoring.outputs.connectionString
    storageAccountName: storage.outputs.storageAccountName
    storageAccountKey: storage.outputs.primaryKey
    fileShareName: storage.outputs.fileShareName
    apiMinReplicas: apiMinReplicas
    pipelineCron: pipelineCron
    latitude: latitude
    longitude: longitude
    carbonRegionId: carbonRegionId
    keyVaultName: keyvault.outputs.keyVaultName
    hasOpenWeatherKey: !empty(openWeatherApiKey)
  }
}

// ---------------------------------------------------------------------------
// managed training (optional)
// ---------------------------------------------------------------------------
module aml 'modules/machinelearning.bicep' = if (deployMachineLearning) {
  name: 'machinelearning'
  params: {
    location: location
    tags: tags
    workspaceName: 'mlw-${baseName}'
    storageAccountId: storage.outputs.storageAccountId
    keyVaultId: keyvault.outputs.keyVaultId
    appInsightsId: monitoring.outputs.appInsightsId
    registryId: registry.outputs.registryId
    identityId: identity.id
  }
}

// ---------------------------------------------------------------------------
// outputs
// ---------------------------------------------------------------------------
output apiUrl string = 'https://${apps.outputs.apiFqdn}'
output dashboardUrl string = 'https://${apps.outputs.dashboardFqdn}'
output containerRegistry string = registry.outputs.loginServer
output storageAccount string = storage.outputs.storageAccountName
output keyVault string = keyvault.outputs.keyVaultName
output managedIdentityClientId string = identity.properties.clientId
output appInsightsConnectionString string = monitoring.outputs.connectionString
output machineLearningWorkspace string = deployMachineLearning ? aml!.outputs.workspaceName : ''
