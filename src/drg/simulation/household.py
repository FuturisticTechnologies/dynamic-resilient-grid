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

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

if TYPE_CHECKING:  # configs live with the public API; avoid an import cycle
    from drg.simulation.electrification import EVConfig

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
