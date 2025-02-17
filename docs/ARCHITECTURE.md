# DRG architecture

This document explains *why* the system is built the way it is. For how to run it, see the
[README](../README.md).

---

## 1. Design principles

1. **Stages are pure functions over tables.** Each stage reads a parquet table, returns a parquet
   table, and caches its output. Any stage can be re-run alone (`python -m drg.cli features`), and
   the Azure ML job and the local CLI call the *same* functions — there is no second code path for
   the cloud.
2. **One feature builder.** Training, streaming replay and the API all call
   `drg.features.engineering`. Train/serve skew is a class of bug that cannot occur here, and the
   replay engine deliberately reloads the cached carbon-intensity series so that even the exogenous
   columns match.
3. **Never claim data you do not have.** Every derived series carries a `source` column, and the
   pipeline degrades in documented steps (measured → climatology proxy → synthetic) rather than
   failing or silently fabricating.
4. **Thresholds are fixed before scenarios run.** Stress is measured against the historical
   baseline, so electrification raises the measured stress rather than moving the goalposts.
5. **Physical sanity is asserted, not assumed.** The simulation reports ADMD per technology and
   kWh per car per day; tests assert charger and heat-pump ratings are never exceeded and that
   daily EV energy stays in the range implied by UK average mileage.

---

## 2. Data flow

### 2.1 Ingestion (`drg.data`)

The Low Carbon London half-hourly release is several GB of CSV with columns
`LCLid, stdorToU, DateTime, KWH/hh (per half hour)`. `lcl_loader` reads it with
`pandas.read_csv(chunksize=...)` and **aggregates inside the chunk loop**, so peak memory is
proportional to `chunk_size`, not to the file — this is what keeps the 8 GB requirement in the
proposal honest.

Households become "neighbourhoods" through a stable BLAKE2b hash of the meter id modulo the
configured group count. The hash is stable across processes and runs (unlike Python's `hash()`,
which is salted per process), so group membership is reproducible.

Cleaning then: regularises the 30-minute grid, clips outliers with a median-absolute-deviation
rule (robust to the very spikes it is meant to catch), interpolates gaps up to
`max_gap_periods` **inside** the series only, and drops days with less than `min_coverage` of their
48 periods.

### 2.2 Context APIs (`drg.data.external_apis`)

| Service | Why this one |
|---|---|
| Open-Meteo ERA5 archive | free, no key, and its archive genuinely covers 2011–2014, so historical temperature for the study period is observed rather than modelled |
| Open-Meteo forecast | free live conditions and short-term forecast |
| National Grid ESO Carbon Intensity | the authoritative GB source; free, no key, half-hourly, national and regional |
| OpenWeatherMap | used for live conditions when a key is configured |

Every call is retried with exponential backoff (`tenacity`), disk-cached (`requests-cache`), and
falls back deterministically. The carbon API archive starts in 2018; for earlier study periods the
client pulls one reference year and projects a **month × half-hour median climatology** onto the
study index, tagging every row `climatology-proxy`.

### 2.3 Features (`drg.features.engineering`)

| Group | Columns |
|---|---|
| Calendar | hour, `period_of_day` (0–47), day of week, month, season, week of year, weekend flag, UK bank-holiday flag, evening-peak flag |
| Cyclical | sin/cos of period, day of week and day of year — so linear models see periodicity as smoothly as trees do |
| Lags | t-1, t-2, t-3, t-48 (yesterday), t-96, t-336 (last week) |
| Rolling | mean / std / min / max over 3 h, 1 day and 1 week, all computed on `shift(1)` |
| Dynamics | ramp rate, ramp acceleration, daily and weekly deltas, load factor |
| Exogenous | temperature, heating degrees, cooling degrees, lagged and smoothed temperature, HDD × evening interaction, carbon intensity |

Two invariants are enforced and tested: rolling statistics are built from **shifted** values (never
including the current observation), and `groupby("neighbourhood_id")` means no lag ever crosses a
site boundary.

---

## 3. Forecasting (`drg.models`)

The ladder exists so that the headline number means something: a 3.4 % MAPE is only impressive
against the 7.7 % that a seasonal-naive rule achieves on the same window.

- **Splitting** is chronological — train, then a validation window for early stopping, then a
  held-out test window (60 days by default).
- **Rolling-origin cross-validation** (`TimeSeriesSplit`) re-fits the champion on five expanding
  windows to show the test result is stable.
- **Metrics** go beyond accuracy: MAE, RMSE, MAPE, sMAPE, R², bias, P95 absolute error, and then
  the two that matter operationally — accuracy restricted to the evening peak, and
  precision/recall/F1 when the forecast is used as a stress alarm against the P95 threshold.
- **The served champion is always a tabular model.** Sequence models take a frame, not a design
  matrix; if one wins on RMSE the trainer says so in the log and still saves XGBoost as
  `best_model.joblib`, because that is what the API and replay engine can call.

`ModelBundle` stores the estimator together with its feature column order, kind, training window
and metrics, plus a JSON sidecar. The same artifact is loaded by the CLI, the dashboard, the
FastAPI service and the Azure ML online endpoint.

---

## 4. Stress detection (`drg.stress`)

Stress is defined statistically because the dataset carries no transformer ratings:

- **primary**: demand ≥ the 95th percentile of that neighbourhood's history;
- **sensitivity**: demand ≥ mean + 2 standard deviations.

Consecutive flagged half-hours collapse into **events** (minimum 2 periods = 1 hour), each carrying
duration, peak, exceedance in kWh and %, energy above threshold, season and start period. Site
summaries report frequency, hours per week, event counts and durations, peak-to-threshold ratio and
load factor; profiles break stress down by season and by half-hour of day.

By construction the primary threshold flags ~5 % of history — that is the definition, not a result.
The interesting numbers are how that 5 % moves under electrification, and *when* it occurs.

---

## 5. Electrification simulation (`drg.simulation`)

### Electric vehicles

Each adopting household owns a charger of `charger_kw` (7 kW default). Per day it plugs in with a
weekday/weekend probability, starting at a uniformly random time in the 17:00–22:00 window, for a
uniformly random 2–4 hour session that is allowed to run past the window into the night — which is
what uncontrolled domestic charging does.

Partial half-hour overlap is computed analytically, so a session starting at 18:12 contributes the
correct fraction to the 18:00 period. The whole fleet is vectorised: sessions are drawn as one
array and deposited with `np.add.at` over the at most ten periods a session can touch.

**Calibration.** A 2–4 h session at 7 kW delivers 14–28 kWh — a near-full charge. Charging *every*
day would imply ~7,600 kWh/year per car. UK average car mileage (~7,400 miles at ~3.5 miles/kWh)
implies ~2,100 kWh/year, so the default plug-in probability is ~1 day in 3. This single parameter
is the difference between a plausible study and an alarmist one; it is documented in the config and
the resulting kWh/car/day is reported in every scenario summary.

### Heat pumps

Electrical input rises with heating degrees below the balance-point temperature, is shaped by
morning and evening occupancy peaks with an overnight setback, is scaled by a per-household
efficiency spread, modulated by thermostat cycling, and is **clipped at the unit rating** — the
clip is applied after cycling, so no unit can ever draw more than it is rated for. Without a
temperature series the model degrades to a winter-seasonal proxy.

### Aggregation

Technology-specific diversity factors are applied to the aggregate, and the whole simulation is
repeated `monte_carlo_runs` times so a headline scenario carries a distribution rather than a
single draw. Each scenario reports peak amplification, energy growth, per-technology ADMD and
kWh/car/day.

---

## 6. Sensitivity analysis (`drg.analysis.sensitivity`)

The 5 × 5 adoption grid re-runs stress detection under every combination against the fixed
historical thresholds and reports peak amplification, stress frequency in percentage points and as
a multiple of the base case, event-duration growth, energy above threshold and the winter split.

`elasticity_curve` differentiates peak amplification with respect to adoption to give a marginal
"% peak per 10 percentage points" figure, and `summarise_amplification` reports the combined case
against the sum of the two single-technology cases — the two loads peak at overlapping but not
identical times, so the combination is consistently *less* than additive, which is a planning-
relevant result in itself.

---

## 7. Explainability (`drg.explain`)

TreeSHAP gives exact Shapley values for the XGBoost champion. Two views are produced:

- **global** — mean |SHAP| over a sample of the test window;
- **stress-conditional** — the same, restricted to observations above the stress threshold.

The second is the one a network planner needs: it answers "what drives the half-hours I care
about", not "what drives demand on average". A `KernelExplainer` fallback covers non-tree models.

---

## 8. Near-real-time layer (`drg.streaming`)

`StreamingReplayEngine` is pull-based and synchronous, so the CLI demo, the dashboard and the API
share one implementation. Each tick appends the newly "arrived" observation, rebuilds features from
the rolling window, issues a fresh one-step-ahead forecast, and compares **both** the observation
and the forecast to the threshold — raising a *pre-emptive* alert when the forecast breaches before
the measurement does, which is the only kind of alert with operational value.

Ticks carry severity bands (normal / watch / elevated / high / critical), headroom in kWh and %,
and optionally the live weather and carbon snapshot.

---

## 9. Serving

**FastAPI** (`drg.api`) loads the demand table, thresholds and champion model lazily behind
`lru_cache`, returns 503 with the exact CLI command to run when an artifact is missing, and
validates scenario requests with pydantic (adoption bounded to [0, 1], charger rating to 22 kW).

**Streamlit** (`drg.dashboard`) renders five panels against a validated chart theme:
a fixed categorical hue order checked for colour-vision-deficiency separation, one blue ramp for
magnitude, a reserved status palette that always ships with an icon and a label, single y-axes,
recessive grid and axes, and a data table beside every chart.

---

## 10. Azure

```
GitHub Actions ──OIDC──▶ Azure
     │
     ├─ az acr build ─────▶ Container Registry ──▶ drg-api / drg-dashboard / drg-pipeline
     └─ az deployment ────▶ Container Apps environment
                              ├── drg-api        (scale-to-zero, health probes)
                              ├── drg-dashboard  (sticky sessions)
                              └── drg-pipeline   (nightly cron job)
                                      │
                    all three mount the same Azure Files share
                                      │
                              Storage (ADLS Gen2 + Files)
                              Key Vault ── secrets by managed identity
                              Log Analytics + Application Insights
                              Azure ML workspace (optional managed training)
```

Design choices worth noting:

- **Container Apps over AKS** — the workload is three small services and a nightly batch job;
  scale-to-zero and a cron job type cover it without a cluster to operate.
- **One shared Azure Files volume** — the batch job writes data and models; the API and dashboard
  read them immediately. No separate model-sync step.
- **Managed identity everywhere** — ACR pull, blob/file access and Key Vault secret references all
  go through a user-assigned identity. The only key in the template is the storage account key the
  Files mount requires.
- **ACR Tasks builds** — deployment needs no local Docker daemon, which matters for a
  Windows-first analyst workstation.
- **Azure ML is optional** (`deployMachineLearning: false` turns it off). It earns its place when
  the real Low Carbon London extract needs a compute cluster, MLflow tracking and a versioned
  model registry.

---

## 11. Known limitations

- **No power-flow modelling.** Stress is statistical. Real reinforcement decisions need transformer
  ratings and network topology, which this dataset does not carry.
- **The carbon-intensity series for 2011–2014 is a climatology proxy**, not measurements, because
  the API archive begins in 2018. It is tagged as such in the data and contributes little to the
  model (< 1 % of SHAP attribution).
- **Neighbourhood groups are hash-derived**, not geographic feeders. Real LV-feeder assignment
  would need network data.
- **Uncontrolled charging only.** Smart tariffs and managed charging would flatten these peaks
  substantially; modelling them is the natural next extension, and the EV configuration already
  isolates the parameters that would change.
