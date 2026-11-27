"""EV charging profiles (DRG-74)."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from drg.analysis.sensitivity import run_sensitivity_grid, summarise_amplification
from drg.simulation.electrification import (
    EVConfig,
    apply_scenario,
    draw_ev_sessions,
    ev_daily_kwh,
    ev_planning_metrics,
    ev_session_kwh,
    simulate_ev_households,
    simulate_ev_load,
)
from drg.stress.detection import compute_thresholds

WINTER = pd.date_range("2014-01-06", "2014-02-03", freq="30min", inclusive="left")


def _cfg(**overrides) -> EVConfig:
    return dataclasses.replace(EVConfig(), **overrides)


# --------------------------------------------------------------- sessions --
def test_arrivals_follow_a_distribution_inside_the_window(rng):
    cfg = EVConfig()
    sessions = draw_ev_sessions(pd.DatetimeIndex(sorted(set(WINTER.normalize()))), 200, cfg, rng)
    arrival = sessions["arrival_h"]
    assert arrival.between(cfg.window_start_hour, cfg.window_end_hour).all()
    assert arrival.std() > 0.8, "arrival must be a distribution, not a fixed time"
    assert abs(arrival.mean() - cfg.weekday_arrival_mean_h) < 0.6
    assert arrival.nunique() == len(arrival)


def test_session_duration_is_energy_over_charger_power(rng):
    cfg = _cfg(charger_kw=11.0)
    sessions = draw_ev_sessions(pd.DatetimeIndex(sorted(set(WINTER.normalize()))), 50, cfg, rng)
    assert np.allclose(sessions["duration_h"], sessions["energy_kwh"] / 11.0)
    assert sessions["duration_h"].std() > 0, "durations vary with energy need"
    assert sessions["energy_kwh"].max() <= cfg.battery_kwh + 1e-9
    assert sessions["energy_kwh"].mean() == pytest.approx(ev_session_kwh(cfg), rel=0.1)


def test_mileage_calibration():
    cfg = _cfg(annual_miles=7000, miles_per_kwh=3.5, charge_efficiency=1.0)
    assert ev_daily_kwh(cfg) == pytest.approx(7000 / 365 / 3.5)
    p = (5 * cfg.weekday_charge_probability + 2 * cfg.weekend_charge_probability) / 7
    assert ev_session_kwh(cfg) == pytest.approx(ev_daily_kwh(cfg) / p)


# ------------------------------------------------------ household profiles --
def test_profiles_are_per_household_and_respect_the_charger():
    cfg = _cfg(charger_kw=7.0)
    matrix = simulate_ev_households(WINTER, 12, cfg, seed=2)
    assert matrix.shape == (len(WINTER), 12)
    assert matrix.max() <= 7.0 * 0.5 + 1e-9
    assert (matrix.sum(axis=0) > 0).all(), "every EV household charges at some point"
    assert np.allclose(simulate_ev_load(WINTER, 12, 1.0, cfg, seed=2), matrix.sum(axis=1))


def test_charger_power_changes_the_peak_not_the_energy():
    slow = simulate_ev_load(WINTER, 100, 1.0, _cfg(charger_kw=3.6), seed=4, runs=2)
    fast = simulate_ev_load(WINTER, 100, 1.0, _cfg(charger_kw=22.0), seed=4, runs=2)
    assert fast.sum() == pytest.approx(slow.sum(), rel=0.02)
    assert fast.max() > slow.max() * 1.3


def test_daily_energy_matches_average_uk_mileage():
    cfg = EVConfig()
    load = simulate_ev_load(WINTER, 100, 1.0, cfg, seed=7, runs=3)
    per_car_day = load.sum() / 100 / (len(WINTER) / 48)
    assert per_car_day == pytest.approx(ev_daily_kwh(cfg), rel=0.08)
    assert 4.0 < per_car_day < 7.0, "~1,500-2,500 kWh/year, i.e. average UK car mileage"


# ---------------------------------------------------------- per scenario ---
def _frame(n_households: int = 120) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": np.tile(WINTER, 2),
            "neighbourhood_id": np.repeat(["N01", "N02"], len(WINTER)),
            "demand_kwh": 30.0 + 10.0 * np.sin(np.tile(np.arange(len(WINTER)), 2) * np.pi / 24),
            "n_households": n_households,
        }
    )


def test_scenario_reports_charger_admd_and_daily_energy():
    s = apply_scenario(_frame(), 0.5, 0.0, ev_config=_cfg(charger_kw=7.0), seed=1).summary
    assert s["ev_charger_kw"] == 7.0
    assert s["ev_count"] == 120
    assert 0.5 < s["ev_admd_kw"] < 3.5
    assert s["ev_kwh_per_car_per_year"] == pytest.approx(s["ev_kwh_per_car_per_day"] * 365)
    assert s["ev_implied_miles_per_year"] == pytest.approx(s["ev_kwh_per_car_per_year"] * 3.5)
    assert s["ev_mileage_check_ratio"] == pytest.approx(1.0, abs=0.1)


def test_admd_rises_with_charger_power():
    slow = apply_scenario(_frame(), 0.6, 0.0, ev_config=_cfg(charger_kw=3.6), seed=1).summary
    fast = apply_scenario(_frame(), 0.6, 0.0, ev_config=_cfg(charger_kw=22.0), seed=1).summary
    assert fast["ev_admd_kw"] > slow["ev_admd_kw"]
    assert fast["ev_kwh_per_car_per_day"] == pytest.approx(slow["ev_kwh_per_car_per_day"], rel=0.03)


def test_planning_metrics_without_evs():
    out = apply_scenario(_frame(), 0.0, 0.0, seed=1).summary
    assert out["ev_count"] == 0 and out["ev_admd_kw"] == 0.0
    assert np.isnan(
        ev_planning_metrics(pd.DataFrame(columns=["neighbourhood_id"]), {})["ev_mileage_check_ratio"]
    )


def test_sensitivity_headline_carries_ev_figures():
    frame = _frame()
    grid, _ = run_sensitivity_grid(
        frame, compute_thresholds(frame), ev_levels=[0.0, 0.4], hp_levels=[0.0], seed=3
    )
    assert {"ev_admd_kw", "ev_kwh_per_car_per_day", "ev_implied_miles_per_year"} <= set(grid.columns)
    headline = summarise_amplification(grid)
    assert headline["headline_ev_charger_kw"] == pytest.approx(EVConfig().charger_kw)
    assert headline["headline_ev_admd_kw"] > 0
