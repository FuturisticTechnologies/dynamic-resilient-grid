"""FastAPI decision-support service.

Endpoints (matching the JSON API surface in the proposal architecture):

    GET  /health              liveness / readiness for Azure Container Apps
    GET  /context             live weather + carbon intensity
    GET  /neighbourhoods      configured sites and their stress thresholds
    GET  /forecast            rolling one-step-ahead forecast + stress alert
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
# endpoints
# ===========================================================================
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
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


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    payload = _read_json(cfg.paths.metrics_output)
    if payload is None:
        raise HTTPException(503, "Model metrics not found. Run: python -m drg.cli train")
    return payload
