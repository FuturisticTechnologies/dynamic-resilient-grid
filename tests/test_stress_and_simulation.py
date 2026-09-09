"""Stress detection, electrification simulation and sensitivity tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from drg.analysis.sensitivity import elasticity_curve, run_sensitivity_grid, summarise_amplification
from drg.simulation.electrification import (
    EVConfig,
    HeatPumpConfig,
    apply_scenario,
    simulate_ev_load,
    simulate_heat_pump_load,
)
from drg.stress.detection import (
    compute_thresholds,
    detect_stress,
    stress_events,
    stress_summary,
)


# ---------------------------------------------------------------- stress ---
def test_threshold_is_the_95th_percentile(demand):
    th = compute_thresholds(demand, percentile=95.0)
    for nid, t in th.items():
        values = demand[demand["neighbourhood_id"] == nid]["demand_kwh"]
        assert t.primary_kwh == pytest.approx(np.percentile(values, 95))
        assert t.sensitivity_kwh == pytest.approx(values.mean() + 2 * values.std(ddof=1))


def test_stress_flags_about_five_percent_of_periods(demand):
    flagged = detect_stress(demand, compute_thresholds(demand, percentile=95.0))
    rate = flagged["is_stress"].mean()
    assert 0.045 <= rate <= 0.055


def test_stress_events_are_contiguous_runs():
    index = pd.date_range("2014-01-01", periods=20, freq="30min")
    values = np.full(20, 1.0)
    values[5:9] = 100.0  # one 2-hour event
    values[15] = 100.0  # single period -> below min_periods
    df = pd.DataFrame(
        {
            "timestamp": index,
            "neighbourhood_id": "N01",
            "demand_kwh": values,
            "n_households": 10,
        }
    )
    flagged = detect_stress(df, compute_thresholds(df, percentile=95.0))
    events = stress_events(flagged, min_periods=2)
    assert len(events) == 1
    assert events["duration_periods"].iloc[0] == 4
    assert events["duration_hours"].iloc[0] == 2.0
    assert events["peak_kwh"].iloc[0] == 100.0


def test_stress_summary_columns(demand):
    thresholds = compute_thresholds(demand)
    flagged = detect_stress(demand, thresholds)
    events = stress_events(flagged, min_periods=2)
    summary = stress_summary(flagged, events)
    expected = {"stress_frequency_pct", "stress_hours_per_week", "n_events"}
    assert expected <= set(summary.columns)
    assert (summary["load_factor"] > 0).all() and (summary["load_factor"] < 1).all()


# ------------------------------------------------------------ EV / heat ----
def test_ev_load_is_zero_without_adoption(small_index):
    assert simulate_ev_load(small_index, 100, 0.0).sum() == 0


def test_ev_load_concentrates_in_the_evening(small_index):
    load = simulate_ev_load(small_index, 100, 0.5, EVConfig(), seed=1, runs=4)
    period = small_index.hour * 2 + small_index.minute // 30
    by_period = pd.Series(load).groupby(period.to_numpy()).mean()
    assert 34 <= by_period.idxmax() <= 47, "EV peak must fall inside/just after the window"
    assert by_period.loc[10:20].mean() < by_period.loc[34:43].mean() * 0.2


def test_ev_energy_scales_with_adoption(small_index):
    low = simulate_ev_load(small_index, 100, 0.2, seed=2, runs=3).sum()
    high = simulate_ev_load(small_index, 100, 0.8, seed=2, runs=3).sum()
    assert high == pytest.approx(low * 4, rel=0.25)


def test_ev_daily_energy_is_physically_plausible(small_index):
    """~5-7 kWh per car per day matches average UK car mileage."""
    cfg = EVConfig()
    n_cars = 100
    load = simulate_ev_load(small_index, n_cars, 1.0, cfg, seed=3, runs=5)
    days = len(small_index) / 48
    per_car_per_day = load.sum() / n_cars / days
    assert 3.0 < per_car_per_day < 9.0


def test_ev_respects_the_charger_rating(small_index):
    """A single car can never draw more than the charger rating."""
    cfg = EVConfig(diversity_factor=1.0)
    load = simulate_ev_load(small_index, 1, 1.0, cfg, seed=4, runs=1)
    assert load.max() <= cfg.charger_kw * 0.5 + 1e-9


def test_heat_pump_responds_to_temperature(small_index):
    cold = simulate_heat_pump_load(small_index, 100, 0.5, np.full(len(small_index), -2.0), seed=1)
    mild = simulate_heat_pump_load(small_index, 100, 0.5, np.full(len(small_index), 16.0), seed=1)
    assert cold.sum() > mild.sum() * 5
    assert mild.sum() == pytest.approx(0.0, abs=1e-6)


def test_heat_pump_respects_the_rating(small_index):
    cfg = HeatPumpConfig(diversity_factor=1.0)
    load = simulate_heat_pump_load(small_index, 1, 1.0, np.full(len(small_index), -25.0), cfg, seed=1, runs=1)
    assert load.max() <= cfg.rated_kw * 0.5 + 1e-9


def test_scenario_adds_load_and_reports_admd(demand):
    result = apply_scenario(demand, 0.4, 0.3, seed=11, runs=1)
    frame = result.frame
    assert (frame["electrified_kwh"] >= frame["base_kwh"] - 1e-9).all()
    assert np.allclose(frame["electrified_kwh"], frame["base_kwh"] + frame["ev_kwh"] + frame["heat_pump_kwh"])
    assert result.summary["peak_amplification_pct"] > 0
    # after-diversity maximum demand should land near published DNO figures
    assert 0.5 < result.summary["ev_admd_kw"] < 3.0
    assert 0.3 < result.summary["heat_pump_admd_kw"] < 3.0


def test_zero_adoption_scenario_is_a_no_op(demand):
    result = apply_scenario(demand, 0.0, 0.0, seed=11)
    assert np.allclose(result.frame["electrified_kwh"], result.frame["base_kwh"])
    assert result.summary["peak_amplification_pct"] == pytest.approx(0.0)


def test_scenario_is_reproducible(demand):
    a = apply_scenario(demand, 0.4, 0.2, seed=99).frame["electrified_kwh"].to_numpy()
    b = apply_scenario(demand, 0.4, 0.2, seed=99).frame["electrified_kwh"].to_numpy()
    assert np.allclose(a, b)


# --------------------------------------------------------- sensitivity -----
def test_sensitivity_grid_is_monotonic_in_adoption(demand):
    window = demand[demand["timestamp"] >= demand["timestamp"].max() - pd.Timedelta(days=30)]
    thresholds = compute_thresholds(demand)
    grid, _ = run_sensitivity_grid(
        window,
        thresholds,
        ev_levels=[0.0, 0.4, 0.8],
        hp_levels=[0.0, 0.5],
        seed=5,
        runs=1,
    )
    assert len(grid) == 6
    for _, sub in grid.groupby("hp_adoption"):
        peaks = sub.sort_values("ev_adoption")["peak_amplification_pct"].to_numpy()
        assert np.all(np.diff(peaks) > 0), "more EVs must mean a higher peak"

    base = grid[(grid["ev_adoption"] == 0) & (grid["hp_adoption"] == 0)]
    assert base["peak_amplification_pct"].iloc[0] == pytest.approx(0.0, abs=1e-6)

    headline = summarise_amplification(grid)
    assert headline["worst_case_scenario"] == "EV80_HP50"
    assert headline["n_scenarios"] == 6

    curves = elasticity_curve(grid, hold="hp_adoption")
    assert "elasticity_pct_per_10pp" in curves.columns
    assert len(curves) == 6
