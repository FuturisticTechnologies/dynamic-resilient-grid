"""Statistical stress detection.

No transformer nameplate ratings are published with the Low Carbon London
data, so "stress" is defined *statistically* against each neighbourhood own
historical distribution, exactly as set out in the proposal:

* **primary threshold** - the 95th percentile of historical demand;
* **sensitivity threshold** - mean + 2 standard deviations.

Thresholds are always estimated on a *baseline* window (the historical /
training period) and then held fixed, so that a scenario which raises demand
raises the measured stress rather than moving the goalposts with it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


@dataclass
class StressThresholds:
    neighbourhood_id: str
    percentile: float
    primary_kwh: float
    sensitivity_kwh: float
    baseline_mean_kwh: float
    baseline_std_kwh: float
    baseline_peak_kwh: float
    n_observations: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_thresholds(
    df: pd.DataFrame,
    value_col: str = "demand_kwh",
    percentile: float = 95.0,
    sigma: float = 2.0,
) -> dict[str, StressThresholds]:
    """Per-neighbourhood thresholds from a baseline window."""
    out: dict[str, StressThresholds] = {}
    for nid, sub in df.groupby("neighbourhood_id", observed=True):
        values = sub[value_col].astype(float).dropna()
        if values.empty:
            continue
        mean, std = float(values.mean()), float(values.std(ddof=1))
        out[str(nid)] = StressThresholds(
            neighbourhood_id=str(nid),
            percentile=float(percentile),
            primary_kwh=float(np.percentile(values, percentile)),
            sensitivity_kwh=float(mean + sigma * std),
            baseline_mean_kwh=mean,
            baseline_std_kwh=std,
            baseline_peak_kwh=float(values.max()),
            n_observations=int(values.size),
        )
    log.info("stress thresholds computed for %s neighbourhoods (P%s)", len(out), percentile)
    return out


def detect_stress(
    df: pd.DataFrame,
    thresholds: dict[str, StressThresholds],
    value_col: str = "demand_kwh",
) -> pd.DataFrame:
    """Flag each half-hour against both thresholds and score its severity."""
    df = df.copy()
    primary = df["neighbourhood_id"].map(lambda n: thresholds[n].primary_kwh if n in thresholds else np.nan)
    sensitivity = df["neighbourhood_id"].map(
        lambda n: thresholds[n].sensitivity_kwh if n in thresholds else np.nan
    )
    df["threshold_primary_kwh"] = primary.to_numpy()
    df["threshold_sensitivity_kwh"] = sensitivity.to_numpy()
    df["is_stress"] = (df[value_col] >= df["threshold_primary_kwh"]).astype(int)
    df["is_stress_sensitivity"] = (df[value_col] >= df["threshold_sensitivity_kwh"]).astype(int)
    df["stress_margin_kwh"] = df[value_col] - df["threshold_primary_kwh"]
    df["stress_ratio"] = df[value_col] / df["threshold_primary_kwh"].replace(0, np.nan)
    df["severity"] = pd.cut(
        df["stress_ratio"],
        bins=[-np.inf, 1.0, 1.1, 1.25, np.inf],
        labels=["normal", "elevated", "high", "critical"],
    )
    return df


def stress_events(
    flagged: pd.DataFrame,
    min_periods: int = 2,
    value_col: str = "demand_kwh",
    flag_col: str = "is_stress",
) -> pd.DataFrame:
    """Collapse consecutive flagged half-hours into discrete stress events."""
    events: list[dict[str, Any]] = []
    for nid, sub in flagged.groupby("neighbourhood_id", observed=True):
        sub = sub.sort_values("timestamp").reset_index(drop=True)
        flag = sub[flag_col].to_numpy().astype(bool)
        if not flag.any():
            continue
        # event id increments whenever a run of True starts
        breaks = np.diff(flag.astype(int), prepend=0) == 1
        event_id = np.cumsum(breaks) * flag
        for eid in np.unique(event_id[event_id > 0]):
            block = sub[event_id == eid]
            if len(block) < min_periods:
                continue
            events.append(
                {
                    "neighbourhood_id": nid,
                    "start": block["timestamp"].iloc[0],
                    "end": block["timestamp"].iloc[-1],
                    "duration_periods": int(len(block)),
                    "duration_hours": float(len(block) * 0.5),
                    "peak_kwh": float(block[value_col].max()),
                    "mean_kwh": float(block[value_col].mean()),
                    "threshold_kwh": float(block["threshold_primary_kwh"].iloc[0]),
                    "peak_exceedance_kwh": float(
                        block[value_col].max() - block["threshold_primary_kwh"].iloc[0]
                    ),
                    "peak_exceedance_pct": float(
                        100.0 * (block[value_col].max() / block["threshold_primary_kwh"].iloc[0] - 1.0)
                    ),
                    "energy_above_threshold_kwh": float(block["stress_margin_kwh"].clip(lower=0).sum()),
                    "season": _season_name(int(block["timestamp"].iloc[0].month)),
                    "start_period": int(
                        block["timestamp"].iloc[0].hour * 2 + block["timestamp"].iloc[0].minute // 30
                    ),
                }
            )
    if not events:
        return pd.DataFrame(
            columns=[
                "neighbourhood_id",
                "start",
                "end",
                "duration_periods",
                "duration_hours",
                "peak_kwh",
                "mean_kwh",
                "threshold_kwh",
                "peak_exceedance_kwh",
                "peak_exceedance_pct",
                "energy_above_threshold_kwh",
                "season",
                "start_period",
            ]
        )
    return pd.DataFrame(events).sort_values(["neighbourhood_id", "start"]).reset_index(drop=True)


def _season_name(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def stress_summary(
    flagged: pd.DataFrame,
    events: pd.DataFrame | None = None,
    value_col: str = "demand_kwh",
) -> pd.DataFrame:
    """Per-neighbourhood stress frequency, duration and intensity metrics."""
    rows: list[dict[str, Any]] = []
    for nid, sub in flagged.groupby("neighbourhood_id", observed=True):
        n = len(sub)
        stress = sub[sub["is_stress"] == 1]
        ev = events[events["neighbourhood_id"] == nid] if events is not None and len(events) else None
        span_days = max((sub["timestamp"].max() - sub["timestamp"].min()).total_seconds() / 86400.0, 1.0)
        rows.append(
            {
                "neighbourhood_id": nid,
                "n_periods": n,
                "stress_periods": int(len(stress)),
                "stress_frequency_pct": float(100.0 * len(stress) / n) if n else 0.0,
                "stress_hours": float(0.5 * len(stress)),
                "stress_hours_per_week": float(0.5 * len(stress) / span_days * 7.0),
                "sensitivity_stress_pct": float(100.0 * sub["is_stress_sensitivity"].sum() / n) if n else 0.0,
                "peak_kwh": float(sub[value_col].max()),
                "mean_kwh": float(sub[value_col].mean()),
                "threshold_kwh": float(sub["threshold_primary_kwh"].iloc[0]),
                "peak_to_threshold_ratio": float(sub[value_col].max() / sub["threshold_primary_kwh"].iloc[0]),
                "load_factor": (
                    float(sub[value_col].mean() / sub[value_col].max()) if sub[value_col].max() else np.nan
                ),
                "energy_above_threshold_kwh": float(sub["stress_margin_kwh"].clip(lower=0).sum()),
                "n_events": int(len(ev)) if ev is not None else np.nan,
                "mean_event_hours": float(ev["duration_hours"].mean()) if ev is not None and len(ev) else 0.0,
                "max_event_hours": float(ev["duration_hours"].max()) if ev is not None and len(ev) else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("neighbourhood_id").reset_index(drop=True)


def seasonal_stress_profile(flagged: pd.DataFrame) -> pd.DataFrame:
    """Stress frequency by season and by half-hour of day."""
    df = flagged.copy()
    df["season"] = df["timestamp"].dt.month.map(_season_name)
    df["period_of_day"] = df["timestamp"].dt.hour * 2 + df["timestamp"].dt.minute // 30
    by_season = (
        df.groupby(["neighbourhood_id", "season"], observed=True)["is_stress"]
        .agg(["mean", "sum", "count"])
        .reset_index()
        .rename(columns={"mean": "stress_rate", "sum": "stress_periods", "count": "n_periods"})
    )
    by_season["stress_rate"] *= 100.0
    return by_season


def diurnal_stress_profile(flagged: pd.DataFrame) -> pd.DataFrame:
    df = flagged.copy()
    df["period_of_day"] = df["timestamp"].dt.hour * 2 + df["timestamp"].dt.minute // 30
    return (
        df.groupby(["neighbourhood_id", "period_of_day"], observed=True)["is_stress"]
        .mean()
        .mul(100.0)
        .reset_index()
        .rename(columns={"is_stress": "stress_rate_pct"})
    )
