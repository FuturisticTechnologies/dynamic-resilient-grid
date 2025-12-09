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

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

PERIODS_PER_DAY = 48
HOURS_PER_PERIOD = 0.5


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

    ``timestamps`` must be a regular 30-minute index. Returns the Monte-Carlo
    mean profile, optionally with the 10th/90th percentile band.
    """
    cfg = config or EVConfig()
    timestamps = pd.DatetimeIndex(timestamps)
    n_ev = int(round(n_households * float(adoption)))
    if n_ev <= 0 or len(timestamps) == 0:
        zeros = np.zeros(len(timestamps))
        return (zeros, zeros, zeros) if return_band else zeros

    # absolute half-hour index of every timestamp relative to the first day
    day0 = timestamps[0].normalize()
    abs_period = ((timestamps - day0).total_seconds().to_numpy() // (60 * 30)).astype(np.int64)
    n_slots = int(abs_period.max()) + PERIODS_PER_DAY + 1

    unique_days = pd.DatetimeIndex(sorted(set(timestamps.normalize())))
    day_offset = ((unique_days - day0).days.to_numpy() * PERIODS_PER_DAY).astype(np.int64)
    is_weekend = unique_days.dayofweek.to_numpy() >= 5
    p_charge = np.where(is_weekend, cfg.weekend_charge_probability, cfg.weekday_charge_probability)

    energy_full_period = cfg.charger_kw * HOURS_PER_PERIOD  # kWh in a fully-charging half hour
    max_span = int(np.ceil(cfg.max_duration_h * 2)) + 2

    profiles = np.zeros((runs, n_slots), dtype=float)
    for run in range(runs):
        rng = np.random.default_rng(seed + 1009 * run)
        n_days = len(unique_days)

        charging = rng.random((n_days, n_ev)) < p_charge[:, None]
        day_idx, _ = np.nonzero(charging)
        n_sessions = day_idx.size
        if n_sessions == 0:
            continue

        start = rng.uniform(
            cfg.window_start_hour * 2, cfg.window_end_hour * 2, n_sessions
        )  # fractional periods after midnight
        duration = rng.uniform(cfg.min_duration_h * 2, cfg.max_duration_h * 2, n_sessions)
        end = start + duration
        base = day_offset[day_idx] + np.floor(start).astype(np.int64)

        acc = profiles[run]
        for k in range(max_span):
            slot = base + k
            lo = np.floor(start) + k
            overlap = np.clip(np.minimum(end, lo + 1) - np.maximum(start, lo), 0.0, 1.0)
            contrib = overlap * energy_full_period
            valid = (contrib > 0) & (slot >= 0) & (slot < n_slots)
            if valid.any():
                np.add.at(acc, slot[valid], contrib[valid])

    profiles *= cfg.diversity_factor
    aligned = profiles[:, abs_period]
    mean = aligned.mean(axis=0)
    if return_band:
        return mean, np.percentile(aligned, 10, axis=0), np.percentile(aligned, 90, axis=0)
    return mean
