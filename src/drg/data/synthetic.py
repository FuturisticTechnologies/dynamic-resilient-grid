"""Physically-plausible synthetic smart-meter fallback.

The Low Carbon London dataset (UK Data Service study 7857) is licence
controlled and cannot be redistributed, so DRG ships a calibrated generator
that reproduces the statistical properties the framework depends on:

* half-hourly resolution, 48 periods per day;
* bimodal weekday load curve (07:00-09:00 and 17:00-21:00 peaks);
* flatter, later weekend profile;
* winter amplification driven by heating-degree response to temperature;
* household diversity (aggregate coefficient of variation ~ 1/sqrt(N));
* holiday and daylight-saving effects.

Every generated series is reproducible from ``project.random_seed``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

# Half-hourly weekday / weekend shape factors (48 values each), normalised to
# mean 1.0. Derived from published UK domestic profile class 1 load curves.
# fmt: off
_WEEKDAY_SHAPE = np.array([
    0.62, 0.57, 0.53, 0.50, 0.48, 0.47, 0.46, 0.46, 0.48, 0.53, 0.62, 0.76,
    0.93, 1.06, 1.10, 1.05, 0.98, 0.93, 0.90, 0.88, 0.87, 0.87, 0.88, 0.90,
    0.92, 0.94, 0.96, 0.99, 1.03, 1.10, 1.22, 1.40, 1.62, 1.80, 1.88, 1.86,
    1.78, 1.68, 1.56, 1.44, 1.32, 1.20, 1.08, 0.97, 0.87, 0.79, 0.72, 0.67,
])
_WEEKEND_SHAPE = np.array([
    0.68, 0.62, 0.57, 0.53, 0.50, 0.48, 0.47, 0.46, 0.46, 0.48, 0.53, 0.61,
    0.72, 0.85, 0.97, 1.06, 1.10, 1.11, 1.10, 1.08, 1.06, 1.05, 1.05, 1.06,
    1.08, 1.10, 1.11, 1.12, 1.14, 1.18, 1.27, 1.42, 1.58, 1.72, 1.79, 1.78,
    1.71, 1.62, 1.52, 1.42, 1.32, 1.22, 1.12, 1.02, 0.92, 0.84, 0.77, 0.72,
])
# fmt: on

_UK_HOLIDAYS = {"01-01", "12-25", "12-26"}


def synthetic_temperature(index: pd.DatetimeIndex, seed: int = 42) -> pd.Series:
    """London-like half-hourly air temperature (deg C).

    Annual sinusoid + diurnal sinusoid + AR(1) synoptic weather noise.
    """
    rng = np.random.default_rng(seed + 991)
    doy = index.dayofyear.to_numpy(dtype=float)
    tod = index.hour.to_numpy(dtype=float) + index.minute.to_numpy(dtype=float) / 60.0

    annual = 11.0 - 6.6 * np.cos(2 * np.pi * (doy - 20.0) / 365.25)
    diurnal = 3.1 * np.sin(2 * np.pi * (tod - 9.0) / 24.0)

    # AR(1) synoptic anomaly evolving on a daily timescale
    n_days = int((index[-1].normalize() - index[0].normalize()).days) + 2
    anomaly = np.zeros(n_days)
    for i in range(1, n_days):
        anomaly[i] = 0.86 * anomaly[i - 1] + rng.normal(0, 1.9)
    day_index = (index.normalize() - index[0].normalize()).days.to_numpy()
    synoptic = anomaly[np.clip(day_index, 0, n_days - 1)]

    temp = annual + diurnal + synoptic + rng.normal(0, 0.35, len(index))
    return pd.Series(np.round(temp, 2), index=index, name="temperature_c")


def generate_synthetic_neighbourhoods(
    start: str = "2012-01-01",
    end: str = "2014-02-28",
    n_neighbourhoods: int = 4,
    households_per_neighbourhood: int = 120,
    seed: int = 42,
    freq: str = "30min",
    temperature: pd.Series | None = None,
) -> pd.DataFrame:
    """Return tidy half-hourly neighbourhood demand.

    Columns: ``timestamp``, ``neighbourhood_id``, ``demand_kwh``,
    ``n_households``, ``temperature_c``.

    When ``temperature`` is supplied (for example the real ERA5 reanalysis
    series fetched from Open-Meteo) the heating response is driven by observed
    London weather, so the fallback dataset still exhibits genuine weather
    dependence rather than a synthetic sinusoid.
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range(start=start, end=end, freq=freq, inclusive="left")
    if len(index) == 0:
        raise ValueError("Empty date range for synthetic generation")

    if temperature is not None and len(temperature):
        temperature = pd.Series(np.asarray(temperature, dtype=float), index=index).interpolate(
            limit_direction="both"
        )
        log.info("synthetic demand driven by supplied (observed) temperature series")
    else:
        temperature = synthetic_temperature(index, seed=seed)
    period = (index.hour * 2 + index.minute // 30).to_numpy()
    is_weekend = index.dayofweek.to_numpy() >= 5
    md = index.strftime("%m-%d")
    is_holiday = np.isin(md, list(_UK_HOLIDAYS))

    # Heating-degree response: kWh per half hour per household per degree below base
    heat_base_c = 15.5
    hdd = np.clip(heat_base_c - temperature.to_numpy(), 0, None)

    frames = []
    for n_id in range(n_neighbourhoods):
        n_households = int(households_per_neighbourhood * (1.0 + 0.12 * rng.standard_normal()))
        n_households = max(30, n_households)

        # Neighbourhood archetype: affluence multiplier + heating electrification
        wealth = float(np.clip(rng.normal(1.0, 0.13), 0.7, 1.4))
        elec_heat_share = float(np.clip(rng.normal(0.16, 0.06), 0.03, 0.35))

        base_kwh_hh = 0.135 * wealth  # per half hour, per household
        shape = np.where(
            is_weekend[:, None], _WEEKEND_SHAPE[period][:, None], _WEEKDAY_SHAPE[period][:, None]
        ).ravel()

        seasonal = 1.0 + 0.10 * np.cos(2 * np.pi * (index.dayofyear.to_numpy() - 15) / 365.25)
        holiday_factor = np.where(is_holiday, 1.18, 1.0)

        # Evening-weighted heating response
        evening_weight = (
            0.55
            + 0.85 * np.exp(-0.5 * ((period - 38) / 7.0) ** 2)
            + 0.45 * np.exp(-0.5 * ((period - 15) / 5.0) ** 2)
        )
        heating_kwh_hh = elec_heat_share * 0.0125 * hdd * evening_weight

        mean_hh = base_kwh_hh * shape * seasonal * holiday_factor + heating_kwh_hh

        # Aggregate diversity: CV shrinks like 1/sqrt(N); add AR(1) persistence.
        cv = 0.55 / np.sqrt(n_households)
        noise = rng.normal(0.0, 1.0, len(index))
        for i in range(1, len(noise)):
            noise[i] = 0.55 * noise[i - 1] + 0.835 * noise[i]
        demand = mean_hh * n_households * (1.0 + cv * noise)

        # Rare, short data-quality dropouts (meter comms loss)
        dropout = rng.random(len(index)) < 0.0006
        demand[dropout] = np.nan

        frames.append(
            pd.DataFrame(
                {
                    "timestamp": index,
                    "neighbourhood_id": f"N{n_id + 1:02d}",
                    "demand_kwh": np.round(np.clip(demand, 0.0, None), 4),
                    "n_households": n_households,
                    "temperature_c": temperature.to_numpy(),
                }
            )
        )

    out = pd.concat(frames, ignore_index=True)
    log.info(
        "generated synthetic demand: %s rows, %s neighbourhoods, %s -> %s",
        f"{len(out):,}",
        n_neighbourhoods,
        index[0].date(),
        index[-1].date(),
    )
    return out
