"""Bottom-up EV and heat-pump electrification simulation.

Both technologies are simulated at *household* level and then aggregated, so
the resulting neighbourhood profile carries a realistic diversity effect
rather than a flat multiplier:

**Electric vehicles** - each adopting household owns a home charger of
``charger_kw``. On any given day it plugs in with a weekday/weekend
probability; the arrival time is drawn from an evening-peaked distribution
(truncated normal inside the charging window) and the session energy from the
car's mileage (``annual_miles`` / ``miles_per_kwh``, lognormal spread), so the
session lasts energy / charger power rather than a fixed schedule. A faster
charger therefore delivers the *same* energy in a shorter, sharper session.
Sessions that overrun the window continue into the night, exactly as
uncontrolled domestic charging does, and partial half-hour overlap is
accounted for analytically (DRG-74).

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
    # arrival-time distribution: truncated normal inside the charging window
    window_start_hour: float = 15.0
    window_end_hour: float = 23.5
    weekday_arrival_mean_h: float = 18.5
    weekday_arrival_sd_h: float = 1.4
    weekend_arrival_mean_h: float = 17.5
    weekend_arrival_sd_h: float = 2.2
    # plug-in frequency
    weekday_charge_probability: float = 0.32
    weekend_charge_probability: float = 0.24
    # session energy, calibrated from mileage: energy / charger_kw = duration
    annual_miles: float = 6800.0
    miles_per_kwh: float = 3.5
    charge_efficiency: float = 1.0  # energy at the meter per kWh into the battery
    session_energy_cv: float = 0.45
    battery_kwh: float = 60.0
    # linear calibration of the aggregate; diversity itself comes from the draws
    diversity_factor: float = 1.0

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
def ev_daily_kwh(cfg: EVConfig) -> float:
    """Mean energy drawn from the grid per car per day implied by the mileage settings."""
    return float(cfg.annual_miles) / 365.0 / float(cfg.miles_per_kwh) / float(cfg.charge_efficiency)


def _mean_plug_in_probability(cfg: EVConfig) -> float:
    return (5.0 * cfg.weekday_charge_probability + 2.0 * cfg.weekend_charge_probability) / 7.0


def ev_session_kwh(cfg: EVConfig) -> float:
    """Mean energy per charging session: daily energy spread over the plug-in days."""
    p = _mean_plug_in_probability(cfg)
    return ev_daily_kwh(cfg) / p if p > 0 else 0.0


def draw_ev_sessions(
    unique_days: pd.DatetimeIndex,
    n_ev: int,
    cfg: EVConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Draw every charging session for ``n_ev`` cars over ``unique_days``.

    * **plug-in** -- each car plugs in on a day with the weekday / weekend
      probability;
    * **arrival** -- a truncated normal around the weekday / weekend mean
      arrival hour, bounded by the charging window;
    * **energy** -- lognormal around the mean session energy implied by the
      mileage settings (``annual_miles`` / ``miles_per_kwh``), capped at the
      battery size;
    * **duration** -- energy / charger power, so a faster charger delivers the
      same energy in a shorter, sharper session.

    Returns one row per session: ``day_index, car, arrival_h, energy_kwh,
    duration_h``.
    """
    from scipy.stats import truncnorm

    cols = ["day_index", "car", "arrival_h", "energy_kwh", "duration_h"]
    if n_ev <= 0 or len(unique_days) == 0:
        return pd.DataFrame(columns=cols)

    is_weekend = unique_days.dayofweek.to_numpy() >= 5
    p_charge = np.where(is_weekend, cfg.weekend_charge_probability, cfg.weekday_charge_probability)
    charging = rng.random((len(unique_days), n_ev)) < p_charge[:, None]
    day_idx, car_idx = np.nonzero(charging)
    n = day_idx.size
    if n == 0:
        return pd.DataFrame(columns=cols)

    weekend = is_weekend[day_idx]
    mean_h = np.where(weekend, cfg.weekend_arrival_mean_h, cfg.weekday_arrival_mean_h)
    sd_h = np.where(weekend, cfg.weekend_arrival_sd_h, cfg.weekday_arrival_sd_h)
    lo = (cfg.window_start_hour - mean_h) / sd_h
    hi = (cfg.window_end_hour - mean_h) / sd_h
    arrival = truncnorm.rvs(lo, hi, loc=mean_h, scale=sd_h, size=n, random_state=rng)

    mean_kwh = ev_session_kwh(cfg)
    sigma = np.sqrt(np.log1p(cfg.session_energy_cv**2))
    mu = np.log(mean_kwh) - sigma**2 / 2.0
    energy = np.minimum(rng.lognormal(mu, sigma, n), cfg.battery_kwh)

    return pd.DataFrame(
        {
            "day_index": day_idx,
            "car": car_idx,
            "arrival_h": arrival,
            "energy_kwh": energy,
            "duration_h": energy / cfg.charger_kw,
        }
    )


def simulate_ev_households(
    timestamps: pd.DatetimeIndex,
    n_ev: int,
    config: EVConfig | None = None,
    *,
    seed: int = 42,
    sessions: pd.DataFrame | None = None,
) -> np.ndarray:
    """Half-hourly charging energy per EV household: a ``(periods, n_ev)`` matrix.

    Partial half-hour overlap is accounted for analytically, so a session
    arriving at 18:12 contributes the correct fraction to the 18:00 period,
    and sessions that run past midnight continue into the next day.
    """
    cfg = config or EVConfig()
    timestamps = pd.DatetimeIndex(timestamps)
    out = np.zeros((len(timestamps), max(int(n_ev), 0)))
    if n_ev <= 0 or len(timestamps) == 0:
        return out

    day0 = timestamps[0].normalize()
    abs_period = ((timestamps - day0).total_seconds().to_numpy() // (60 * 30)).astype(np.int64)
    unique_days = pd.DatetimeIndex(sorted(set(timestamps.normalize())))
    if sessions is None:
        sessions = draw_ev_sessions(unique_days, n_ev, cfg, np.random.default_rng(seed))
    if sessions.empty:
        return out

    day_offset = ((unique_days - day0).days.to_numpy() * PERIODS_PER_DAY).astype(np.int64)
    start = sessions["arrival_h"].to_numpy() * 2.0  # fractional periods after midnight
    end = start + sessions["duration_h"].to_numpy() * 2.0
    car = sessions["car"].to_numpy()
    base = day_offset[sessions["day_index"].to_numpy()] + np.floor(start).astype(np.int64)

    n_slots = int(abs_period.max()) + PERIODS_PER_DAY * 2 + 1
    energy_full_period = cfg.charger_kw * HOURS_PER_PERIOD  # kWh in a fully-charging half hour
    acc = np.zeros((n_slots, n_ev))
    for k in range(int(np.ceil((end - start).max())) + 2):
        slot = base + k
        lo = np.floor(start) + k
        overlap = np.clip(np.minimum(end, lo + 1) - np.maximum(start, lo), 0.0, 1.0)
        contrib = overlap * energy_full_period
        valid = (contrib > 0) & (slot >= 0) & (slot < n_slots)
        if valid.any():
            np.add.at(acc, (slot[valid], car[valid]), contrib[valid])

    out[:] = acc[abs_period]
    return out * float(cfg.diversity_factor)


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

    The sum over :func:`simulate_ev_households`. ``timestamps`` must be a
    regular 30-minute index. Returns the Monte-Carlo mean profile, optionally
    with the 10th/90th percentile band.
    """
    cfg = config or EVConfig()
    timestamps = pd.DatetimeIndex(timestamps)
    n_ev = int(round(n_households * float(adoption)))
    if n_ev <= 0 or len(timestamps) == 0:
        zeros = np.zeros(len(timestamps))
        return (zeros, zeros, zeros) if return_band else zeros

    profiles = np.zeros((runs, len(timestamps)))
    for run in range(runs):
        profiles[run] = simulate_ev_households(timestamps, n_ev, cfg, seed=seed + 1009 * run).sum(axis=1)

    mean = profiles.mean(axis=0)
    if return_band:
        return mean, np.percentile(profiles, 10, axis=0), np.percentile(profiles, 90, axis=0)
    return mean


def ev_planning_metrics(
    frame: pd.DataFrame,
    n_ev_by_site: dict[str, int],
    config: EVConfig | None = None,
) -> dict[str, float]:
    """EV figures a planner checks first, per scenario (DRG-74).

    * ``ev_admd_kw`` -- after-diversity maximum demand per EV: each
      neighbourhood's peak half-hourly EV load (as kW) divided by its number
      of EVs, averaged over neighbourhoods. It depends on the charger power:
      faster chargers shorten sessions and raise the coincident peak.
    * ``ev_kwh_per_car_per_day`` / ``_per_year`` -- energy actually delivered
      per car in the scenario window, and ``ev_implied_miles_per_year`` --
      what that energy drives, to sanity-check against average UK mileage;
      ``ev_mileage_check_ratio`` is that mileage over the configured
      ``annual_miles`` (1.0 = consistent).
    """
    cfg = config or EVConfig()
    admd: list[float] = []
    energy = cars = 0.0
    days = 0.0
    for nid, sub in frame.groupby("neighbourhood_id", observed=True):
        n_ev = int(n_ev_by_site.get(str(nid), 0))
        if n_ev <= 0:
            continue
        admd.append(float(sub["ev_kwh"].max()) / HOURS_PER_PERIOD / n_ev)
        energy += float(sub["ev_kwh"].sum())
        cars += n_ev
        days = max(days, sub["timestamp"].nunique() / PERIODS_PER_DAY)
    if not cars or not days:
        return {
            "ev_charger_kw": float(cfg.charger_kw),
            "ev_count": 0,
            "ev_admd_kw": 0.0,
            "ev_kwh_per_car_per_day": 0.0,
            "ev_kwh_per_car_per_year": 0.0,
            "ev_implied_miles_per_year": 0.0,
            "ev_mileage_check_ratio": float("nan"),
        }
    per_day = energy / cars / days
    miles = per_day * 365.0 * cfg.miles_per_kwh * cfg.charge_efficiency
    return {
        "ev_charger_kw": float(cfg.charger_kw),
        "ev_count": int(cars),
        "ev_admd_kw": float(np.mean(admd)),
        "ev_kwh_per_car_per_day": float(per_day),
        "ev_kwh_per_car_per_year": float(per_day * 365.0),
        "ev_implied_miles_per_year": float(miles),
        "ev_mileage_check_ratio": float(miles / cfg.annual_miles) if cfg.annual_miles else float("nan"),
    }


# ===========================================================================
# heat pumps
# ===========================================================================
def _heat_pump_shape(period_of_day: np.ndarray, cfg: HeatPumpConfig) -> np.ndarray:
    """Occupancy-driven shaping factor with morning and evening peaks."""
    m_start, m_end, e_start, e_end = cfg.evening_peak_hours
    hours = period_of_day / 2.0
    morning = np.exp(-0.5 * ((hours - (m_start + m_end) / 2) / 1.6) ** 2)
    evening = np.exp(-0.5 * ((hours - (e_start + e_end) / 2) / 2.6) ** 2)
    setback = 0.35  # overnight / away frost protection
    return setback + 0.75 * morning + 1.0 * evening


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
    """Aggregate heat-pump electrical demand (kWh per half hour)."""
    cfg = config or HeatPumpConfig()
    timestamps = pd.DatetimeIndex(timestamps)
    n_hp = int(round(n_households * float(adoption)))
    if n_hp <= 0 or len(timestamps) == 0:
        zeros = np.zeros(len(timestamps))
        return (zeros, zeros, zeros) if return_band else zeros

    period_of_day = (timestamps.hour * 2 + timestamps.minute // 30).to_numpy()
    shape = _heat_pump_shape(period_of_day, cfg)

    if temperature_c is not None:
        temp = (
            pd.Series(np.asarray(temperature_c, dtype=float)).interpolate(limit_direction="both").to_numpy()
        )
        hdd = np.clip(cfg.base_temperature_c - temp, 0.0, None)
    else:  # winter-seasonal proxy when no temperature is available
        doy = timestamps.dayofyear.to_numpy(dtype=float)
        hdd = np.clip(6.5 + 6.0 * np.cos(2 * np.pi * (doy - 20) / 365.25), 0.0, None)

    profiles = np.zeros((runs, len(timestamps)), dtype=float)
    for run in range(runs):
        rng = np.random.default_rng(seed + 3607 * run)
        # per-household thermal efficiency / setpoint spread
        spread = np.clip(rng.normal(1.0, 0.18, n_hp), 0.4, 1.8)
        # thermostat cycling noise, common-mode across the fleet
        cycling = np.clip(rng.normal(1.0, 0.08, len(timestamps)), 0.6, 1.4)

        # cycling is applied *inside* the clip: a unit can modulate below its
        # rating but never draw more than its rated electrical input
        per_hh_kw = np.clip(
            cfg.kw_per_degree * hdd[:, None] * shape[:, None] * spread[None, :] * cycling[:, None],
            0.0,
            cfg.rated_kw,
        )
        profiles[run] = per_hh_kw.sum(axis=1) * HOURS_PER_PERIOD

    profiles *= cfg.diversity_factor
    mean = profiles.mean(axis=0)
    if return_band:
        return mean, np.percentile(profiles, 10, axis=0), np.percentile(profiles, 90, axis=0)
    return mean


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
    ``electrified_kwh``. The summary carries the EV planning figures of
    :func:`ev_planning_metrics` (charger power, ADMD, kWh per car per day and
    the implied annual mileage).
    """
    ev_config = ev_config or EVConfig()
    frames: list[pd.DataFrame] = []
    n_ev_by_site: dict[str, int] = {}
    for nid, sub in df.groupby("neighbourhood_id", observed=True, sort=True):
        sub = sub.sort_values("timestamp").copy()
        ts = pd.DatetimeIndex(sub["timestamp"])
        households = int(sub[households_col].iloc[0]) if households_col in sub else 100
        n_ev_by_site[str(nid)] = int(round(households * float(ev_adoption)))

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
    n_hp = households * float(hp_adoption)
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
        **ev_planning_metrics(out, n_ev_by_site, ev_config),
        "heat_pump_admd_kw": hp_admd,
        "monte_carlo_runs": int(runs),
    }
    log.info(
        "scenario EV=%.0f%% HP=%.0f%% -> peak +%.1f%%, energy +%.1f%%; EV %.1f kW charger: "
        "ADMD %.2f kW, %.1f kWh/car/day (~%s miles/year)",
        ev_adoption * 100,
        hp_adoption * 100,
        summary["peak_amplification_pct"],
        summary["energy_growth_pct"],
        summary["ev_charger_kw"],
        summary["ev_admd_kw"],
        summary["ev_kwh_per_car_per_day"],
        f"{summary['ev_implied_miles_per_year']:,.0f}",
    )
    return ScenarioResult(frame=out, summary=summary)
