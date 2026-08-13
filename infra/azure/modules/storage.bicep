// ADLS Gen2 storage for smart-meter data and model artifacts, plus an Azure
// Files share that Container Apps mounts read/write.
//
// Data governance note: the UK Data Service End User Licence for study 7857
// prohibits publishing the raw data. The account therefore disables public
// blob access, enforces TLS 1.2 and HTTPS, and is reachable only through the
// managed identity granted below.
param location string
param tags object
param storageAccountName string

@description('Principal id of the workload managed identity.')
param principalId string

var blobDataContributor = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
)
var fileDataContributor = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '0c867c2a-1d8c-454a-a3db-ab2ea1bdc8bb'
)

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true                 // ADLS Gen2 hierarchical namespace
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true         // required by the Container Apps file mount
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
    encryption: {
      services: {
        blob: { enabled: true }
        file: { enabled: true }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for name in ['raw', 'processed', 'external', 'models', 'reports']: {
    parent: blobService
    name: name
    properties: {
      publicAccess: 'None'
    }
  }
]

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: 'drgdata'
  properties: {
    shareQuota: 100
    enabledProtocols: 'SMB'
  }
}

resource blobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, principalId, blobDataContributor)
  properties: {
    roleDefinitionId: blobDataContributor
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource fileRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, principalId, fileDataContributor)
  properties: {
    roleDefinitionId: fileDataContributor
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output storageAccountId string = storage.id
output storageAccountName string = storage.name
output fileShareName string = share.name
output blobEndpoint string = storage.properties.primaryEndpoints.blob
#disable-next-line outputs-should-not-contain-secrets
output primaryKey string = storage.listKeys().keys[0].value
