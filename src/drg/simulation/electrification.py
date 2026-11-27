"""Bottom-up EV and heat-pump electrification simulation.

Both technologies are simulated at *household* level and then aggregated, so
the resulting neighbourhood profile carries a realistic diversity effect
rather than a flat multiplier:

**Electric vehicles** - each adopting household owns a 7 kW single-phase
charger. On any given day it plugs in with a weekday/weekend probability, at a
uniformly random start time inside the evening window (17:00-22:00), for a
uniformly random 2-4 hour session. Sessions that overrun the window continue
into the night, exactly as uncontrolled domestic charging does. Partial
half-hour overlap is accounted for analytically, so a session starting at
18:12 contributes the correct fraction to the 18:00 period.

**Heat pumps** - a thermally driven load: electrical input rises with heating
degrees below the balance-point temperature, is shaped by the morning and
evening occupancy peaks, and is capped at the unit rated input. When the
temperature series is unavailable the model degrades to a winter-seasonal
proxy.

Aggregate profiles apply a technology-specific *diversity factor*, and the
whole simulation is repeated ``monte_carlo_runs`` times so the reported
scenario carries a mean and an uncertainty band rather than a single draw.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from drg.simulation.household import (
    HOURS_PER_PERIOD,
    PERIODS_PER_DAY,
    simulate_neighbourhood_load,
)
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

__all__ = [
    "EVConfig",
    "HeatPumpConfig",
    "ScenarioResult",
    "simulate_ev_load",
    "simulate_heat_pump_load",
    "apply_scenario",
    "HOURS_PER_PERIOD",
    "PERIODS_PER_DAY",
]


# ===========================================================================
# configuration
# ===========================================================================
@dataclass
class EVConfig:
    charger_kw: float = 7.0
    window_start_hour: float = 17.0
    window_end_hour: float = 22.0
    min_duration_h: float = 2.0
    max_duration_h: float = 4.0
    weekday_charge_probability: float = 0.32
    weekend_charge_probability: float = 0.24
    diversity_factor: float = 0.85

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "EVConfig":
        fields = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in cfg.items() if k in fields})


@dataclass
class HeatPumpConfig:
    rated_kw: float = 2.5
    base_temperature_c: float = 15.5
    kw_per_degree: float = 0.085
    evening_peak_hours: tuple[float, float, float, float] = (6.0, 9.0, 16.0, 22.0)
    diversity_factor: float = 0.7

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "HeatPumpConfig":
        fields = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        payload = {k: v for k, v in cfg.items() if k in fields}
        if "evening_peak_hours" in payload:
            payload["evening_peak_hours"] = tuple(payload["evening_peak_hours"])
        return cls(**payload)


@dataclass
class ScenarioResult:
    frame: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.summary[key]


def _site_seed(neighbourhood_id: object, modulus: int) -> int:
    """Process-stable per-site seed offset (``hash()`` is randomised)."""
    return int(zlib.crc32(str(neighbourhood_id).encode("utf-8")) % modulus)


# ===========================================================================
# EV
# ===========================================================================
def simulate_ev_load(
    timestamps: pd.DatetimeIndex,
    n_households: int,
    adoption: float,
    config: EVConfig | None = None,
    *,
    seed: int = 42,
    runs: int = 1,
    return_band: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Aggregate EV charging demand (kWh per half hour) on ``timestamps``.

    Simulated per household (:func:`drg.simulation.household.ev_household_profiles`)
    and summed once. ``timestamps`` must be a regular 30-minute index. Returns
    the Monte-Carlo mean profile, optionally with the 10th/90th percentile band.
    """
    load = simulate_neighbourhood_load(
        timestamps, n_households, adoption, 0.0, None, config, None, ev_seed=seed, hp_seed=seed, runs=runs
    )
    if return_band:
        lo, hi = load.band("ev")
        return load.ev_kwh, lo, hi
    return load.ev_kwh


# ===========================================================================
# heat pumps
# ===========================================================================
def simulate_heat_pump_load(
    timestamps: pd.DatetimeIndex,
    n_households: int,
    adoption: float,
    temperature_c: np.ndarray | pd.Series | None = None,
    config: HeatPumpConfig | None = None,
    *,
    seed: int = 42,
    runs: int = 1,
    return_band: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Aggregate heat-pump electrical demand (kWh per half hour).

    Simulated per household with household-specific timing
    (:func:`drg.simulation.household.heat_pump_household_profiles`) and
    summed once.
    """
    load = simulate_neighbourhood_load(
        timestamps,
        n_households,
        0.0,
        adoption,
        temperature_c,
        None,
        config,
        ev_seed=seed,
        hp_seed=seed,
        runs=runs,
    )
    if return_band:
        lo, hi = load.band("heat_pump")
        return load.heat_pump_kwh, lo, hi
    return load.heat_pump_kwh


# ===========================================================================
# scenario application
# ===========================================================================
def apply_scenario(
    df: pd.DataFrame,
    ev_adoption: float,
    hp_adoption: float,
    *,
    value_col: str = "demand_kwh",
    ev_config: EVConfig | None = None,
    hp_config: HeatPumpConfig | None = None,
    seed: int = 42,
    runs: int = 1,
    households_col: str = "n_households",
) -> ScenarioResult:
    """Add simulated EV + heat-pump load to a base demand frame.

    The input frame must contain ``timestamp``, ``neighbourhood_id``,
    ``value_col`` and ``households_col``; ``temperature_c`` is used when
    present. The returned frame adds ``ev_kwh``, ``heat_pump_kwh`` and
    ``electrified_kwh``.
    """
    frames: list[pd.DataFrame] = []
    for nid, sub in df.groupby("neighbourhood_id", observed=True, sort=True):
        sub = sub.sort_values("timestamp").copy()
        ts = pd.DatetimeIndex(sub["timestamp"])
        households = int(sub[households_col].iloc[0]) if households_col in sub else 100

        ev = simulate_ev_load(
            ts, households, ev_adoption, ev_config, seed=seed + _site_seed(nid, 997), runs=runs
        )
        hp = simulate_heat_pump_load(
            ts,
            households,
            hp_adoption,
            sub.get("temperature_c"),
            hp_config,
            seed=seed + _site_seed(nid, 991),
            runs=runs,
        )
        sub["base_kwh"] = sub[value_col].astype(float)
        sub["ev_kwh"] = ev
        sub["heat_pump_kwh"] = hp
        sub["electrified_kwh"] = sub["base_kwh"] + sub["ev_kwh"] + sub["heat_pump_kwh"]
        frames.append(sub)

    out = pd.concat(frames, ignore_index=True)
    base_peak = float(out.groupby("neighbourhood_id")["base_kwh"].max().mean())
    new_peak = float(out.groupby("neighbourhood_id")["electrified_kwh"].max().mean())

    # After-diversity maximum demand per adopting household -- the quantity UK
    # DNOs use for reinforcement planning, exposed so the simulation can be
    # checked against published ADMD figures (~1.5-2 kW for both technologies).
    households = (
        out.groupby("neighbourhood_id")[households_col].first().mean()
        if households_col in out
        else float("nan")
    )
    n_ev = households * float(ev_adoption)
    n_hp = households * float(hp_adoption)
    ev_admd = (
        float(out.groupby("timestamp")["ev_kwh"].sum().max() / out["neighbourhood_id"].nunique() / n_ev * 2.0)
        if n_ev
        else 0.0
    )
    hp_admd = (
        float(
            out.groupby("timestamp")["heat_pump_kwh"].sum().max()
            / out["neighbourhood_id"].nunique()
            / n_hp
            * 2.0
        )
        if n_hp
        else 0.0
    )

    summary = {
        "ev_adoption": float(ev_adoption),
        "hp_adoption": float(hp_adoption),
        "base_mean_kwh": float(out["base_kwh"].mean()),
        "electrified_mean_kwh": float(out["electrified_kwh"].mean()),
        "base_peak_kwh": base_peak,
        "electrified_peak_kwh": new_peak,
        "peak_amplification_pct": float(100.0 * (new_peak / base_peak - 1.0)) if base_peak else 0.0,
        "energy_growth_pct": float(100.0 * (out["electrified_kwh"].sum() / out["base_kwh"].sum() - 1.0)),
        "ev_energy_kwh": float(out["ev_kwh"].sum()),
        "heat_pump_energy_kwh": float(out["heat_pump_kwh"].sum()),
        "ev_admd_kw": ev_admd,
        "heat_pump_admd_kw": hp_admd,
        "ev_kwh_per_car_per_day": (
            float(
                out["ev_kwh"].sum()
                / out["neighbourhood_id"].nunique()
                / n_ev
                / out["timestamp"].nunique()
                * 48.0
            )
            if n_ev
            else 0.0
        ),
        "monte_carlo_runs": int(runs),
    }
    log.info(
        "scenario EV=%.0f%% HP=%.0f%% -> peak +%.1f%%, energy +%.1f%%",
        ev_adoption * 100,
        hp_adoption * 100,
        summary["peak_amplification_pct"],
        summary["energy_growth_pct"],
    )
    return ScenarioResult(frame=out, summary=summary)
