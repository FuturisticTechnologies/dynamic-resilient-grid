"""Data generation, cleaning and column-resolution tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from drg.data.lcl_loader import _resolve_columns, _stable_group, clean_demand
from drg.data.synthetic import generate_synthetic_neighbourhoods, synthetic_temperature


def test_synthetic_shape_and_grid(demand):
    assert {"timestamp", "neighbourhood_id", "demand_kwh", "n_households"} <= set(demand.columns)
    assert demand["neighbourhood_id"].nunique() == 2
    one = demand[demand["neighbourhood_id"] == "N01"].sort_values("timestamp")
    deltas = one["timestamp"].diff().dropna().unique()
    assert set(deltas) <= {np.timedelta64(30, "m"), np.timedelta64(60, "m")}


def test_synthetic_is_reproducible():
    a = generate_synthetic_neighbourhoods("2013-01-01", "2013-01-10", 1, 50, seed=3)
    b = generate_synthetic_neighbourhoods("2013-01-01", "2013-01-10", 1, 50, seed=3)
    pd.testing.assert_frame_equal(a, b)


def test_synthetic_has_evening_peak_and_winter_uplift():
    df = generate_synthetic_neighbourhoods("2013-01-01", "2013-12-31", 1, 100, seed=5)
    df = df.dropna(subset=["demand_kwh"])
    period = df["timestamp"].dt.hour * 2 + df["timestamp"].dt.minute // 30
    profile = df.groupby(period)["demand_kwh"].mean()
    assert 32 <= profile.idxmax() <= 42, "peak must fall in the 16:00-21:00 evening window"

    month = df["timestamp"].dt.month
    winter = df[month.isin([12, 1, 2])]["demand_kwh"].mean()
    summer = df[month.isin([6, 7, 8])]["demand_kwh"].mean()
    assert winter > summer * 1.05, "winter demand must exceed summer demand"


def test_synthetic_accepts_observed_temperature(small_index):
    temp = pd.Series(np.full(len(small_index), -5.0), index=small_index)
    cold = generate_synthetic_neighbourhoods("2014-01-01", "2014-01-15", 1, 100, seed=1, temperature=temp)
    mild = generate_synthetic_neighbourhoods(
        "2014-01-01",
        "2014-01-15",
        1,
        100,
        seed=1,
        temperature=pd.Series(np.full(len(small_index), 18.0), index=small_index),
    )
    assert cold["demand_kwh"].mean() > mild["demand_kwh"].mean()


def test_temperature_series_is_seasonal():
    index = pd.date_range("2013-01-01", "2013-12-31", freq="30min", inclusive="left")
    temp = synthetic_temperature(index, seed=1)
    jan = temp[temp.index.month == 1].mean()
    jul = temp[temp.index.month == 7].mean()
    assert jul > jan + 5


def test_stable_group_is_deterministic():
    assert _stable_group("MAC000123", 4) == _stable_group("MAC000123", 4)
    assignments = {_stable_group(f"MAC{i:06d}", 4) for i in range(200)}
    assert assignments == {0, 1, 2, 3}


def test_resolve_columns_tolerates_published_spellings():
    mapping = {
        "household_id": "LCLid",
        "timestamp": "DateTime",
        "energy_kwh": "KWH/hh (per half hour) ",
    }
    resolved = _resolve_columns(["LCLid", "stdorToU", "DateTime", "KWH/hh (per half hour) "], mapping)
    assert resolved["energy_kwh"] == "KWH/hh (per half hour) "

    # different casing / trailing space stripped by the publisher
    resolved = _resolve_columns(["lclid", "datetime", "kwh/hh"], mapping)
    assert resolved["household_id"] == "lclid"
    assert resolved["energy_kwh"] == "kwh/hh"


def test_clean_demand_repairs_gaps_and_clips_outliers(cfg):
    index = pd.date_range("2014-01-01", periods=480, freq="30min")
    values = np.full(len(index), 10.0)
    values[100] = 5000.0  # spike
    df = pd.DataFrame(
        {
            "timestamp": index,
            "neighbourhood_id": "N01",
            "demand_kwh": values,
            "n_households": 50,
        }
    )
    df = df.drop(index=[200, 201])  # short gap to interpolate

    out = clean_demand(df, cfg)
    assert out["demand_kwh"].max() < 5000.0, "spike must be clipped"
    assert len(out) == len(index), "short gaps must be interpolated back in"
    assert out["demand_kwh"].notna().all()
