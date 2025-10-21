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
