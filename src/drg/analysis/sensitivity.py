"""Electrification sensitivity analysis.

Sweeps the EV x heat-pump adoption grid, re-runs stress detection under each
scenario against the *fixed historical* thresholds, and quantifies:

* peak amplification (%) versus the un-electrified base case;
* stress frequency escalation (percentage points and multiple);
* stress duration escalation (mean and maximum event length);
* adoption elasticity - the marginal peak increase per 10 pp of adoption;
* the seasonal split, which isolates the winter heat-pump contribution.
"""

from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from drg.simulation.electrification import (
    EVConfig,
    HeatPumpConfig,
    apply_scenario,
)
from drg.stress.detection import (
    StressThresholds,
    detect_stress,
    stress_events,
    stress_summary,
)
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


def _scenario_metrics(
    frame: pd.DataFrame,
    thresholds: dict[str, StressThresholds],
    min_event_periods: int,
) -> dict[str, Any]:
    flagged = detect_stress(frame, thresholds, value_col="electrified_kwh")
    events = stress_events(flagged, min_periods=min_event_periods, value_col="electrified_kwh")
    summary = stress_summary(flagged, events, value_col="electrified_kwh")

    winter = flagged[flagged["timestamp"].dt.month.isin([12, 1, 2])]
    return {
        "stress_frequency_pct": float(summary["stress_frequency_pct"].mean()),
        "stress_hours_per_week": float(summary["stress_hours_per_week"].mean()),
        "n_stress_events": int(summary["n_events"].fillna(0).sum()),
        "mean_event_hours": float(summary["mean_event_hours"].mean()),
        "max_event_hours": float(summary["max_event_hours"].max()) if len(summary) else 0.0,
        "energy_above_threshold_kwh": float(summary["energy_above_threshold_kwh"].sum()),
        "winter_stress_frequency_pct": (
            float(100.0 * winter["is_stress"].mean()) if len(winter) else float("nan")
        ),
        "sensitivity_stress_pct": float(summary["sensitivity_stress_pct"].mean()),
        "peak_to_threshold_ratio": float(summary["peak_to_threshold_ratio"].max()),
    }


def run_sensitivity_grid(
    base: pd.DataFrame,
    thresholds: dict[str, StressThresholds],
    *,
    ev_levels: list[float],
    hp_levels: list[float],
    value_col: str = "demand_kwh",
    ev_config: EVConfig | None = None,
    hp_config: HeatPumpConfig | None = None,
    min_event_periods: int = 2,
    seed: int = 42,
    runs: int = 1,
    keep_frames: bool = False,
) -> tuple[pd.DataFrame, dict[tuple[float, float], pd.DataFrame]]:
    """Evaluate every (EV, heat pump) adoption combination.

    Returns the tidy results table and, optionally, the per-scenario demand
    frames (used by the dashboard for profile comparison).
    """
    rows: list[dict[str, Any]] = []
    frames: dict[tuple[float, float], pd.DataFrame] = {}

    base_case: dict[str, Any] | None = None
    for ev, hp in product(sorted(ev_levels), sorted(hp_levels)):
        result = apply_scenario(
            base,
            ev_adoption=ev,
            hp_adoption=hp,
            value_col=value_col,
            ev_config=ev_config,
            hp_config=hp_config,
            seed=seed,
            runs=runs,
        )
        metrics = {**result.summary, **_scenario_metrics(result.frame, thresholds, min_event_periods)}
        metrics["scenario"] = f"EV{int(ev * 100)}_HP{int(hp * 100)}"
        if ev == 0.0 and hp == 0.0:
            base_case = metrics
        rows.append(metrics)
        if keep_frames:
            frames[(ev, hp)] = result.frame

    grid = pd.DataFrame(rows)

    if base_case is not None:
        ref_freq = base_case["stress_frequency_pct"] or np.nan
        ref_peak = base_case["electrified_peak_kwh"]
        grid["stress_frequency_delta_pp"] = grid["stress_frequency_pct"] - base_case["stress_frequency_pct"]
        grid["stress_escalation_x"] = grid["stress_frequency_pct"] / ref_freq
        grid["peak_amplification_pct"] = 100.0 * (grid["electrified_peak_kwh"] / ref_peak - 1.0)
        grid["event_duration_growth_x"] = grid["mean_event_hours"] / (base_case["mean_event_hours"] or np.nan)
    grid["total_adoption"] = grid["ev_adoption"] + grid["hp_adoption"]
    log.info("sensitivity grid complete: %s scenarios", len(grid))
    return grid.sort_values(["ev_adoption", "hp_adoption"]).reset_index(drop=True), frames


def elasticity_curve(grid: pd.DataFrame, hold: str = "hp_adoption") -> pd.DataFrame:
    """Marginal peak amplification per 10 percentage points of adoption."""
    vary = "ev_adoption" if hold == "hp_adoption" else "hp_adoption"
    out = []
    for held_value, sub in grid.groupby(hold):
        sub = sub.sort_values(vary)
        peak = sub["peak_amplification_pct"].to_numpy()
        adoption = sub[vary].to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            slope = np.gradient(peak, adoption) if len(adoption) > 1 else np.zeros_like(peak)
        out.append(
            pd.DataFrame(
                {
                    hold: held_value,
                    vary: adoption,
                    "peak_amplification_pct": peak,
                    "elasticity_pct_per_10pp": slope / 10.0,
                    "stress_frequency_pct": sub["stress_frequency_pct"].to_numpy(),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def summarise_amplification(grid: pd.DataFrame) -> dict[str, Any]:
    """Headline numbers for the report and the dashboard KPI row."""
    base = grid[(grid["ev_adoption"] == 0) & (grid["hp_adoption"] == 0)]
    worst = grid.loc[grid["peak_amplification_pct"].idxmax()]
    ev_only = grid[grid["hp_adoption"] == 0].sort_values("ev_adoption")
    hp_only = grid[grid["ev_adoption"] == 0].sort_values("hp_adoption")
    base_peak = float(base["electrified_peak_kwh"].iloc[0]) if len(base) else float("nan")
    base_freq = float(base["stress_frequency_pct"].iloc[0]) if len(base) else float("nan")
    return {
        "base_peak_kwh": base_peak,
        "base_stress_frequency_pct": base_freq,
        "worst_case_scenario": str(worst["scenario"]),
        "worst_case_peak_amplification_pct": float(worst["peak_amplification_pct"]),
        "worst_case_stress_frequency_pct": float(worst["stress_frequency_pct"]),
        "worst_case_stress_escalation_x": float(worst.get("stress_escalation_x", np.nan)),
        "worst_case_mean_event_hours": float(worst["mean_event_hours"]),
        "ev_only_max_amplification_pct": float(ev_only["peak_amplification_pct"].max()),
        "hp_only_max_amplification_pct": float(hp_only["peak_amplification_pct"].max()),
        "combined_vs_additive_pp": float(
            worst["peak_amplification_pct"]
            - (ev_only["peak_amplification_pct"].max() + hp_only["peak_amplification_pct"].max())
        ),
        "n_scenarios": int(len(grid)),
    }
