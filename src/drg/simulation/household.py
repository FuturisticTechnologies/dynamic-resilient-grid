"""Household-level electrification load, superimposed then aggregated once (DRG-80).

Peak diversity only exists between households: two neighbours' EV sessions and
heat-pump cycles rarely line up to the half-hour. Any step that sums a
technology over the neighbourhood *before* the technologies are combined
throws those time offsets away, and the combined EV + heat-pump peak then
comes out (almost exactly) additive -- which is not what happens physically.

This module therefore keeps every simulated load as a ``(periods, households)``
matrix:

1. adopters are drawn per household, independently per technology, so a
   household can own an EV, a heat pump, both or neither;
2. each technology is simulated per household at half-hourly resolution with
   its own household-specific timing;
3. the household profiles are **superimposed per household**, and
4. the neighbourhood total is formed **once, at the end**.

Per-technology neighbourhood series are still reported, but only as an
attribution of the same draws; they are never re-combined into the total.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

if TYPE_CHECKING:  # configs live with the public API; avoid an import cycle
    from drg.simulation.electrification import EVConfig, HeatPumpConfig

log = get_logger(__name__)

PERIODS_PER_DAY = 48
HOURS_PER_PERIOD = 0.5


# ===========================================================================
# adopters
# ===========================================================================
def adopter_mask(n_households: int, adoption: float, rng: np.random.Generator) -> np.ndarray:
    """Boolean mask of the households that adopt a technology.

    ``round(n_households * adoption)`` households are drawn without
    replacement. Each technology uses its own random stream, so the EV owners
    do not depend on the heat-pump adoption level and vice versa (common
    random numbers across scenarios).
    """
    if n_households <= 0:
        return np.zeros(0, dtype=bool)
    adoption = float(np.clip(adoption, 0.0, 1.0))
    n_adopt = int(round(n_households * adoption))
    mask = np.zeros(n_households, dtype=bool)
    if n_adopt:
        mask[rng.permutation(n_households)[:n_adopt]] = True
    return mask


# ===========================================================================
# EV -- per household
# ===========================================================================
def ev_household_profiles(
    timestamps: pd.DatetimeIndex,
    owners: np.ndarray,
    cfg: EVConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    """EV charging energy (kWh per half hour) per household.

    Returns a ``(len(timestamps), len(owners))`` matrix; households without an
    EV are all zero. Each owner plugs in on a given day with the weekday /
    weekend probability, at a uniformly random time inside the charging
    window, for a uniformly random session length. Partial half-hour overlap
    is accounted for analytically. ``cfg.diversity_factor`` is applied per
    household as an energy calibration; it is linear, so it never stands in
    for the timing diversity produced by the draws themselves.
    """
    timestamps = pd.DatetimeIndex(timestamps)
    n_periods, n_households = len(timestamps), len(owners)
    out = np.zeros((n_periods, n_households), dtype=float)
    ev_idx = np.flatnonzero(owners)
    if n_periods == 0 or ev_idx.size == 0:
        return out

    day0 = timestamps[0].normalize()
    abs_period = ((timestamps - day0).total_seconds().to_numpy() // (60 * 30)).astype(np.int64)
    n_slots = int(abs_period.max()) + PERIODS_PER_DAY + 1

    unique_days = pd.DatetimeIndex(sorted(set(timestamps.normalize())))
    day_offset = ((unique_days - day0).days.to_numpy() * PERIODS_PER_DAY).astype(np.int64)
    is_weekend = unique_days.dayofweek.to_numpy() >= 5
    p_charge = np.where(is_weekend, cfg.weekend_charge_probability, cfg.weekday_charge_probability)

    charging = rng.random((len(unique_days), ev_idx.size)) < p_charge[:, None]
    day_idx, car_idx = np.nonzero(charging)
    if day_idx.size == 0:
        return out

    start = rng.uniform(cfg.window_start_hour * 2, cfg.window_end_hour * 2, day_idx.size)
    duration = rng.uniform(cfg.min_duration_h * 2, cfg.max_duration_h * 2, day_idx.size)
    end = start + duration
    base = day_offset[day_idx] + np.floor(start).astype(np.int64)
    household = ev_idx[car_idx]

    energy_full_period = cfg.charger_kw * HOURS_PER_PERIOD
    acc = np.zeros((n_slots, n_households), dtype=float)
    for k in range(int(np.ceil(cfg.max_duration_h * 2)) + 2):
        slot = base + k
        lo = np.floor(start) + k
        overlap = np.clip(np.minimum(end, lo + 1) - np.maximum(start, lo), 0.0, 1.0)
        contrib = overlap * energy_full_period
        valid = (contrib > 0) & (slot >= 0) & (slot < n_slots)
        if valid.any():
            np.add.at(acc, (slot[valid], household[valid]), contrib[valid])

    out[:] = acc[abs_period]
    return out * float(cfg.diversity_factor)


# ===========================================================================
# heat pumps -- per household
# ===========================================================================
# Household timing diversity: thermostat schedules differ between homes by
# tens of minutes, and each unit cycles on its own. A small common-mode term
# keeps the fleet-wide response to the weather.
SCHEDULE_OFFSET_SD_H = 0.75
CYCLING_SD = 0.10
COMMON_CYCLING_SD = 0.04
EFFICIENCY_SD = 0.18


def heat_pump_shape(hours: np.ndarray, cfg: HeatPumpConfig) -> np.ndarray:
    """Occupancy-driven shaping factor with morning and evening peaks."""
    m_start, m_end, e_start, e_end = cfg.evening_peak_hours
    morning = np.exp(-0.5 * ((hours - (m_start + m_end) / 2) / 1.6) ** 2)
    evening = np.exp(-0.5 * ((hours - (e_start + e_end) / 2) / 2.6) ** 2)
    setback = 0.35  # overnight / away frost protection
    return setback + 0.75 * morning + 1.0 * evening


def heating_degrees(
    timestamps: pd.DatetimeIndex,
    temperature_c: np.ndarray | pd.Series | None,
    base_temperature_c: float,
) -> np.ndarray:
    """Heating degrees per period; a winter-seasonal proxy when no temperature."""
    if temperature_c is not None:
        temp = (
            pd.Series(np.asarray(temperature_c, dtype=float)).interpolate(limit_direction="both").to_numpy()
        )
        return np.clip(base_temperature_c - temp, 0.0, None)
    doy = timestamps.dayofyear.to_numpy(dtype=float)
    return np.clip(6.5 + 6.0 * np.cos(2 * np.pi * (doy - 20) / 365.25), 0.0, None)


def heat_pump_household_profiles(
    timestamps: pd.DatetimeIndex,
    owners: np.ndarray,
    temperature_c: np.ndarray | pd.Series | None,
    cfg: HeatPumpConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    """Heat-pump electrical energy (kWh per half hour) per household.

    Every owner gets its own thermal efficiency, its own schedule offset
    (the occupancy shape is shifted by a household-specific number of
    minutes) and its own thermostat cycling, so units do not peak in lock-step.
    Draw is capped at the unit rating. ``cfg.diversity_factor`` is applied per
    household as an energy calibration, as for EVs.
    """
    timestamps = pd.DatetimeIndex(timestamps)
    n_periods, n_households = len(timestamps), len(owners)
    out = np.zeros((n_periods, n_households), dtype=float)
    hp_idx = np.flatnonzero(owners)
    if n_periods == 0 or hp_idx.size == 0:
        return out

    hdd = heating_degrees(timestamps, temperature_c, cfg.base_temperature_c)
    hours = (timestamps.hour + timestamps.minute / 60.0).to_numpy(dtype=float)

    n_hp = hp_idx.size
    efficiency = np.clip(rng.normal(1.0, EFFICIENCY_SD, n_hp), 0.4, 1.8)
    offset_h = rng.normal(0.0, SCHEDULE_OFFSET_SD_H, n_hp)
    shape = heat_pump_shape((hours[:, None] - offset_h[None, :]) % 24.0, cfg)
    common = rng.normal(0.0, COMMON_CYCLING_SD, n_periods)[:, None]
    cycling = np.clip(1.0 + common + rng.normal(0.0, CYCLING_SD, (n_periods, n_hp)), 0.6, 1.4)

    # cycling is applied *inside* the clip: a unit can modulate below its
    # rating but never draw more than its rated electrical input
    kw = np.clip(cfg.kw_per_degree * hdd[:, None] * shape * efficiency[None, :] * cycling, 0.0, cfg.rated_kw)
    out[:, hp_idx] = kw * HOURS_PER_PERIOD
    return out * float(cfg.diversity_factor)


# ===========================================================================
# superposition -> single aggregation
# ===========================================================================
@dataclass
class NeighbourhoodLoad:
    """Electrification load of one neighbourhood, aggregated exactly once.

    ``total_runs`` holds, per Monte-Carlo run, the sum over households of each
    household's superimposed EV + heat-pump load. ``ev_runs`` and
    ``heat_pump_runs`` attribute the same draws to each technology; they add
    up to ``total_runs`` but are never used to build it.
    """

    total_runs: np.ndarray
    ev_runs: np.ndarray
    heat_pump_runs: np.ndarray
    n_households: int
    n_ev: int
    n_heat_pump: int
    household_peak_kwh: float

    @property
    def runs(self) -> int:
        return int(self.total_runs.shape[0])

    @property
    def total_kwh(self) -> np.ndarray:
        return self.total_runs.mean(axis=0)

    @property
    def ev_kwh(self) -> np.ndarray:
        return self.ev_runs.mean(axis=0)

    @property
    def heat_pump_kwh(self) -> np.ndarray:
        return self.heat_pump_runs.mean(axis=0)

    def band(self, which: str = "total", lo: float = 10, hi: float = 90) -> tuple[np.ndarray, np.ndarray]:
        """Monte-Carlo percentile band of a series, from its per-run values."""
        runs = {"total": self.total_runs, "ev": self.ev_runs, "heat_pump": self.heat_pump_runs}[which]
        return np.percentile(runs, lo, axis=0), np.percentile(runs, hi, axis=0)


def simulate_neighbourhood_load(
    timestamps: pd.DatetimeIndex,
    n_households: int,
    ev_adoption: float,
    hp_adoption: float,
    temperature_c: np.ndarray | pd.Series | None = None,
    ev_config: EVConfig | None = None,
    hp_config: HeatPumpConfig | None = None,
    *,
    ev_seed: int = 42,
    hp_seed: int = 42,
    runs: int = 1,
) -> NeighbourhoodLoad:
    """Simulate, superimpose per household, then aggregate once.

    Each technology draws from its own seeded stream (``ev_seed`` /
    ``hp_seed`` plus a per-run offset), so the EV draws are identical whether
    or not heat pumps are present. That makes EV-only, heat-pump-only and
    combined scenarios directly comparable.
    """
    from drg.simulation.electrification import EVConfig, HeatPumpConfig

    ev_cfg = ev_config or EVConfig()
    hp_cfg = hp_config or HeatPumpConfig()
    timestamps = pd.DatetimeIndex(timestamps)
    n_periods, n_households, runs = len(timestamps), max(int(n_households), 0), max(int(runs), 1)

    total = np.zeros((runs, n_periods))
    ev_total = np.zeros((runs, n_periods))
    hp_total = np.zeros((runs, n_periods))
    household_peak = 0.0
    n_ev = n_hp = 0
    for run in range(runs):
        ev_rng = np.random.default_rng(ev_seed + 1009 * run)
        hp_rng = np.random.default_rng(hp_seed + 3607 * run)
        ev_owners = adopter_mask(n_households, ev_adoption, ev_rng)
        hp_owners = adopter_mask(n_households, hp_adoption, hp_rng)
        n_ev, n_hp = int(ev_owners.sum()), int(hp_owners.sum())

        ev_hh = ev_household_profiles(timestamps, ev_owners, ev_cfg, ev_rng)
        hp_hh = heat_pump_household_profiles(timestamps, hp_owners, temperature_c, hp_cfg, hp_rng)

        household = ev_hh + hp_hh  # superimpose per household, half-hourly
        total[run] = household.sum(axis=1)  # aggregate once, at the end
        ev_total[run] = ev_hh.sum(axis=1)  # attribution of the same draws
        hp_total[run] = hp_hh.sum(axis=1)
        if household.size:
            household_peak = max(household_peak, float(household.max()))

    return NeighbourhoodLoad(
        total_runs=total,
        ev_runs=ev_total,
        heat_pump_runs=hp_total,
        n_households=n_households,
        n_ev=n_ev,
        n_heat_pump=n_hp,
        household_peak_kwh=household_peak,
    )
