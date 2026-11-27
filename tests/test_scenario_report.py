"""Scenario reporting artefacts (DRG-84)."""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pandas as pd
import pytest

from drg.analysis.scenario_report import (
    BASE_LABEL,
    diversity_gap_table,
    ladder,
    load_shape_profiles,
    load_shape_summary,
    peak_amplification_table,
    stress_escalation_table,
    write_scenario_report,
)
from drg.analysis.sensitivity import run_sensitivity_grid
from drg.simulation.electrification import apply_scenario
from drg.stress.detection import compute_thresholds

EV_LEVELS = [0.0, 0.4, 0.8]
HP_LEVELS = [0.0, 0.3, 0.7]


@pytest.fixture(scope="module")
def window(demand):
    return demand[demand["timestamp"] >= demand["timestamp"].max() - pd.Timedelta(days=40)]


@pytest.fixture(scope="module")
def grid(window):
    grid, _ = run_sensitivity_grid(
        window, compute_thresholds(window), ev_levels=EV_LEVELS, hp_levels=HP_LEVELS, seed=5
    )
    return grid


@pytest.fixture(scope="module")
def frames(window, grid):
    return {
        f"EV{ev}_HP{hp}": apply_scenario(window, ev, hp, seed=5).frame
        for ev, hp in ladder(grid)
        if ev or hp
    }


def test_peak_amplification_table_is_the_adoption_matrix(grid):
    table = peak_amplification_table(grid)
    assert list(table.index) == EV_LEVELS and list(table.columns) == HP_LEVELS
    assert table.loc[0.0, 0.0] == pytest.approx(0.0)
    assert (table.diff(axis=0).iloc[1:] > 0).all().all(), "more EVs must raise the peak"


def test_diversity_gap_table(grid):
    table = diversity_gap_table(grid)
    assert len(table) == 4, "one row per scenario with both technologies"
    amp = grid.set_index(["ev_adoption", "hp_adoption"])["peak_amplification_pct"]
    row = table[(table["ev_adoption"] == 0.8) & (table["hp_adoption"] == 0.7)].iloc[0]
    assert row["ev_only_amplification_pct"] == pytest.approx(amp[(0.8, 0.0)])
    assert row["heat_pump_only_amplification_pct"] == pytest.approx(amp[(0.0, 0.7)])
    assert row["additive_amplification_pct"] == pytest.approx(
        row["ev_only_amplification_pct"] + row["heat_pump_only_amplification_pct"]
    )
    assert row["diversity_gap_pp"] == pytest.approx(
        row["additive_amplification_pct"] - row["combined_amplification_pct"]
    )


def test_diversity_gap_prefers_same_draw_components():
    grid = pd.DataFrame(
        {
            "scenario": ["EV0_HP0", "EV50_HP0", "EV0_HP50", "EV50_HP50"],
            "ev_adoption": [0.0, 0.5, 0.0, 0.5],
            "hp_adoption": [0.0, 0.0, 0.5, 0.5],
            "peak_amplification_pct": [0.0, 60.0, 40.0, 85.0],
            "ev_only_peak_amplification_pct": [np.nan, np.nan, np.nan, 61.0],
            "heat_pump_only_peak_amplification_pct": [np.nan, np.nan, np.nan, 41.0],
        }
    )
    row = diversity_gap_table(grid).iloc[0]
    assert row["additive_amplification_pct"] == pytest.approx(102.0)
    assert row["diversity_gap_pp"] == pytest.approx(17.0)


def test_stress_escalation_table(grid):
    table = stress_escalation_table(grid)
    assert {"stress_frequency_pct", "mean_event_hours", "max_event_hours"} <= set(table.columns)
    assert len(table) == len(EV_LEVELS) * len(HP_LEVELS)
    base = table[(table["ev_adoption"] == 0) & (table["hp_adoption"] == 0)].iloc[0]
    worst = table[(table["ev_adoption"] == 0.8) & (table["hp_adoption"] == 0.7)].iloc[0]
    assert worst["stress_frequency_pct"] > base["stress_frequency_pct"]


def test_load_shape_profiles_and_widening(frames):
    profiles = load_shape_profiles(frames)
    assert set(profiles["scenario"]) == {BASE_LABEL, *frames}
    assert (profiles.groupby("scenario").size() == 48).all()

    summary = load_shape_summary(profiles).set_index("scenario")
    assert summary.loc[BASE_LABEL, "hours_above_base_peak"] == 0
    top = list(frames)[-1]
    assert summary.loc[top, "peak_kwh"] > summary.loc[BASE_LABEL, "peak_kwh"]
    assert summary.loc[top, "hours_above_base_peak"] > 0, "the electrified peak must widen"
    hours = int(summary.loc[top, "peak_time"][:2])
    assert 16 <= hours <= 23, "the amplification lands in the evening"
    assert summary.loc[top, "evening_share_of_added_energy"] > 0.3


def test_write_scenario_report_writes_every_artefact(tmp_path, grid, frames):
    art = write_scenario_report(grid, frames, tmp_path / "figures", tmp_path / "reports")
    assert set(art.figures) == {
        "peak_amplification",
        "diversity_gap",
        "stress_frequency_duration",
        "load_shape_overlay",
    }
    assert set(art.tables) == {
        "peak_amplification",
        "diversity_gap",
        "stress_escalation",
        "load_shape",
        "load_shape_summary",
    }
    for path in art.all_paths():
        assert path.exists() and path.stat().st_size > 0, path
    for path in art.figures.values():
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    manifest = json.loads(art.manifest.read_text(encoding="utf-8"))
    assert manifest["figures"]["load_shape_overlay"] == "scenario_load_shape_overlay.png"
    assert "worst_case_diversity_gap_pp" in manifest["headline"]

    summary = art.summary.read_text(encoding="utf-8")
    for heading in ("Peak amplification", "Diversity gap", "Stress frequency", "Load shape"):
        assert heading in summary


def test_report_without_load_shape_frames(tmp_path, grid):
    art = write_scenario_report(grid, {}, tmp_path / "f", tmp_path / "r")
    assert "load_shape_overlay" not in art.figures
    assert art.summary.exists()


def test_scenarios_stage_regenerates_the_artefacts(cfg, demand, tmp_path):
    from drg.pipeline import stage_scenarios

    window = demand[demand["timestamp"] >= demand["timestamp"].max() - pd.Timedelta(days=30)]
    local = dataclasses.replace(cfg, raw=json.loads(json.dumps(cfg.raw, default=str)))
    local.paths = dataclasses.replace(
        cfg.paths, figure_dir=tmp_path / "figures", report_dir=tmp_path / "reports"
    )
    local.paths.report_dir.mkdir(parents=True)
    local.raw["electrification"]["ev"]["adoption_levels"] = [0.0, 0.8]
    local.raw["electrification"]["heat_pump"]["adoption_levels"] = [0.0, 0.7]
    local.raw["electrification"]["monte_carlo_runs"] = 1

    _, headline, _ = stage_scenarios(local, window)
    artefacts = headline["report_artefacts"]
    assert len(artefacts["figures"]) == 4
    assert (tmp_path / "reports" / "scenario_report.md").exists()
    assert (tmp_path / "figures" / "scenario_load_shape_overlay.png").exists()
