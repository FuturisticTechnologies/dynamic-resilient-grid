#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Provision the DRG Azure environment and deploy the container images.
#
#   ./scripts/deploy_azure.sh -g rg-drg-dev -l uksouth
#   ./scripts/deploy_azure.sh -g rg-drg-dev -k "$DRG_OPENWEATHER_API_KEY"
# ---------------------------------------------------------------------------
set -Eeuo pipefail

RESOURCE_GROUP="rg-drg-dev"
LOCATION="uksouth"
ENVIRONMENT="dev"
NAME_PREFIX="drg"
IMAGE_TAG="$(date +%Y%m%d%H%M)"
OPENWEATHER_KEY=""
SKIP_INFRA=0
SKIP_BUILD=0
SKIP_SEED=0

usage() {
  sed -n '2,10p' "$0"
  echo "Options: -g <rg> -l <location> -e <env> -p <prefix> -t <tag> -k <owm-key> --skip-infra --skip-build --skip-seed"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -g) RESOURCE_GROUP="$2"; shift 2 ;;
    -l) LOCATION="$2"; shift 2 ;;
    -e) ENVIRONMENT="$2"; shift 2 ;;
    -p) NAME_PREFIX="$2"; shift 2 ;;
    -t) IMAGE_TAG="$2"; shift 2 ;;
    -k) OPENWEATHER_KEY="$2"; shift 2 ;;
    --skip-infra) SKIP_INFRA=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --skip-seed) SKIP_SEED=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }

step "Checking prerequisites"
command -v az >/dev/null || { echo "Azure CLI not found: https://aka.ms/installazurecli"; exit 1; }
az account show >/dev/null || { echo "Not signed in. Run: az login"; exit 1; }
az extension add --name containerapp --upgrade --only-show-errors >/dev/null 2>&1 || true
az extension add --name ml --upgrade --only-show-errors >/dev/null 2>&1 || true

step "Ensuring resource group ${RESOURCE_GROUP} (${LOCATION})"
az group create -n "$RESOURCE_GROUP" -l "$LOCATION" --only-show-errors >/dev/null

deploy_params=(
  --resource-group "$RESOURCE_GROUP"
  --template-file "$ROOT/infra/azure/main.bicep"
  --parameters "$ROOT/infra/azure/main.parameters.json"
  --parameters "namePrefix=$NAME_PREFIX" "environmentName=$ENVIRONMENT"
  --parameters "location=$LOCATION" "imageTag=$IMAGE_TAG"
)
[[ -n "$OPENWEATHER_KEY" ]] && deploy_params+=(--parameters "openWeatherApiKey=$OPENWEATHER_KEY")

if [[ $SKIP_INFRA -eq 0 ]]; then
  step "Deploying infrastructure (Bicep)"
  az deployment group create --name "drg-$IMAGE_TAG" "${deploy_params[@]}" --only-show-errors >/dev/null
fi

OUTPUTS=$(az deployment group show -g "$RESOURCE_GROUP" -n "drg-$IMAGE_TAG" --query properties.outputs -o json 2>/dev/null || echo '{}')
REGISTRY=$(echo "$OUTPUTS" | python -c "import json,sys;print(json.load(sys.stdin).get('containerRegistry',{}).get('value',''))")
REGISTRY_NAME="${REGISTRY%%.*}"
echo "  registry : ${REGISTRY:-<unknown>}"

if [[ $SKIP_BUILD -eq 0 ]]; then
  for spec in "drg-api:docker/Dockerfile.api" "drg-dashboard:docker/Dockerfile.dashboard" "drg-pipeline:docker/Dockerfile.pipeline"; do
    IMAGE="${spec%%:*}"; FILE="${spec#*:}"
    step "Building ${IMAGE}:${IMAGE_TAG} in ACR Tasks"
    az acr build --registry "$REGISTRY_NAME" \
      --image "${IMAGE}:${IMAGE_TAG}" --image "${IMAGE}:latest" \
      --file "$ROOT/$FILE" "$ROOT" --only-show-errors >/dev/null
  done

  step "Re-deploying container apps with tag ${IMAGE_TAG}"
  az deployment group create --name "drg-$IMAGE_TAG-apps" "${deploy_params[@]}" --only-show-errors >/dev/null
fi

if [[ $SKIP_SEED -eq 0 ]]; then
  step "Starting the pipeline job so the services have data"
  az containerapp job start --name "cj-${NAME_PREFIX}-${ENVIRONMENT}-pipeline" \
    -g "$RESOURCE_GROUP" --only-show-errors >/dev/null
fi

step "Deployment complete"
echo "$OUTPUTS" | python -c "
import json,sys
o = json.load(sys.stdin)
for key, label in (('apiUrl','API      '), ('dashboardUrl','Dashboard'), ('machineLearningWorkspace','AML ws   ')):
    if key in o:
        print(f'  {label}: {o[key][\"value\"]}')
"
