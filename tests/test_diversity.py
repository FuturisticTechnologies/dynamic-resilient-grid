"""Household diversity in combined EV + heat-pump scenarios (DRG-80)."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from drg.analysis.sensitivity import run_sensitivity_grid, summarise_amplification
from drg.data.synthetic import generate_synthetic_neighbourhoods
from drg.simulation import (
    DiversityError,
    EVConfig,
    HeatPumpConfig,
    apply_scenario,
    check_peak_diversity,
    simulate_neighbourhood_load,
)
from drg.simulation.household import (
    adopter_mask,
    ev_household_profiles,
    heat_pump_household_profiles,
)
from drg.stress.detection import compute_thresholds


@pytest.fixture(scope="module")
def winter():
    """Six winter months, 2 sites x 100 households: both technologies matter."""
    return (
        generate_synthetic_neighbourhoods("2013-10-01", "2014-04-01", 2, 100, seed=21)
        .dropna(subset=["demand_kwh"])
        .reset_index(drop=True)
    )


# --------------------------------------------------------------- adopters --
def test_adopter_mask_draws_the_configured_share(rng):
    mask = adopter_mask(120, 0.7, rng)
    assert mask.dtype == bool and mask.sum() == 84
    assert adopter_mask(120, 0.0, rng).sum() == 0
    assert adopter_mask(0, 0.5, rng).size == 0


def test_ev_draws_do_not_depend_on_heat_pump_adoption(small_index):
    alone = simulate_neighbourhood_load(small_index, 100, 0.6, 0.0, ev_seed=5, hp_seed=9)
    mixed = simulate_neighbourhood_load(small_index, 100, 0.6, 0.5, ev_seed=5, hp_seed=9)
    assert np.allclose(alone.ev_kwh, mixed.ev_kwh)


# ------------------------------------------------------- household level ---
def test_household_profiles_are_per_household(small_index, rng):
    owners = np.zeros(10, dtype=bool)
    owners[[1, 4]] = True
    ev = ev_household_profiles(small_index, owners, EVConfig(diversity_factor=1.0), rng)
    assert ev.shape == (len(small_index), 10)
    assert ev[:, ~owners].sum() == 0
    assert ev.max() <= EVConfig().charger_kw * 0.5 + 1e-9


def test_heat_pumps_do_not_peak_in_lock_step(small_index, rng):
    owners = np.ones(60, dtype=bool)
    cold = np.full(len(small_index), 0.0)
    hp = heat_pump_household_profiles(small_index, owners, cold, HeatPumpConfig(), rng)
    one_day = hp[: 48 * 1]
    peak_period = one_day.argmax(axis=0)
    assert len(set(peak_period.tolist())) > 5, "households must not all peak in the same half-hour"
    # aggregate peak is below households x individual peak: timing diversity
    assert one_day.sum(axis=1).max() < one_day.max(axis=0).sum()


def test_total_is_the_once_aggregated_superposition(small_index):
    load = simulate_neighbourhood_load(small_index, 80, 0.5, 0.5, None, runs=3, ev_seed=1, hp_seed=2)
    assert load.total_runs.shape == (3, len(small_index))
    assert np.allclose(load.total_runs, load.ev_runs + load.heat_pump_runs)
    lo, hi = load.band("total")
    assert (lo <= load.total_kwh + 1e-9).all() and (load.total_kwh <= hi + 1e-9).all()
    assert load.n_ev == 40 and load.n_heat_pump == 40


# --------------------------------------------------------- scenario level --
def test_combined_peak_is_strictly_below_the_sum_of_individual_peaks(winter):
    result = apply_scenario(winter, 0.8, 0.7, seed=42)
    frame = result.frame
    for _, sub in frame.groupby("neighbourhood_id"):
        added = sub["electrified_kwh"] - sub["base_kwh"]
        assert added.max() < sub["ev_kwh"].max() + sub["heat_pump_kwh"].max()


def test_combined_amplification_is_below_additive(winter):
    s = apply_scenario(winter, 0.8, 0.7, seed=42).summary
    assert s["ev_only_peak_amplification_pct"] > 0 and s["heat_pump_only_peak_amplification_pct"] > 0
    assert s["peak_amplification_pct"] < s["additive_peak_amplification_pct"]
    assert s["diversity_gain_pp"] > 0


def test_matched_components_equal_single_technology_runs(winter):
    combined = apply_scenario(winter, 0.6, 0.5, seed=8).summary
    ev_only = apply_scenario(winter, 0.6, 0.0, seed=8).summary
    hp_only = apply_scenario(winter, 0.0, 0.5, seed=8).summary
    assert combined["ev_only_peak_amplification_pct"] == pytest.approx(ev_only["peak_amplification_pct"])
    assert combined["heat_pump_only_peak_amplification_pct"] == pytest.approx(
        hp_only["peak_amplification_pct"]
    )


def _lock_step_frame() -> tuple[pd.DataFrame, dict]:
    ts = pd.date_range("2014-01-01", periods=48, freq="30min")
    ev = np.zeros(48)
    hp = np.zeros(48)
    ev[38] = hp[38] = 5.0  # both technologies peak in the same half-hour
    base = np.full(48, 10.0)
    frame = pd.DataFrame(
        {
            "timestamp": ts,
            "neighbourhood_id": "N01",
            "base_kwh": base,
            "ev_kwh": ev,
            "heat_pump_kwh": hp,
            "electrified_kwh": base + ev + hp,
        }
    )
    summary = {
        "ev_adoption": 0.5,
        "hp_adoption": 0.5,
        "peak_amplification_pct": 100.0,
        "ev_only_peak_amplification_pct": 50.0,
        "heat_pump_only_peak_amplification_pct": 50.0,
    }
    return frame, summary


def test_lock_step_peaks_raise_diversity_error():
    frame, summary = _lock_step_frame()
    with pytest.raises(DiversityError):
        check_peak_diversity(frame, summary)


def test_check_is_skipped_without_both_technologies():
    frame, summary = _lock_step_frame()
    check_peak_diversity(frame, {**summary, "hp_adoption": 0.0})


def test_super_additive_amplification_only_warns(caplog):
    frame, summary = _lock_step_frame()
    frame.loc[38, "heat_pump_kwh"] = 4.0  # loads no longer add exactly
    frame["electrified_kwh"] = frame["base_kwh"] + frame["ev_kwh"] + frame["heat_pump_kwh"] - 0.5
    with caplog.at_level(logging.WARNING):
        check_peak_diversity(frame, {**summary, "peak_amplification_pct": 120.0})
    assert "not below" in caplog.text


# ------------------------------------------------------------ sensitivity --
def test_sensitivity_grid_reports_diversity(winter):
    window = winter[winter["timestamp"] >= winter["timestamp"].max() - pd.Timedelta(days=45)]
    grid, _ = run_sensitivity_grid(
        window,
        compute_thresholds(window),
        ev_levels=[0.0, 0.8],
        hp_levels=[0.0, 0.7],
        seed=3,
    )
    assert {"additive_peak_amplification_pct", "diversity_gain_pp"} <= set(grid.columns)
    both = grid[(grid["ev_adoption"] > 0) & (grid["hp_adoption"] > 0)].iloc[0]
    assert both["diversity_gain_pp"] == pytest.approx(
        both["additive_peak_amplification_pct"] - both["peak_amplification_pct"]
    )
    headline = summarise_amplification(grid)
    assert headline["combined_vs_additive_pp"] == pytest.approx(-headline["worst_case_diversity_gain_pp"])
