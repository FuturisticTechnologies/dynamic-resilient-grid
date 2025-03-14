"""Exploratory data analysis (proposal section 7.2).

Produces the load-curve, seasonality and peak-pattern evidence base, writing
publication-quality PNGs to ``artifacts/figures`` and a machine-readable
summary to ``artifacts/reports/eda_summary.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from drg.utils.logging_utils import get_logger  # noqa: E402

log = get_logger(__name__)

_SEASON_ORDER = ["winter", "spring", "summer", "autumn"]


def _season(month: pd.Series) -> pd.Series:
    return pd.Series(
        np.select(
            [month.isin([12, 1, 2]), month.isin([3, 4, 5]), month.isin([6, 7, 8])],
            ["winter", "spring", "summer"],
            default="autumn",
        ),
        index=month.index,
    )


def daily_load_curve(df: pd.DataFrame, value_col: str = "demand_kwh") -> pd.DataFrame:
    d = df.copy()
    d["period_of_day"] = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    d["day_type"] = np.where(d["timestamp"].dt.dayofweek >= 5, "weekend", "weekday")
    return (
        d.groupby(["neighbourhood_id", "day_type", "period_of_day"], observed=True)[value_col]
        .agg(["mean", "median", lambda s: np.percentile(s, 95)])
        .rename(columns={"<lambda_0>": "p95"})
        .reset_index()
    )


def seasonal_profile(df: pd.DataFrame, value_col: str = "demand_kwh") -> pd.DataFrame:
    d = df.copy()
    d["season"] = _season(d["timestamp"].dt.month)
    d["period_of_day"] = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    return d.groupby(["season", "period_of_day"], observed=True)[value_col].mean().reset_index()


def winter_amplification(df: pd.DataFrame, value_col: str = "demand_kwh") -> dict[str, Any]:
    d = df.copy()
    d["season"] = _season(d["timestamp"].dt.month)
    by_season = d.groupby("season", observed=True)[value_col].agg(["mean", "max"])
    summer_mean = float(by_season.loc["summer", "mean"]) if "summer" in by_season.index else np.nan
    winter_mean = float(by_season.loc["winter", "mean"]) if "winter" in by_season.index else np.nan
    return {
        "winter_mean_kwh": winter_mean,
        "summer_mean_kwh": summer_mean,
        "winter_uplift_pct": (
            float(100.0 * (winter_mean / summer_mean - 1.0)) if summer_mean else float("nan")
        ),
        "winter_peak_kwh": float(by_season.loc["winter", "max"]) if "winter" in by_season.index else np.nan,
        "summer_peak_kwh": float(by_season.loc["summer", "max"]) if "summer" in by_season.index else np.nan,
    }


def peak_pattern(df: pd.DataFrame, value_col: str = "demand_kwh", top_n: int = 50) -> pd.DataFrame:
    d = df.copy()
    d["period_of_day"] = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    top = d.sort_values(value_col, ascending=False).groupby("neighbourhood_id", observed=True).head(top_n)
    return (
        top.groupby(["neighbourhood_id", "period_of_day"], observed=True)
        .size()
        .reset_index(name="count_in_top_peaks")
    )
