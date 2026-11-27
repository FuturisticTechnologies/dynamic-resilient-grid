"""Electrification sensitivity analysis.

Sweeps the EV x heat-pump adoption grid, re-runs stress detection under each
scenario against the *fixed historical* thresholds, and quantifies:

* peak amplification (%) versus the un-electrified base case;
* stress frequency escalation (percentage points and multiple);
* stress duration escalation (mean and maximum event length);
* adoption elasticity - the marginal peak increase per 10 pp of adoption;
* the seasonal split, which isolates the winter heat-pump contribution;
* a one-at-a-time assumption sweep - each modelling assumption moved to the
  low and high end of a plausible range around a reference scenario, so the
  assumptions can be ranked by how much they move stress frequency and
  duration.
"""

from __future__ import annotations

from dataclasses import replace
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


# ===========================================================================
# one-at-a-time assumption sweep
# ===========================================================================
#: Plausible low / high values for each assumption, used when the config does
#: not override them. Adoption rates are scenario inputs; the rest are
#: equipment and behaviour parameters of the simulation.
DEFAULT_ASSUMPTION_RANGES: dict[str, tuple[float, float]] = {
    "ev_adoption": (0.2, 0.6),
    "hp_adoption": (0.15, 0.5),
    "ev.charger_kw": (3.6, 11.0),
    "ev.weekday_charge_probability": (0.2, 0.45),
    "ev.diversity_factor": (0.7, 1.0),
    "heat_pump.kw_per_degree": (0.065, 0.105),
    "heat_pump.rated_kw": (2.0, 3.5),
    "heat_pump.diversity_factor": (0.55, 0.85),
}

ASSUMPTION_LABELS: dict[str, str] = {
    "ev_adoption": "EV adoption rate",
    "hp_adoption": "Heat-pump adoption rate",
    "ev.charger_kw": "EV charger rating (kW)",
    "ev.weekday_charge_probability": "EV weekday plug-in probability",
    "ev.weekend_charge_probability": "EV weekend plug-in probability",
    "ev.diversity_factor": "EV diversity factor",
    "ev.window_start_hour": "EV plug-in window start (h)",
    "heat_pump.kw_per_degree": "Heat-pump kW per heating degree",
    "heat_pump.rated_kw": "Heat-pump rating (kW)",
    "heat_pump.base_temperature_c": "Heating base temperature (°C)",
    "heat_pump.diversity_factor": "Heat-pump diversity factor",
}

ADOPTION_ASSUMPTIONS = frozenset({"ev_adoption", "hp_adoption"})


def _with_assumption(
    name: str,
    value: float,
    ev_adoption: float,
    hp_adoption: float,
    ev_config: EVConfig,
    hp_config: HeatPumpConfig,
) -> tuple[float, float, EVConfig, HeatPumpConfig]:
    """Return the scenario inputs with one assumption moved to ``value``."""
    if name == "ev_adoption":
        return float(value), hp_adoption, ev_config, hp_config
    if name == "hp_adoption":
        return ev_adoption, float(value), ev_config, hp_config
    group, _, field_name = name.partition(".")
    if group == "ev" and field_name in EVConfig.__dataclass_fields__:  # type: ignore[attr-defined]
        return ev_adoption, hp_adoption, replace(ev_config, **{field_name: float(value)}), hp_config
    if group == "heat_pump" and field_name in HeatPumpConfig.__dataclass_fields__:  # type: ignore[attr-defined]
        return ev_adoption, hp_adoption, ev_config, replace(hp_config, **{field_name: float(value)})
    raise ValueError(f"unknown sensitivity assumption: {name!r}")


def _reference_value(
    name: str, ev_adoption: float, hp_adoption: float, ev_config: EVConfig, hp_config: HeatPumpConfig
) -> float:
    if name == "ev_adoption":
        return float(ev_adoption)
    if name == "hp_adoption":
        return float(hp_adoption)
    group, _, field_name = name.partition(".")
    return float(getattr(ev_config if group == "ev" else hp_config, field_name))


def assumption_sweep(
    base: pd.DataFrame,
    thresholds: dict[str, StressThresholds],
    *,
    reference_ev: float = 0.4,
    reference_hp: float = 0.3,
    ranges: dict[str, tuple[float, float]] | None = None,
    value_col: str = "demand_kwh",
    ev_config: EVConfig | None = None,
    hp_config: HeatPumpConfig | None = None,
    min_event_periods: int = 2,
    seed: int = 42,
    runs: int = 1,
) -> pd.DataFrame:
    """Move each assumption to its low and high value, one at a time.

    Every run uses the same seed and the same fixed historical thresholds as
    the reference scenario, so the only thing that differs between a row and
    the reference is the one assumption named on it.

    Returns one row per (assumption, setting) with setting in
    ``{"low", "reference", "high"}``.
    """
    ev_config = ev_config or EVConfig()
    hp_config = hp_config or HeatPumpConfig()
    ranges = dict(ranges or DEFAULT_ASSUMPTION_RANGES)
    for name in ranges:  # fail before any simulation runs, not halfway through
        _with_assumption(name, 0.0, reference_ev, reference_hp, ev_config, hp_config)

    def _run(ev: float, hp: float, evc: EVConfig, hpc: HeatPumpConfig) -> dict[str, Any]:
        result = apply_scenario(
            base,
            ev_adoption=ev,
            hp_adoption=hp,
            value_col=value_col,
            ev_config=evc,
            hp_config=hpc,
            seed=seed,
            runs=runs,
        )
        metrics = _scenario_metrics(result.frame, thresholds, min_event_periods)
        return {
            "peak_amplification_pct": float(result.summary["peak_amplification_pct"]),
            "stress_frequency_pct": metrics["stress_frequency_pct"],
            "mean_event_hours": metrics["mean_event_hours"],
            "stress_hours_per_week": metrics["stress_hours_per_week"],
        }

    reference = _run(reference_ev, reference_hp, ev_config, hp_config)
    rows: list[dict[str, Any]] = []
    for name, (low, high) in ranges.items():
        ref_value = _reference_value(name, reference_ev, reference_hp, ev_config, hp_config)
        meta = {
            "assumption": name,
            "label": ASSUMPTION_LABELS.get(name, name),
            "kind": "adoption" if name in ADOPTION_ASSUMPTIONS else "equipment",
        }
        rows.append({**meta, "setting": "reference", "value": ref_value, **reference})
        for setting, value in (("low", low), ("high", high)):
            ev, hp, evc, hpc = _with_assumption(name, value, reference_ev, reference_hp, ev_config, hp_config)
            rows.append({**meta, "setting": setting, "value": float(value), **_run(ev, hp, evc, hpc)})

    sweep = pd.DataFrame(rows)
    sweep["reference_ev_adoption"] = float(reference_ev)
    sweep["reference_hp_adoption"] = float(reference_hp)
    log.info("assumption sweep complete: %s assumptions", len(ranges))
    return sweep


def rank_assumptions(sweep: pd.DataFrame) -> pd.DataFrame:
    """Rank assumptions by how far they move stress frequency.

    The swing is the spread between the lowest and highest result across the
    low / reference / high settings. Stress frequency is the ranking metric;
    the duration swing is reported alongside it, with its own rank.
    """
    rows = []
    for name, sub in sweep.groupby("assumption", sort=False):
        ref = sub[sub["setting"] == "reference"].iloc[0]
        rows.append(
            {
                "assumption": name,
                "label": ref["label"],
                "kind": ref["kind"],
                "low_value": float(sub.loc[sub["setting"] == "low", "value"].iloc[0]),
                "reference_value": float(ref["value"]),
                "high_value": float(sub.loc[sub["setting"] == "high", "value"].iloc[0]),
                "stress_frequency_swing_pp": float(
                    sub["stress_frequency_pct"].max() - sub["stress_frequency_pct"].min()
                ),
                "mean_event_hours_swing": float(
                    sub["mean_event_hours"].max() - sub["mean_event_hours"].min()
                ),
                "peak_amplification_swing_pp": float(
                    sub["peak_amplification_pct"].max() - sub["peak_amplification_pct"].min()
                ),
            }
        )
    ranking = pd.DataFrame(rows).sort_values("stress_frequency_swing_pp", ascending=False)
    total = ranking["stress_frequency_swing_pp"].sum()
    ranking["share_of_total_swing_pct"] = (
        100.0 * ranking["stress_frequency_swing_pp"] / total if total else 0.0
    )
    ranking["rank"] = np.arange(1, len(ranking) + 1)
    ranking["duration_rank"] = (
        ranking["mean_event_hours_swing"].rank(ascending=False, method="min").astype(int)
    )
    return ranking.reset_index(drop=True)


def adoption_dominance(ranking: pd.DataFrame) -> dict[str, Any]:
    """Does adoption rate move stress more than any equipment assumption?"""
    adoption = ranking[ranking["kind"] == "adoption"]
    equipment = ranking[ranking["kind"] != "adoption"]
    top_adoption = float(adoption["stress_frequency_swing_pp"].max()) if len(adoption) else 0.0
    top_equipment = float(equipment["stress_frequency_swing_pp"].max()) if len(equipment) else 0.0
    return {
        "adoption_dominates": bool(len(ranking) and ranking.iloc[0]["kind"] == "adoption"),
        "top_assumption": str(ranking.iloc[0]["label"]) if len(ranking) else "",
        "top_adoption_swing_pp": top_adoption,
        "top_equipment_swing_pp": top_equipment,
        "top_equipment_assumption": (str(equipment.iloc[0]["label"]) if len(equipment) else ""),
        "adoption_share_of_total_swing_pct": float(adoption["share_of_total_swing_pct"].sum())
        if len(adoption)
        else 0.0,
    }
