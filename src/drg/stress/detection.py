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
