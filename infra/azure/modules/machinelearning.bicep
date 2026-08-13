// Azure Machine Learning workspace for managed training runs, MLflow tracking
// and versioned model registration. The Container Apps job can run the whole
// pipeline unaided; this workspace is what you use when the Low Carbon London
// extract is large enough to need a compute cluster.
param location string
param tags object
param workspaceName string
param storageAccountId string
param keyVaultId string
param appInsightsId string
param registryId string
param identityId string

@description('VM size for the training cluster.')
param computeVmSize string = 'Standard_DS3_v2'

@description('Maximum nodes; 0 minimum keeps the cluster free when idle.')
param computeMaxNodes int = 2

resource workspace 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: workspaceName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    friendlyName: 'DRG electrification stress analysis'
    description: 'Training and model registry for the Dynamic Resilient Grid framework.'
    storageAccount: storageAccountId
    keyVault: keyVaultId
    applicationInsights: appInsightsId
    containerRegistry: registryId
    publicNetworkAccess: 'Enabled'
    hbiWorkspace: false
  }
}

resource cluster 'Microsoft.MachineLearningServices/workspaces/computes@2024-04-01' = {
  parent: workspace
  name: 'cpu-cluster'
  location: location
  properties: {
    computeType: 'AmlCompute'
    properties: {
      vmSize: computeVmSize
      vmPriority: 'Dedicated'
      scaleSettings: {
        minNodeCount: 0
        maxNodeCount: computeMaxNodes
        nodeIdleTimeBeforeScaleDown: 'PT10M'
      }
      osType: 'Linux'
    }
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output computeName string = cluster.name
