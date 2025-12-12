# Deploying DRG to Azure

Step-by-step guide for provisioning and operating the Dynamic Resilient Grid framework on Azure.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Azure subscription | Contributor + User Access Administrator on the target resource group (role assignments are created by the template) |
| [Azure CLI](https://aka.ms/installazurecli) 2.60+ | `az login` before you start |
| CLI extensions | `az extension add --name containerapp --upgrade` and `--name ml` (the scripts do this for you) |
| Resource providers | `Microsoft.App`, `Microsoft.OperationalInsights`, `Microsoft.ContainerRegistry`, `Microsoft.MachineLearningServices` (registered by the scripts) |

No local Docker installation is needed — images are built server-side with ACR Tasks.

---

## 2. One-command deployment

```powershell
# Windows
./scripts/deploy_azure.ps1 -ResourceGroup rg-drg-dev -Location uksouth
```

```bash
# Linux / macOS
./scripts/deploy_azure.sh -g rg-drg-dev -l uksouth
```

The script:

1. creates the resource group;
2. deploys `infra/azure/main.bicep`;
3. builds `drg-api`, `drg-dashboard` and `drg-pipeline` in ACR Tasks;
4. redeploys the Container Apps with the new image tag;
5. starts the pipeline job once so the services have data to serve;
6. prints the API and dashboard URLs.

First run takes roughly 12–18 minutes, most of it image builds. Add an OpenWeatherMap key with
`-OpenWeatherApiKey <key>` / `-k <key>` — without one, the deployment uses the key-free Open-Meteo
fallback and no Key Vault reference is created.

Useful flags: `-SkipInfra` / `--skip-infra` (redeploy code only), `-SkipBuild` / `--skip-build`,
`-SkipSeedRun` / `--skip-seed`.

---

## 3. What gets created

| Resource | Name pattern | Purpose |
|---|---|---|
| Container Registry | `cr<prefix><env><hash>` | api / dashboard / pipeline images |
| Storage account | `st<prefix><env><hash>` | ADLS Gen2 containers (`raw`, `processed`, `external`, `models`, `reports`) + the `drgdata` file share |
| Key Vault | `kv-<prefix>-<env>-<hash>` | OpenWeatherMap key, RBAC-authorised |
| Log Analytics | `log-<prefix>-<env>` | container logs |
| Application Insights | `appi-<prefix>-<env>` | traces and metrics |
| Managed identity | `id-<prefix>-<env>` | ACR pull, storage data access, Key Vault secrets |
| Container Apps env | `cae-<prefix>-<env>` | hosting |
| API app | `ca-<prefix>-<env>-api` | FastAPI, external ingress, scale-to-zero |
| Dashboard app | `ca-<prefix>-<env>-dash` | Streamlit, sticky sessions |
| Pipeline job | `cj-<prefix>-<env>-pipeline` | nightly retrain (cron `0 2 * * *`) |
| Azure ML workspace | `mlw-<prefix>-<env>` | optional managed training + registry |

All three compute resources mount the same Azure Files share at `/app/shared`, so the batch job
publishes data and models that the two services read immediately.

Approximate dev-tier cost: roughly USD 60–110 per month with scale-to-zero on the API and the AML
cluster idling at zero nodes. Set `deployMachineLearning: false` in
`infra/azure/main.parameters.json` to drop the workspace.

---

## 4. Manual deployment

```bash
az group create -n rg-drg-dev -l uksouth

az deployment group create \
  -g rg-drg-dev \
  -f infra/azure/main.bicep \
  -p infra/azure/main.parameters.json \
  -p environmentName=dev imageTag=v1

REGISTRY=$(az deployment group show -g rg-drg-dev -n main \
  --query properties.outputs.containerRegistry.value -o tsv)

az acr build --registry "${REGISTRY%%.*}" --image drg-api:v1 \
  --file docker/Dockerfile.api .
az acr build --registry "${REGISTRY%%.*}" --image drg-dashboard:v1 \
  --file docker/Dockerfile.dashboard .
az acr build --registry "${REGISTRY%%.*}" --image drg-pipeline:v1 \
  --file docker/Dockerfile.pipeline .
```

Then re-run the deployment with the same `imageTag` to roll the apps forward.

---

## 5. Loading the real Low Carbon London data

The raw extract must not be committed to source control, so upload it directly to the storage
account:

```bash
STORAGE=$(az deployment group show -g rg-drg-dev -n main \
  --query properties.outputs.storageAccount.value -o tsv)

az storage fs directory upload \
  --account-name "$STORAGE" -f raw \
  -s ./local-lcl-extract --recursive --auth-mode login
```

Then point `data.lcl_glob` at the mounted path and trigger the job:

```bash
az containerapp job start -n cj-drg-dev-pipeline -g rg-drg-dev
```

---

## 6. CI/CD with GitHub Actions

`deploy-azure.yml` authenticates with **OIDC federated credentials** — no secrets stored in the
repository. Create the app registration and federated credential once:

```bash
az ad app create --display-name drg-github-oidc
APP_ID=$(az ad app list --display-name drg-github-oidc --query "[0].appId" -o tsv)
az ad sp create --id "$APP_ID"

az role assignment create --assignee "$APP_ID" --role Contributor \
  --scope /subscriptions/<SUB_ID>/resourceGroups/rg-drg-dev
az role assignment create --assignee "$APP_ID" --role "User Access Administrator" \
  --scope /subscriptions/<SUB_ID>/resourceGroups/rg-drg-dev

az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<OWNER>/<REPO>:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

Repository secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, and optionally
`DRG_OPENWEATHER_API_KEY`. Repository variables: `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`.

---

## 7. Managed training with Azure ML

```bash
WS=mlw-drg-dev
az ml environment create -f infra/aml/environment.yml -g rg-drg-dev -w $WS
az ml job create      -f infra/aml/train-job.yml      -g rg-drg-dev -w $WS
```

`pipelines/run_azureml.py` runs the same stages as the CLI and additionally logs parameters,
metrics (test MAE/RMSE/MAPE/R², stress F1, CV RMSE, worst-case peak amplification) and artifacts to
MLflow, then registers the champion as `drg-champion`.

Serve it behind a managed online endpoint:

```bash
az ml online-endpoint create   -f infra/aml/endpoint.yml   -g rg-drg-dev -w $WS
az ml online-deployment create -f infra/aml/deployment.yml -g rg-drg-dev -w $WS --all-traffic
```

`pipelines/score.py` handles scoring: it accepts a batch of feature records, fills missing features
with NaN (which the gradient-boosted champion handles natively) and reports which were missing, and
returns forecasts plus stress flags and headroom when a threshold is supplied.

---

## 8. Model deployment pipeline (MLOps)

Application deployment and *model* deployment are deliberately separate
workflows. `deploy-azure.yml` ships containers; `model-deploy.yml` ships a model, and nothing
reaches production traffic without clearing a quality gate and a live scoring test.

```
train (Azure ML)  ->  promotion gate  ->  register  ->  deploy to idle slot (0% traffic)
                            |                                      |
                       blocked? stop,                        smoke test
                    incumbent keeps serving                        |
                                                      shift 100% -> verify live -> retire old slot
                                                                   |
                                                            any failure -> roll back
```

### Triggering it

| Trigger | Effect |
|---|---|
| Schedule (Mon 03:00 UTC) | weekly retrain and, if it passes the gate, redeploy |
| `workflow_dispatch` | manual run with options below |

Dispatch inputs:

- **environment** - `dev` / `test` / `prod`; the `deploy` job uses GitHub `environment:`, so a
  protection rule on `prod` gives you a human approval step before any traffic moves.
- **skipTraining** - gate and redeploy the latest registered model without retraining.
- **allowSynthetic** - acknowledge a model trained on the synthetic fallback (demo only).
- **dryRun** - evaluate the gate and publish the report, deploy nothing.

### The promotion gate

Logic lives in [`src/drg/mlops/gate.py`](../src/drg/mlops/gate.py), thresholds in
`configs/config.yaml` under `mlops.promotion_gate`:

| Check | Default | Kind |
|---|---|---|
| R2 floor | >= 0.90 | absolute, blocking |
| MAPE ceiling | <= 8 % | absolute, blocking |
| Stress recall floor | >= 0.70 | absolute, blocking |
| Stress F1 floor | >= 0.65 | absolute, blocking |
| Evaluation size | >= 5,000 test rows | absolute, blocking |
| RMSE vs incumbent | <= +2 % | relative, blocking |
| Stress recall vs incumbent | <= -5 pp | relative, blocking |
| Data provenance | not `synthetic` | warning only |

Two deliberate design choices:

- **Stress recall is gated harder than precision.** A missed stress period is a missed
  reinforcement signal; a false alarm costs a glance at a dashboard.
- **A small RMSE regression is tolerated (2 %)** so ordinary retraining noise does not block a
  refresh, but a real regression stops the deployment - and no RMSE improvement can buy a recall
  collapse, because the recall check is independent.

A missing metric counts as a failure, never a pass. On the first ever deployment there is no
incumbent and only the absolute gates apply.

The gate writes its metrics onto the registered model as Azure ML tags, which is how the *next*
run finds its incumbent - no separate metrics store.

Run it locally against any pipeline artifact:

```bash
python pipelines/promote_model.py --candidate artifacts/reports/run_report.json
python pipelines/promote_model.py --candidate artifacts/reports/run_report.json     --incumbent incumbent_tags.json --summary-out gate.md
# exit 0 = promote, exit 2 = blocked
```

### Blue/green deployment

The workflow reads the endpoint traffic split, picks the *idle* slot (`blue` <-> `green`), deploys
there with **0 % traffic**, and only then invokes it. Traffic shifts to 100 % only after
[`pipelines/verify_endpoint.py`](../pipelines/verify_endpoint.py) passes, and the previous slot is
deleted only after the live endpoint has been verified too.

The smoke test checks behaviour, not just HTTP 200: forecasts must be numeric and inside a
plausible kWh range, no features may have been silently dropped from the request, `is_stress` must
align with the forecasts, and latency must be within `mlops.smoke_test.max_latency_ms`. An endpoint
returning `200 {"forecast_kwh": [0.0]}` fails.

Any failure after the new slot exists triggers the rollback step: traffic returns to the incumbent
and the new deployment is deleted.

### Manual equivalent

```bash
WS=mlw-drg-dev; RG=rg-drg-dev; EP=drg-forecast

# what is live now?
az ml online-endpoint show -n $EP -g $RG -w $WS --query traffic

# deploy the newest registered model into the idle slot, no traffic
az ml online-deployment create -f infra/aml/deployment.yml -g $RG -w $WS   --set name=green model=azureml:drg-champion@latest

# test it before it serves anyone
az ml online-endpoint invoke -n $EP --deployment-name green   --request-file infra/aml/sample-request.json -g $RG -w $WS > response.json
python pipelines/verify_endpoint.py --response response.json   --request infra/aml/sample-request.json

# cut over, then retire the old slot
az ml online-endpoint update -n $EP --traffic "green=100 blue=0" -g $RG -w $WS
az ml online-deployment delete -n blue --endpoint-name $EP -g $RG -w $WS --yes
```

`infra/aml/sample-request.json` is a real 47-feature evening-peak row taken from the feature
table, not a placeholder, so a passing smoke test means the model genuinely scored a
production-shaped payload.

---

## 9. Operating

```bash
# logs
az containerapp logs show -n ca-drg-dev-api -g rg-drg-dev --follow

# run the pipeline now
az containerapp job start -n cj-drg-dev-pipeline -g rg-drg-dev
az containerapp job execution list -n cj-drg-dev-pipeline -g rg-drg-dev -o table

# change the retrain schedule
az deployment group create -g rg-drg-dev -f infra/azure/main.bicep \
  -p infra/azure/main.parameters.json -p pipelineCron="0 4 * * 1"

# keep one API replica warm (removes cold starts)
az deployment group create -g rg-drg-dev -f infra/azure/main.bicep \
  -p infra/azure/main.parameters.json -p apiMinReplicas=1
```

Application Insights queries worth saving:

```kusto
// slowest API requests
requests | where cloud_RoleName has "api"
| summarize p95=percentile(duration, 95), count() by name
| order by p95 desc

// pipeline warnings from the nightly job
traces | where cloud_RoleName has "pipeline" and severityLevel >= 2
| project timestamp, message | order by timestamp desc
```

---

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| API returns 503 with "Processed demand not found" | The pipeline job has not completed yet. `az containerapp job start -n cj-drg-dev-pipeline -g rg-drg-dev` and wait. |
| Container app cannot pull the image | The AcrPull role assignment can take a minute to propagate. Redeploy, or check the identity on the app. |
| Deployment fails on `roleAssignments` | The deploying principal needs **User Access Administrator** (or Owner) on the resource group. |
| Key Vault reference fails to resolve | The `openweather-api-key` secret only exists when `openWeatherApiKey` was supplied; the template omits the reference otherwise. Redeploy with the key to add it. |
| Dashboard loses state on refresh | Sticky sessions are enabled; if you scaled beyond one replica without them, re-apply the template. |
| Cold-start latency on the API | Expected with `apiMinReplicas: 0`. Set it to 1. |
| Model promotion blocked | Read the `promotion-gate` artifact for the check-by-check detail. The incumbent keeps serving; nothing was changed. |
| Endpoint smoke test fails | The new slot is deleted automatically and traffic stays on the incumbent. Check the deployment logs: `az ml online-deployment get-logs -n <slot> --endpoint-name drg-forecast`. |
| Gate blocks every run with "Evaluation size" | The training window is too short. Lower `mlops.promotion_gate.min_train_rows` or lengthen `models.test_size_days`. |

---

## 11. Tear-down

```bash
az group delete -n rg-drg-dev --yes --no-wait
```

Key Vault soft-delete retains the vault name for 7 days; purge it explicitly if you need to reuse
the name sooner:

```bash
az keyvault purge --name <vault-name> --location uksouth
```
