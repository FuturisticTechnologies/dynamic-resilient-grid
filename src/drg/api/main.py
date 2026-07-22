"""FastAPI decision-support service.

Endpoints (matching the JSON API surface in the proposal architecture):

    GET  /health              liveness / readiness for Azure Container Apps
    GET  /context             live weather + carbon intensity
    GET  /neighbourhoods      configured sites and their stress thresholds
    GET  /forecast            rolling one-step-ahead forecast + stress alert
    GET  /stress              historical stress summary
    POST /scenario            on-demand EV / heat-pump scenario evaluation
    GET  /sensitivity         cached adoption sensitivity grid
    GET  /explain             SHAP driver ranking for the champion model
    GET  /metrics             model evaluation metrics
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from drg import __version__
from drg.config import get_config
from drg.data.external_apis import fetch_context_snapshot
from drg.models.registry import ModelBundle, load_best
from drg.simulation.electrification import EVConfig, HeatPumpConfig, apply_scenario
from drg.streaming.replay import StreamingReplayEngine
from drg.stress.detection import (
    StressThresholds,
    compute_thresholds,
    detect_stress,
    stress_events,
    stress_summary,
)
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)
cfg = get_config()

app = FastAPI(
    title=cfg.api.get("title", "DRG Decision Support API"),
    version=__version__,
    description=(
        "Dynamic Resilient Grid: neighbourhood demand forecasting, statistical "
        "stress detection and electrification scenario analysis."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ===========================================================================
# lazily-loaded state
# ===========================================================================
@lru_cache(maxsize=1)
def _demand() -> pd.DataFrame:
    path = cfg.paths.neighbourhood_demand
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="Processed demand not found. Run: python -m drg.cli ingest",
        )
    return pd.read_parquet(path)


@lru_cache(maxsize=1)
def _thresholds() -> dict[str, StressThresholds]:
    return compute_thresholds(
        _demand(),
        percentile=float(cfg.stress.get("primary_percentile", 95)),
        sigma=float(cfg.stress.get("sensitivity_sigma", 2.0)),
    )


@lru_cache(maxsize=1)
def _bundle() -> ModelBundle:
    try:
        return load_best(cfg.paths.model_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _read_json(path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ===========================================================================
# schemas
# ===========================================================================
class ScenarioRequest(BaseModel):
    ev_adoption: float = Field(0.4, ge=0.0, le=1.0, description="Share of households with an EV")
    hp_adoption: float = Field(0.3, ge=0.0, le=1.0, description="Share with a heat pump")
    neighbourhood_id: str | None = Field(None, description="Restrict to one site")
    days: int = Field(90, ge=7, le=730, description="Length of the evaluation window")
    monte_carlo_runs: int = Field(1, ge=1, le=50)
    charger_kw: float | None = Field(None, gt=0, le=22)
    heat_pump_kw: float | None = Field(None, gt=0, le=15)


class ScenarioResponse(BaseModel):
    summary: dict[str, Any]
    stress: list[dict[str, Any]]
    profile: list[dict[str, Any]]


# ===========================================================================
# endpoints
# ===========================================================================
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "data_ready": cfg.paths.neighbourhood_demand.exists(),
        "model_ready": any(cfg.paths.model_dir.glob("*.joblib")),
    }


@app.get("/context")
def context() -> dict[str, Any]:
    """Live temperature and grid carbon intensity for the study location."""
    return fetch_context_snapshot(
        float(cfg.external["latitude"]),
        float(cfg.external["longitude"]),
        api_key=cfg.openweather_key,
        carbon_base_url=cfg.carbon_base_url,
        region_id=int(cfg.external.get("region_id", 13)),
        cache_dir=cfg.paths.external_dir,
    )


@app.get("/neighbourhoods")
def neighbourhoods() -> list[dict[str, Any]]:
    demand = _demand()
    out = []
    for nid, th in _thresholds().items():
        sub = demand[demand["neighbourhood_id"] == nid]
        out.append(
            {
                **th.to_dict(),
                "n_households": int(sub["n_households"].iloc[0]) if len(sub) else None,
                "first_reading": str(sub["timestamp"].min()),
                "last_reading": str(sub["timestamp"].max()),
            }
        )
    return out


@app.get("/forecast")
def forecast(
    neighbourhood_id: str | None = Query(None),
    steps: int = Query(24, ge=1, le=336, description="Half-hourly steps to replay"),
) -> dict[str, Any]:
    """Replay the most recent window and return forecasts with stress alerts."""
    demand = _demand()
    nid = neighbourhood_id or str(demand["neighbourhood_id"].iloc[0])
    if nid not in set(demand["neighbourhood_id"]):
        raise HTTPException(404, f"Unknown neighbourhood {nid}")

    site_rows = int((demand["neighbourhood_id"] == nid).sum())
    window = int(cfg.streaming.get("window_periods", 336))
    engine = StreamingReplayEngine(
        demand,
        _bundle(),
        _thresholds(),
        cfg,
        neighbourhood_id=nid,
        start_index=max(site_rows - steps - 1, window + 1),
    )
    ticks = [t.to_dict() for t in engine.stream(n=steps)]
    stressed = [t for t in ticks if t["is_stress"] or t["forecast_is_stress"]]
    return {
        "neighbourhood_id": nid,
        "model": _bundle().name,
        "threshold_kwh": ticks[0]["threshold_kwh"] if ticks else None,
        "n_alerts": len(stressed),
        "ticks": ticks,
    }


@app.get("/stress")
def stress(neighbourhood_id: str | None = Query(None)) -> dict[str, Any]:
    demand = _demand()
    if neighbourhood_id:
        demand = demand[demand["neighbourhood_id"] == neighbourhood_id]
        if demand.empty:
            raise HTTPException(404, f"Unknown neighbourhood {neighbourhood_id}")
    flagged = detect_stress(demand, _thresholds())
    events = stress_events(flagged, min_periods=int(cfg.stress.get("min_event_periods", 2)))
    summary = stress_summary(flagged, events)
    return {
        "summary": summary.to_dict(orient="records"),
        "recent_events": events.tail(20).astype({"start": str, "end": str}).to_dict(orient="records"),
        "n_events": int(len(events)),
    }


@app.post("/scenario", response_model=ScenarioResponse)
def scenario(req: ScenarioRequest) -> ScenarioResponse:
    """Evaluate an EV / heat-pump adoption scenario on demand."""
    demand = _demand()
    if req.neighbourhood_id:
        demand = demand[demand["neighbourhood_id"] == req.neighbourhood_id]
        if demand.empty:
            raise HTTPException(404, f"Unknown neighbourhood {req.neighbourhood_id}")

    cutoff = demand["timestamp"].max() - pd.Timedelta(days=req.days)
    window = demand[demand["timestamp"] >= cutoff]

    ev_cfg = EVConfig.from_config(cfg.electrification["ev"])
    hp_cfg = HeatPumpConfig.from_config(cfg.electrification["heat_pump"])
    if req.charger_kw:
        ev_cfg.charger_kw = req.charger_kw
    if req.heat_pump_kw:
        hp_cfg.rated_kw = req.heat_pump_kw

    result = apply_scenario(
        window,
        req.ev_adoption,
        req.hp_adoption,
        ev_config=ev_cfg,
        hp_config=hp_cfg,
        seed=cfg.seed,
        runs=req.monte_carlo_runs,
    )
    flagged = detect_stress(result.frame, _thresholds(), value_col="electrified_kwh")
    events = stress_events(
        flagged,
        min_periods=int(cfg.stress.get("min_event_periods", 2)),
        value_col="electrified_kwh",
    )
    summary = stress_summary(flagged, events, value_col="electrified_kwh")

    profile = (
        result.frame.assign(
            period_of_day=lambda d: d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
        )
        .groupby("period_of_day")[["base_kwh", "ev_kwh", "heat_pump_kwh", "electrified_kwh"]]
        .mean()
        .round(3)
        .reset_index()
    )
    return ScenarioResponse(
        summary=result.summary,
        stress=summary.replace({np.nan: None}).to_dict(orient="records"),
        profile=profile.to_dict(orient="records"),
    )


@app.get("/sensitivity")
def sensitivity() -> dict[str, Any]:
    path = cfg.paths.sensitivity_output
    if not path.exists():
        raise HTTPException(503, "Sensitivity grid not built. Run: python -m drg.cli scenarios")
    grid = pd.read_parquet(path)
    return {
        "grid": grid.replace({np.nan: None}).to_dict(orient="records"),
        "headline": _read_json(cfg.paths.report_dir / "sensitivity_summary.json"),
    }


@app.get("/explain")
def explain(top: int = Query(15, ge=1, le=60)) -> dict[str, Any]:
    payload = _read_json(cfg.paths.report_dir / "shap_summary.json")
    if payload is None:
        raise HTTPException(503, "SHAP report not built. Run: python -m drg.cli explain")
    payload["top_global_drivers"] = payload.get("top_global_drivers", [])[:top]
    payload["top_stress_drivers"] = payload.get("top_stress_drivers", [])[:top]
    return payload


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    payload = _read_json(cfg.paths.metrics_output)
    if payload is None:
        raise HTTPException(503, "Model metrics not found. Run: python -m drg.cli train")
    return payload
