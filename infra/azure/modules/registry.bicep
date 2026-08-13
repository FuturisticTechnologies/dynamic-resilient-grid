// Azure Container Registry for the api / dashboard / pipeline images.
param location string
param tags object
param registryName string

@description('Principal id of the workload managed identity (needs pull).')
param principalId string

@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

var acrPull = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: false            // managed-identity pull only
    publicNetworkAccess: 'Enabled'
  }
}

resource pullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, principalId, acrPull)
  properties: {
    roleDefinitionId: acrPull
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output registryId string = registry.id
output registryName string = registry.name
output loginServer string = registry.properties.loginServer
