"""Streaming replay, external API clients and the FastAPI service."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from drg.data.external_apis import (
    _carbon_climatology,
    _synthetic_carbon,
    build_carbon_intensity_series,
    build_temperature_series,
)
from drg.features.engineering import build_feature_table, feature_columns
from drg.models.gbm import XGBoostForecaster
from drg.models.registry import ModelBundle
from drg.streaming.replay import StreamingReplayEngine, _severity
from drg.stress.detection import compute_thresholds


# ------------------------------------------------------------- offline APIs
def test_carbon_series_falls_back_offline(small_index):
    frame = build_carbon_intensity_series(small_index, allow_network=False)
    assert len(frame) == len(small_index)
    assert frame["source"].eq("synthetic").all()
    assert frame["carbon_intensity_gco2_kwh"].between(40, 520).all()


def test_temperature_series_falls_back_offline(small_index):
    frame = build_temperature_series(small_index, latitude=51.5, longitude=-0.13, allow_network=False)
    assert len(frame) == len(small_index)
    assert frame["source"].eq("synthetic").all()
    assert frame["temperature_c"].between(-25, 45).all()


def test_carbon_climatology_shape(small_index):
    reference = pd.DataFrame(
        {
            "timestamp": small_index,
            "carbon_intensity_gco2_kwh": _synthetic_carbon(small_index).to_numpy(),
        }
    )
    clim = _carbon_climatology(reference)
    assert set(clim.columns) == {"month", "period", "carbon_intensity_gco2_kwh"}
    assert clim["period"].between(0, 47).all()


# ---------------------------------------------------------------- severity
@pytest.mark.parametrize(
    "ratio,expected",
    [(1.4, "critical"), (1.15, "high"), (1.02, "elevated"), (0.95, "watch"), (0.5, "normal")],
)
def test_severity_bands(ratio, expected):
    assert _severity(ratio) == expected


# ----------------------------------------------------------------- replay
@pytest.fixture(scope="module")
def replay_engine(cfg, demand):
    table = build_feature_table(demand, cfg)
    cols = feature_columns(table)
    model = XGBoostForecaster(n_estimators=80, max_depth=4).fit(table[cols], table["target"].to_numpy())
    bundle = ModelBundle(name="test_gbm", estimator=model, feature_columns=cols, kind="xgboost")
    thresholds = compute_thresholds(demand)
    return StreamingReplayEngine(
        demand, bundle, thresholds, cfg, neighbourhood_id="N01", carbon=pd.DataFrame()
    )


def test_replay_tick_payload(replay_engine):
    tick = replay_engine.tick()
    assert tick.neighbourhood_id == "N01"
    assert tick.forecast_timestamp == tick.timestamp + pd.Timedelta(minutes=30)
    assert tick.forecast_next_kwh >= 0
    assert np.isfinite(tick.threshold_kwh)
    assert tick.severity in {"normal", "watch", "elevated", "high", "critical"}
    assert len(tick.window) <= replay_engine.window_periods


def test_replay_advances_and_is_writable(replay_engine):
    replay_engine.reset()
    frame = replay_engine.run(n=24)
    assert len(frame) == 24
    assert frame["timestamp"].is_monotonic_increasing
    assert "context" not in frame.columns  # empty dicts dropped for parquet
    assert frame["forecast_next_kwh"].notna().all()


def test_replay_forecast_tracks_the_series(replay_engine):
    replay_engine.reset()
    frame = replay_engine.run(n=96)
    actual_next = frame["actual_kwh"].shift(-1).dropna()
    predicted = frame["forecast_next_kwh"].iloc[:-1]
    mape = np.mean(np.abs((actual_next - predicted.to_numpy()) / actual_next)) * 100
    assert mape < 20.0, f"one-step replay MAPE too high: {mape:.1f}%"


def test_replay_requires_enough_history(cfg, demand):
    short = demand.head(50)
    with pytest.raises(ValueError, match="periods of history"):
        StreamingReplayEngine(short, None, {}, cfg, neighbourhood_id="N01")


# -------------------------------------------------------------- FastAPI
def test_api_health_endpoint():
    from fastapi.testclient import TestClient

    from drg.api.main import app

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "version" in body


def test_api_scenario_endpoint_when_data_present():
    from fastapi.testclient import TestClient

    from drg.api.main import app, cfg

    if not cfg.paths.neighbourhood_demand.exists():
        pytest.skip("processed demand not built; run `python -m drg.cli ingest`")

    with TestClient(app) as client:
        response = client.post(
            "/scenario",
            json={"ev_adoption": 0.4, "hp_adoption": 0.3, "days": 30, "monte_carlo_runs": 1},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["peak_amplification_pct"] > 0
        assert len(body["profile"]) == 48


def test_api_rejects_out_of_range_adoption():
    from fastapi.testclient import TestClient

    from drg.api.main import app

    with TestClient(app) as client:
        assert client.post("/scenario", json={"ev_adoption": 1.7}).status_code == 422
