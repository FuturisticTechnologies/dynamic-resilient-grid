"""Feature engineering, leakage and model tests."""

from __future__ import annotations

import numpy as np
import pytest

from drg.features.engineering import (
    add_calendar_features,
    add_lag_features,
    build_feature_table,
    chronological_split,
    feature_columns,
)
from drg.models.baseline import BaselineForecaster, SeasonalNaiveForecaster
from drg.models.evaluate import evaluate_forecast
from drg.models.gbm import XGBoostForecaster
from drg.models.registry import ModelBundle, load_model, save_model


def test_calendar_features(demand):
    df = add_calendar_features(demand.copy())
    assert df["period_of_day"].between(0, 47).all()
    assert set(df["is_weekend"].unique()) <= {0, 1}
    assert np.allclose(df["sin_period"] ** 2 + df["cos_period"] ** 2, 1.0)
    saturday = df[df["timestamp"].dt.dayofweek == 5]
    assert (saturday["is_weekend"] == 1).all()


def test_lag_features_do_not_leak(demand):
    df = demand.copy().sort_values(["neighbourhood_id", "timestamp"]).reset_index(drop=True)
    df = add_lag_features(df, lags=[1, 48], rolling_windows=[6], target="demand_kwh")

    one = df[df["neighbourhood_id"] == "N01"].reset_index(drop=True)
    # lag_1 at row i must equal the observation at row i-1
    assert np.allclose(one["lag_1"].iloc[1:10], one["demand_kwh"].iloc[0:9])
    # rolling statistics are built from shifted values only
    expected = one["demand_kwh"].shift(1).rolling(6, min_periods=2).mean().iloc[10]
    assert one["roll_mean_6"].iloc[10] == pytest.approx(expected)


def test_lags_never_cross_neighbourhood_boundaries(demand):
    df = demand.copy().sort_values(["neighbourhood_id", "timestamp"]).reset_index(drop=True)
    df = add_lag_features(df, lags=[1], rolling_windows=[6], target="demand_kwh")
    first_rows = df.groupby("neighbourhood_id").head(1)
    assert first_rows["lag_1"].isna().all()


def test_feature_table_and_split(cfg, demand):
    table = build_feature_table(demand, cfg)
    assert "target" in table.columns
    assert not table[[c for c in table.columns if c.startswith("lag_")]].isna().any().any()

    cols = feature_columns(table)
    assert "demand_kwh" not in cols, "the raw target must never be a model input"
    assert "target" not in cols
    assert "lag_1" in cols and "period_of_day" in cols

    train, val, test = chronological_split(table, test_days=14, val_days=7)
    assert train["timestamp"].max() < val["timestamp"].min()
    assert val["timestamp"].max() < test["timestamp"].min()


def test_evaluate_forecast_metrics():
    y = np.array([10.0, 20.0, 30.0, 40.0])
    perfect = evaluate_forecast(y, y, label="perfect")
    assert perfect["mae"] == 0 and perfect["rmse"] == 0
    assert perfect["r2"] == pytest.approx(1.0)

    off = evaluate_forecast(y, y + 2.0, label="biased")
    assert off["mae"] == pytest.approx(2.0)
    assert off["bias"] == pytest.approx(-2.0)


def test_stress_alarm_metrics():
    y_true = np.array([1.0, 5.0, 9.0, 2.0])
    y_pred = np.array([1.0, 6.0, 3.0, 2.0])
    out = evaluate_forecast(y_true, y_pred, stress_threshold=4.0)
    assert out["stress_tp"] == 1  # 5 -> 6, both above
    assert out["stress_fn"] == 1  # 9 predicted as 3
    assert out["stress_tn"] == 2


def test_model_ladder_beats_naive(cfg, demand):
    table = build_feature_table(demand, cfg)
    cols = feature_columns(table)
    train, _, test = chronological_split(table, test_days=10, val_days=5)

    naive = SeasonalNaiveForecaster().fit(train)
    naive_rmse = evaluate_forecast(test["target"], naive.predict(test))["rmse"]

    ridge = BaselineForecaster(ridge=True).fit(train[cols], train["target"].to_numpy())
    ridge_rmse = evaluate_forecast(test["target"], ridge.predict(test[cols]))["rmse"]

    gbm = XGBoostForecaster(n_estimators=120, max_depth=5).fit(train[cols], train["target"].to_numpy())
    gbm_rmse = evaluate_forecast(test["target"], gbm.predict(test[cols]))["rmse"]

    assert ridge_rmse < naive_rmse
    assert gbm_rmse < naive_rmse
    assert (gbm.predict(test[cols]) >= 0).all(), "demand forecasts must be non-negative"


def test_feature_importance_names_are_real_features(cfg, demand):
    table = build_feature_table(demand, cfg)
    cols = feature_columns(table)
    gbm = XGBoostForecaster(n_estimators=60, max_depth=4).fit(table[cols], table["target"].to_numpy())
    importance = gbm.feature_importance()
    assert set(importance["feature"]) <= set(cols)
    assert importance["importance_pct"].sum() == pytest.approx(100.0, abs=1e-6)


def test_model_bundle_roundtrip(tmp_path, cfg, demand):
    table = build_feature_table(demand, cfg)
    cols = feature_columns(table)
    gbm = XGBoostForecaster(n_estimators=40, max_depth=3).fit(table[cols], table["target"].to_numpy())
    bundle = ModelBundle(name="t", estimator=gbm, feature_columns=cols, kind="xgboost")
    path = save_model(bundle, tmp_path)
    restored = load_model(path)
    assert restored.feature_columns == cols
    assert np.allclose(restored.predict(table[cols].head(20)), gbm.predict(table[cols].head(20)))
    assert path.with_suffix(".json").exists()


def test_sequence_mlp_runs(cfg, demand):
    from drg.models.deep import SequenceMLPForecaster

    table = build_feature_table(demand, cfg)
    cols = feature_columns(table)
    train, _, test = chronological_split(table, test_days=7, val_days=3)
    model = SequenceMLPForecaster(sequence_length=24, hidden_layer_sizes=(32,), max_iter=8)
    model.fit(train, cols, "target")
    preds = model.predict(test, target_col="target")
    assert len(preds) == len(test)
    assert np.isfinite(preds).all() and (preds >= 0).all()
