<#
.SYNOPSIS
    Provision the DRG Azure environment and deploy all three container images.

.DESCRIPTION
    1. Creates the resource group.
    2. Deploys infra/azure/main.bicep (ACR, storage, Key Vault, monitoring,
       Container Apps environment, optional Azure ML workspace).
    3. Builds the api / dashboard / pipeline images in ACR Tasks (no local
       Docker required) and re-deploys with the new tag.
    4. Runs the pipeline job once so the services have data to serve.

.EXAMPLE
    ./scripts/deploy_azure.ps1 -ResourceGroup rg-drg-dev -Location uksouth

.EXAMPLE
    ./scripts/deploy_azure.ps1 -ResourceGroup rg-drg-dev -OpenWeatherApiKey $env:DRG_OPENWEATHER_API_KEY
#>
[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-drg-dev",
    [string]$Location = "uksouth",
    [ValidateSet("dev", "test", "prod")]
    [string]$EnvironmentName = "dev",
    [string]$NamePrefix = "drg",
    [string]$ImageTag = (Get-Date -Format "yyyyMMddHHmm"),
    [string]$OpenWeatherApiKey = "",
    [switch]$SkipInfra,
    [switch]$SkipBuild,
    [switch]$SkipSeedRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

# --- preflight --------------------------------------------------------------
Write-Step "Checking prerequisites"
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI not found. Install from https://aka.ms/installazurecli"
}
$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) { throw "Not signed in. Run: az login" }
Write-Host "  subscription : $($account.name)"
Write-Host "  tenant       : $($account.tenantId)"

az extension add --name containerapp --upgrade --only-show-errors 2>$null | Out-Null
az extension add --name ml --upgrade --only-show-errors 2>$null | Out-Null
az provider register --namespace Microsoft.App --wait 2>$null | Out-Null
az provider register --namespace Microsoft.OperationalInsights --wait 2>$null | Out-Null

# --- resource group ---------------------------------------------------------
Write-Step "Ensuring resource group $ResourceGroup ($Location)"
az group create --name $ResourceGroup --location $Location --only-show-errors | Out-Null

# --- infrastructure ---------------------------------------------------------
if (-not $SkipInfra) {
    Write-Step "Deploying infrastructure (Bicep)"
    $deployArgs = @(
        "deployment", "group", "create",
        "--resource-group", $ResourceGroup,
        "--name", "drg-$ImageTag",
        "--template-file", (Join-Path $root "infra/azure/main.bicep"),
        "--parameters", (Join-Path $root "infra/azure/main.parameters.json"),
        "--parameters", "namePrefix=$NamePrefix", "environmentName=$EnvironmentName",
        "--parameters", "location=$Location", "imageTag=$ImageTag"
    )
    if ($OpenWeatherApiKey) {
        $deployArgs += @("--parameters", "openWeatherApiKey=$OpenWeatherApiKey")
    }
    az @deployArgs --only-show-errors | Out-Null
}

$outputs = az deployment group show --resource-group $ResourceGroup --name "drg-$ImageTag" `
    --query properties.outputs 2>$null | ConvertFrom-Json
if (-not $outputs) {
    $latest = az deployment group list --resource-group $ResourceGroup `
        --query "sort_by([?properties.provisioningState=='Succeeded'], &properties.timestamp)[-1].name" -o tsv
    $outputs = az deployment group show --resource-group $ResourceGroup --name $latest `
        --query properties.outputs | ConvertFrom-Json
}
$registry = $outputs.containerRegistry.value
$registryName = $registry.Split(".")[0]
Write-Host "  registry : $registry"

# --- images -----------------------------------------------------------------
if (-not $SkipBuild) {
    foreach ($image in @(
        @{ Name = "drg-api"; File = "docker/Dockerfile.api" },
        @{ Name = "drg-dashboard"; File = "docker/Dockerfile.dashboard" },
        @{ Name = "drg-pipeline"; File = "docker/Dockerfile.pipeline" }
    )) {
        Write-Step "Building $($image.Name):$ImageTag in ACR Tasks"
        az acr build `
            --registry $registryName `
            --image "$($image.Name):$ImageTag" `
            --image "$($image.Name):latest" `
            --file (Join-Path $root $image.File) `
            $root --only-show-errors | Out-Null
    }

    Write-Step "Re-deploying container apps with tag $ImageTag"
    $redeploy = @(
        "deployment", "group", "create",
        "--resource-group", $ResourceGroup,
        "--name", "drg-$ImageTag-apps",
        "--template-file", (Join-Path $root "infra/azure/main.bicep"),
        "--parameters", (Join-Path $root "infra/azure/main.parameters.json"),
        "--parameters", "namePrefix=$NamePrefix", "environmentName=$EnvironmentName",
        "--parameters", "location=$Location", "imageTag=$ImageTag"
    )
    if ($OpenWeatherApiKey) {
        $redeploy += @("--parameters", "openWeatherApiKey=$OpenWeatherApiKey")
    }
    az @redeploy --only-show-errors | Out-Null
}

# --- seed run ---------------------------------------------------------------
if (-not $SkipSeedRun) {
    Write-Step "Starting the pipeline job so the services have data"
    $jobName = "cj-$NamePrefix-$EnvironmentName-pipeline"
    az containerapp job start --name $jobName --resource-group $ResourceGroup --only-show-errors | Out-Null
    Write-Host "  job started: $jobName (watch with 'az containerapp job execution list')"
}

Write-Step "Deployment complete"
Write-Host "  API       : $($outputs.apiUrl.value)"       -ForegroundColor Green
Write-Host "  Dashboard : $($outputs.dashboardUrl.value)" -ForegroundColor Green
Write-Host "  Docs      : $($outputs.apiUrl.value)/docs"  -ForegroundColor Green
