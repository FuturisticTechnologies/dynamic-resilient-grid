# Dynamic Resilient Grid (DRG)

**AI-driven local electricity demand forecasting and electrification stress analysis for UK urban networks.**

DRG forecasts half-hourly neighbourhood electricity demand from smart-meter data, defines
*stress* statistically from each neighbourhood's own historical distribution, simulates EV and
heat-pump adoption from the bottom up, and quantifies how much electrification amplifies peak
demand and escalates stress — with SHAP explanations, a near-real-time replay engine, a REST API
and an operator dashboard.

The system works purely on **demand-side** data. It performs no physical power-flow modelling;
it is a scenario-based resilience assessment tool for electrification planning.

---

## Table of contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Results from a reference run](#results-from-a-reference-run)
- [Data sources](#data-sources)
- [Architecture](#architecture)
- [Command line](#command-line)
- [REST API](#rest-api)
- [Dashboard](#dashboard)
- [Configuration](#configuration)
- [Modelling notes](#modelling-notes)
- [Azure deployment](#azure-deployment)
- [Testing and quality](#testing-and-quality)
- [Repository layout](#repository-layout)
- [Data governance](#data-governance)

---

## What it does

| Proposal objective | Where it lives |
|---|---|
| 1. Analyse neighbourhood consumption patterns | [`drg/analysis/eda.py`](src/drg/analysis/eda.py) |
| 2. Develop and validate short-term forecasting models | [`drg/models/`](src/drg/models/) |
| 3. Percentile-based statistical stress detection | [`drg/stress/detection.py`](src/drg/stress/detection.py) |
| 4. Simulate EV / heat-pump adoption, quantify peak amplification | [`drg/simulation/electrification.py`](src/drg/simulation/electrification.py) |
| 5. Sensitivity analysis of stress frequency and duration | [`drg/analysis/sensitivity.py`](src/drg/analysis/sensitivity.py) |
| 6. Explainable AI (SHAP) | [`drg/explain/shap_explain.py`](src/drg/explain/shap_explain.py) |
| 7. Streamlit dashboard, near-real-time replay, live APIs | [`drg/dashboard/`](src/drg/dashboard/), [`drg/streaming/`](src/drg/streaming/), [`drg/data/external_apis.py`](src/drg/data/external_apis.py) |

**Model ladder** — every model is evaluated on the same held-out chronological test window:

| Model | Role |
|---|---|
| Seasonal naive (same half-hour yesterday) | operational status quo to beat |
| Linear regression / Ridge | interpretable baseline |
| **XGBoost** | primary model, early-stopped on a validation window |
| LSTM / GRU (PyTorch) | optional deep sequence extension |
| Sequence MLP (scikit-learn) | torch-free neural fallback, used automatically when PyTorch cannot load |

---

## Quick start

Requires Python 3.10–3.12.

```bash
# 1. environment
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt
pip install -e . --no-deps

# 2. run everything: ingest -> EDA -> features -> train -> stress -> scenarios -> SHAP
python -m drg.cli run-all

# 3. explore
python -m drg.cli dashboard        # http://localhost:8501
python -m drg.cli serve            # http://localhost:8000/docs
```

Windows one-shot equivalent:

```powershell
./scripts/setup_local.ps1
```

Everything runs **without any API key and without the licensed dataset**: the framework falls back
to public key-free APIs and a calibrated synthetic smart-meter generator (see
[Data sources](#data-sources)). A full run takes roughly 4–6 minutes on a laptop.

Optional extras:

```bash
pip install -r requirements-deep.txt    # PyTorch LSTM
pip install -r requirements-azure.txt   # Azure SDKs, MLflow, Azure ML
pip install -r requirements-dev.txt     # pytest, ruff, black
```

---

## Results from a reference run

Reference run: 4 neighbourhoods x ~120 households, half-hourly, Jan 2012 – Feb 2014,
60-day held-out test window.

**Forecast accuracy** (test window, one step = 30 minutes ahead):

| Model | MAE (kWh) | RMSE | MAPE | R² | Stress-alarm F1 |
|---|---|---|---|---|---|
| **XGBoost** | **0.70** | **0.95** | **3.37 %** | **0.986** | **0.90** |
| Ridge / linear regression | 0.83 | 1.10 | 4.05 % | 0.982 | 0.89 |
| Sequence MLP | 0.78 | 1.13 | 3.84 % | 0.981 | 0.91 |
| Seasonal naive | 1.54 | 2.08 | 7.66 % | 0.934 | 0.85 |

Rolling-origin cross-validation (5 expanding folds) gives RMSE 0.74–0.95, so the test result is
not a lucky split.

**Electrification stress** (thresholds fixed at each site's historical P95):

| Scenario | Peak amplification | Energy growth | Stress frequency | Mean event duration |
|---|---|---|---|---|
| Base (no EV, no heat pump) | - | - | 4.4 % of half-hours | 2.2 h |
| EV 20 %, heat pumps 15 % | +52 % | +29 % | 20.2 % (4.6x base) | 4.7 h |
| EV 40 %, heat pumps 30 % | +115 % | +59 % | 31.8 % (7.2x base) | 5.5 h |
| EV 60 %, heat pumps 50 % | +190 % | +93 % | 40.2 % (9.1x base) | 6.3 h |
| EV 80 %, heat pumps 70 % | +237 % | +126 % | 46.8 % (10.6x base) | 6.9 h |

EV alone at 80 % gives +154 % peak; heat pumps alone at 70 % give +113 %. Together they give
+237 %, i.e. **29 percentage points less than additive** - the two loads peak at overlapping but
not identical times, which is a planning-relevant result in itself.

Sanity check against UK DNO planning practice: the simulation reports an after-diversity maximum
demand of **1.20 kW per EV** and **1.30 kW per heat pump**, and **5.3 kWh per car per day**
(≈1,900 kWh/year, consistent with average UK car mileage). These are printed in every scenario
summary so the numbers can be audited rather than taken on trust.

**Top SHAP drivers** — globally and, separately, during stress periods:

| Rank | All periods | Stress periods only |
|---|---|---|
| 1 | `lag_336` (same half-hour last week), 39 % | `lag_336`, 39 % |
| 2 | `lag_1` (previous half-hour), 27 % | `lag_1`, 29 % |
| 3 | `lag_48` (same half-hour yesterday), 7.6 % | `lag_48`, 10.7 % |
| 4 | `sin_period` (time of day), 4.0 % | `sin_period`, 3.3 % |

Weekly seasonality dominates, and its share *grows* during stress — high-demand half-hours are
strongly recurrent, which is exactly what makes them forecastable and therefore manageable.

Regenerate all of these with `python -m drg.cli run-all`; the numbers land in
`artifacts/reports/run_report.json`.

---

## Data sources

| Source | Use | Key needed |
|---|---|---|
| **Low Carbon London** smart meters (UK Data Service study 7857, 2011–2014) | primary half-hourly demand | licence registration |
| **Open-Meteo ERA5 archive** | historical temperature (genuinely observed, 1940–present) | no |
| **Open-Meteo forecast** | live temperature and short-term forecast | no |
| **National Grid ESO Carbon Intensity API** | half-hourly national + London carbon intensity | no |
| **OpenWeatherMap** | live conditions (preferred when a key is present) | yes, optional |

### Using the real Low Carbon London data

1. Register with the [UK Data Service](https://beta.ukdataservice.ac.uk/datacatalogue/studies/study?id=7857)
   and download the half-hourly extract.
2. Drop the CSVs anywhere under `data/raw/`.
3. Run `python -m drg.cli ingest --force`.

The loader reads in chunks, resolves the published column spellings case-insensitively, folds
households into fixed-size low-voltage groups by a stable hash of the meter id, and aggregates each
chunk immediately — so memory stays proportional to the chunk, not the dataset.

### Without it

`data.synthetic.enabled: true` (the default) generates a calibrated fallback: bimodal weekday load
curve, flatter/later weekend profile, household diversity scaling as 1/sqrt(N), holiday effects,
and a heating response driven by **real ERA5 temperature** fetched from Open-Meteo for the same
period. The processed table records which source was used in its `source` column, and every
carbon-intensity row is tagged `measured`, `climatology-proxy` (the API archive starts in 2018, so
for the 2011–2014 study period a documented seasonal/diurnal projection is used) or `synthetic`.

---

## Architecture

```
                 ┌───────────────────────────────────────────────────────────┐
  Low Carbon     │  drg.data        chunked ingest, cleaning, aggregation    │
  London CSVs ──▶│                  + public context APIs (weather, carbon)  │
                 └──────────────────────────┬────────────────────────────────┘
                                            ▼
                 ┌───────────────────────────────────────────────────────────┐
                 │  drg.features    calendar · cyclical · lags · rolling      │
                 │                  stats · ramp rate · HDD · carbon          │
                 └──────────────────────────┬────────────────────────────────┘
                                            ▼
        ┌───────────────────────────────────┼───────────────────────────────┐
        ▼                                   ▼                               ▼
┌────────────────┐            ┌──────────────────────────┐      ┌────────────────────┐
│ drg.models     │            │ drg.stress               │      │ drg.simulation     │
│ naive · linear │            │ P95 + mean+2σ thresholds │      │ EV 7 kW sessions   │
│ XGBoost · LSTM │            │ events · duration · peak │      │ heat pumps by HDD  │
└───────┬────────┘            └────────────┬─────────────┘      └─────────┬──────────┘
        │                                  │                              │
        │                                  ▼                              │
        │                     ┌──────────────────────────┐                │
        └────────────────────▶│ drg.analysis.sensitivity │◀───────────────┘
                              │ 5x5 adoption grid        │
                              │ elasticity · escalation  │
                              └────────────┬─────────────┘
                                           ▼
   ┌──────────────┬────────────────────────┴──────────┬────────────────────┐
   ▼              ▼                                   ▼                    ▼
drg.explain   drg.streaming                      drg.api              drg.dashboard
SHAP global   replay + rolling forecast          FastAPI              Streamlit
& stress-only + pre-emptive alerts               /forecast /scenario  5 panels
```

Full write-up in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Command line

```
python -m drg.cli --help

  ingest        Load smart-meter data and the weather / carbon context series
  eda           Load curves, seasonality, peak patterns  -> artifacts/figures
  features      Build the engineered feature table
  train         Train and evaluate the forecasting model ladder
  stress        Detect statistical stress periods and summarise them
  scenarios     Run the EV / heat-pump adoption grid and sensitivity analysis
  explain       SHAP explainability for the champion model
  run-all       Every stage, end to end, into artifacts/reports/run_report.json
  replay        Replay historical demand as a live feed with stress alerts
  context       Fetch the live weather and carbon-intensity snapshot
  serve         Start the FastAPI decision-support service
  dashboard     Launch the Streamlit dashboard
```

Useful flags: `--force` (ignore caches), `--offline` (skip all external APIs),
`--no-lstm`, `--config path/to/config.yaml`.

---

## REST API

```bash
python -m drg.cli serve      # OpenAPI docs at http://localhost:8000/docs
```

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness / readiness (used by Container Apps probes) |
| `GET /context` | live temperature + carbon intensity |
| `GET /neighbourhoods` | sites, household counts and stress thresholds |
| `GET /forecast?steps=48` | rolling one-step-ahead forecasts with stress alerts |
| `GET /stress` | historical stress summary and recent events |
| `POST /scenario` | evaluate an EV / heat-pump scenario on demand |
| `GET /sensitivity` | cached adoption grid + headline numbers |
| `GET /explain` | SHAP driver ranking |
| `GET /metrics` | model evaluation metrics |

```bash
curl -X POST localhost:8000/scenario \
  -H "content-type: application/json" \
  -d '{"ev_adoption":0.6,"hp_adoption":0.5,"days":120}'
```

---

## Dashboard

```bash
python -m drg.cli dashboard        # http://localhost:8501
```

Five panels: **Live & forecast** (streaming replay, rolling forecast, severity badge, headroom),
**Stress profile** (diurnal and seasonal stress concentration, event log), **Scenario studio**
(adoption sliders, stacked component profile, worst modelled day), **Sensitivity** (peak
amplification heat map, escalation curves), **Explainability** (SHAP global vs stress-period
drivers).

Charts follow a validated colour system: a fixed categorical order checked for colour-vision
deficiency separation, one blue ramp for magnitude, a reserved status palette that always ships
with an icon and a label, single y-axes throughout, and a data table beside every chart.

---

## Configuration

Everything lives in [`configs/config.yaml`](configs/config.yaml); `DRG_*` environment variables
(loaded from `.env`) override it. Copy `.env.example` to `.env` to set an OpenWeatherMap key or
point the model at a different location.

Key knobs:

```yaml
stress:
  primary_percentile: 95        # the stress threshold
  sensitivity_sigma: 2.0        # mean + 2 sd secondary threshold
  min_event_periods: 2          # >= 1 hour to count as an event

electrification:
  ev:
    charger_kw: 7.0
    window_start_hour: 17
    window_end_hour: 22
    weekday_charge_probability: 0.32   # ~1 day in 3; matches UK average mileage
    adoption_levels: [0.0, 0.2, 0.4, 0.6, 0.8]
  heat_pump:
    rated_kw: 2.5
    kw_per_degree: 0.085               # ~1.2 kW at 5 C, saturating near the design condition
    adoption_levels: [0.0, 0.15, 0.3, 0.5, 0.7]
  monte_carlo_runs: 30
```

---

## Modelling notes

**No leakage.** Lags and rolling statistics are computed from shifted values only and never cross a
neighbourhood boundary; splits are chronological (train → validation → test by wall-clock time);
rolling-origin cross-validation always trains on the past. Tests assert each of these.

**Stress is statistical, not physical.** No transformer ratings are published with the Low Carbon
London data, so stress is the 95th percentile of each site's own history (with mean + 2σ as a
sensitivity check). Thresholds are estimated on the baseline window and then **held fixed**, so a
scenario that raises demand raises measured stress instead of moving the goalposts with it.

**Electrification is bottom-up.** Each adopting household is simulated individually — EV plug-in
day, start time inside the evening window, session length, with partial half-hour overlap accounted
for analytically; heat-pump electrical input driven by heating degrees, shaped by occupancy and
capped at the unit rating. Diversity factors are applied to the aggregate, and the whole simulation
repeats `monte_carlo_runs` times.

**Train/serve parity.** The streaming engine and the API rebuild features with the same functions
used offline, and reuse the same cached carbon-intensity series, so the online design matrix
matches the training one.

**Honest provenance.** Every derived series is tagged with its source. The carbon-intensity archive
begins in 2018, so for the 2011–2014 study period the framework projects a documented
seasonal/diurnal climatology rather than pretending to have measurements.

---

## Azure deployment

```powershell
./scripts/deploy_azure.ps1 -ResourceGroup rg-drg-dev -Location uksouth
```
```bash
./scripts/deploy_azure.sh -g rg-drg-dev -l uksouth
```

Provisions, via [`infra/azure/main.bicep`](infra/azure/main.bicep):

| Resource | Role |
|---|---|
| Container Registry | api / dashboard / pipeline images (built with ACR Tasks — no local Docker needed) |
| Storage (ADLS Gen2 + Files) | raw and processed data, model artifacts, shared volume |
| Key Vault | OpenWeatherMap key, referenced by managed identity |
| Log Analytics + Application Insights | logs and traces (the logger auto-attaches when the connection string is present) |
| Container Apps environment | `drg-api` (scale-to-zero), `drg-dashboard` (sticky sessions), `drg-pipeline` (nightly cron job) |
| Azure ML workspace + CPU cluster | optional managed training, MLflow tracking, model registry |
| User-assigned managed identity | ACR pull, blob/file data access, Key Vault secrets — no stored credentials |

### CI/CD

Three workflows, all authenticating with OIDC federated credentials (no secrets in the repo):

| Workflow | Trigger | What it does |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | every push / PR | lint, test, end-to-end pipeline smoke test, container builds |
| [`deploy-azure.yml`](.github/workflows/deploy-azure.yml) | push to `main`, manual | ships the **application**: images, infrastructure, retrain job |
| [`model-deploy.yml`](.github/workflows/model-deploy.yml) | weekly cron, manual | ships the **model**: train, gate, register, blue/green deploy |

### Model deployment pipeline

Application and model deployment are separate on purpose. Nothing reaches production traffic
without clearing a quality gate *and* a live scoring test:

```
train (Azure ML) -> promotion gate -> register -> deploy to idle slot (0% traffic)
                          |                                   |
                     blocked? stop,                     smoke test
                  incumbent keeps serving                     |
                                            shift 100% -> verify live -> retire old slot
                                                              |
                                                       any failure -> roll back
```

**The promotion gate** ([`src/drg/mlops/gate.py`](src/drg/mlops/gate.py), thresholds in
`configs/config.yaml`) applies absolute floors — R² ≥ 0.90, MAPE ≤ 8 %, stress recall ≥ 0.70,
≥ 5,000 test rows — and a comparison against whatever is currently deployed: RMSE may regress by at
most 2 % (so retraining noise does not block a refresh) and stress recall by at most 5 pp. Stress
recall is gated harder than precision because a missed stress period is a missed reinforcement
signal, while a false alarm costs a glance at a dashboard. A missing metric counts as a failure,
never a pass. Gate metrics are written onto the registered model as tags, which is how the next run
finds its incumbent.

**Blue/green** — the new model is deployed into the idle slot with 0 % traffic and invoked there
first. [`pipelines/verify_endpoint.py`](pipelines/verify_endpoint.py) checks behaviour rather than
HTTP status: forecasts must be numeric and in a plausible kWh range, no features may have been
silently dropped, and latency must be within budget — a `200 {"forecast_kwh": [0.0]}` fails.
Traffic shifts only after that passes; the old slot is deleted only after the live endpoint is
verified too; any failure rolls back and leaves the incumbent serving.

Run the gate locally against any pipeline artifact:

```bash
python pipelines/promote_model.py --candidate artifacts/reports/run_report.json
# exit 0 = promote, exit 2 = blocked; prints a check-by-check table
```

Manual dispatch supports `skipTraining` (redeploy the latest registered model), `allowSynthetic`
(demo runs), and `dryRun` (gate report only, deploy nothing). The `deploy` job declares a GitHub
`environment:`, so a protection rule on `prod` adds a human approval before traffic moves.

Managed training and endpoint definitions live in [`infra/aml/`](infra/aml/):

```bash
az ml environment create -f infra/aml/environment.yml
az ml job create -f infra/aml/train-job.yml
az ml online-endpoint create -f infra/aml/endpoint.yml
az ml online-deployment create -f infra/aml/deployment.yml --all-traffic
```

Local container stack:

```bash
docker compose run --rm pipeline    # build data, models, reports
docker compose up api dashboard     # serve them
```

Step-by-step guide: [`docs/AZURE.md`](docs/AZURE.md).

---

## Testing and quality

```bash
pytest tests -q                        # 52 tests
ruff check src tests pipelines
black --check src tests pipelines
```

The suite covers data cleaning and column resolution, feature-leakage guarantees, metric
correctness, the model ladder beating the naive benchmark, threshold and event-detection maths,
physical plausibility of the EV and heat-pump simulations (charger rating, heat-pump rating, daily
energy per car, ADMD), sensitivity-grid monotonicity, replay behaviour, offline API fallbacks and
the FastAPI service, and a Streamlit `AppTest` run that executes every dashboard panel.
Everything runs offline in about 20 seconds.

---

## Formal documentation

Two approval-ready documents in [`docs/design/`](docs/design/), rendered to PDF:

| Document | Pages | Contents |
|---|---|---|
| [Business Requirements (DRG-BRD-001)](docs/design/DRG_Business_Requirements.pdf) | 28 | Business case, scope, stakeholders and RACI, as-is/to-be process, 18 business + 33 functional + 12 non-functional requirements, acceptance criteria, benefits, traceability matrix |
| [Architecture & Design (DRG-SAD-001)](docs/design/DRG_Architecture_Design.pdf) | 37 | Overview and scope, system context, layered architecture, **10 UML diagrams** (use case, component, class, three sequence, activity, two state machine, deployment), data and ML architecture, security, NFR realisation, risks |

---

## Repository layout

```
DynamicResilientGrid/
├── configs/config.yaml            # single source of truth for every parameter
├── src/drg/
│   ├── config.py                  # typed config: YAML + .env + environment
│   ├── pipeline.py                # stage functions + run_all orchestration
│   ├── cli.py                     # typer command line
│   ├── data/                      # LCL loader, synthetic fallback, public API clients
│   ├── features/                  # calendar / statistical / exogenous features
│   ├── models/                    # baseline, XGBoost, LSTM + MLP, evaluation, registry
│   ├── stress/                    # percentile thresholds, events, summaries
│   ├── simulation/                # bottom-up EV and heat-pump models
│   ├── analysis/                  # EDA figures, sensitivity grid, elasticity
│   ├── explain/                   # SHAP global + stress-conditional
│   ├── mlops/                     # model promotion gate
│   ├── streaming/                 # near-real-time replay engine
│   ├── api/                       # FastAPI service
│   └── dashboard/                 # Streamlit app + chart theme
├── pipelines/                     # Azure ML job, scoring, promotion gate, endpoint verifier
├── infra/azure/                   # Bicep: registry, storage, vault, monitoring, apps, AML
├── infra/aml/                     # Azure ML environment, training job, endpoint
├── docker/                        # API, dashboard and pipeline images
├── scripts/                       # local setup + Azure deployment (bash and PowerShell)
├── notebooks/                     # exploratory walkthrough
├── tests/                         # 52 tests, fully offline
└── docs/                          # architecture and Azure guides
```

---

## Data governance

- Complies with the UK Data Service End User Licence: raw smart-meter data is never committed
  (`data/raw/` is git-ignored) and never uploaded to a public cloud service by this code.
- All datasets used are anonymised; the Azure storage account disables public blob access,
  enforces HTTPS and TLS 1.2, and is reachable only through a managed identity.
- The synthetic fallback contains no real household data at all, which is what makes the
  repository runnable and shareable end to end.

---

## Licence

MIT for the code. The Low Carbon London dataset remains under the UK Data Service End User Licence;
Open-Meteo and the National Grid ESO Carbon Intensity API have their own terms.
