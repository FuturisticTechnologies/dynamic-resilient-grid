// Key Vault holding the external API credentials, with RBAC authorisation.
param location string
param tags object
param keyVaultName string

@description('Principal id of the workload managed identity.')
param principalId string

@secure()
param openWeatherApiKey string = ''

var secretsUser = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'   // Key Vault Secrets User
)

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: null
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource openWeatherSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(openWeatherApiKey)) {
  parent: vault
  name: 'openweather-api-key'
  properties: {
    value: openWeatherApiKey
    contentType: 'text/plain'
  }
}

resource secretsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, principalId, secretsUser)
  properties: {
    roleDefinitionId: secretsUser
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output keyVaultId string = vault.id
output keyVaultName string = vault.name
output keyVaultUri string = vault.properties.vaultUri
