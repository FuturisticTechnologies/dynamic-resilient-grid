"""Household -> neighbourhood aggregation tests (DRG-29)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from drg.data.aggregation import (
    aggregate_household_reads,
    aggregate_to_neighbourhoods,
    assign_neighbourhoods,
    combine_partial_aggregates,
    finalise_neighbourhood_demand,
    registered_counts,
)
from drg.data.lcl_loader import clean_demand, load_lcl_halfhourly
from drg.data.synthetic import generate_synthetic_neighbourhoods
from drg.features.engineering import feature_columns


def _reads(household_ids, index, kwh=0.5) -> pd.DataFrame:
    return pd.DataFrame(
        [(h, t, kwh) for h in household_ids for t in index],
        columns=["household_id", "timestamp", "demand_kwh"],
    )


# --------------------------------------------------------------------------
# membership
# --------------------------------------------------------------------------
def test_four_neighbourhoods_of_120_households():
    ids = [f"MAC{i:06d}" for i in range(600)]
    membership = assign_neighbourhoods(ids, n_neighbourhoods=4, households_per_neighbourhood=120)
    assert registered_counts(membership) == {"N01": 120, "N02": 120, "N03": 120, "N04": 120}
    assert len(membership) == 480, "households beyond the budget are excluded"


def test_membership_is_independent_of_input_order():
    ids = [f"MAC{i:06d}" for i in range(300)]
    a = assign_neighbourhoods(ids, 4, 50)
    b = assign_neighbourhoods(list(reversed(ids)), 4, 50)
    assert a == b


def test_membership_spreads_a_short_population_evenly():
    counts = registered_counts(assign_neighbourhoods([f"H{i}" for i in range(10)], 4, 120))
    assert sum(counts.values()) == 10
    assert max(counts.values()) - min(counts.values()) <= 1


def test_membership_rejects_bad_sizes():
    with pytest.raises(ValueError):
        assign_neighbourhoods(["a"], 0, 10)
    with pytest.raises(ValueError):
        assign_neighbourhoods(["a"], 1, 0)


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------
def test_household_count_is_retained_per_half_hour():
    index = pd.date_range("2013-01-01", periods=4, freq="30min")
    ids = [f"H{i}" for i in range(10)]
    reads = _reads(ids, index)
    # half the meters miss the third half-hour
    reads = reads[~((reads["timestamp"] == index[2]) & reads["household_id"].isin(ids[:5]))]

    out = aggregate_to_neighbourhoods(reads, n_neighbourhoods=1, households_per_neighbourhood=10)
    assert out["n_households"].tolist() == [10, 10, 5, 10]
    assert (out["n_households_registered"] == 10).all()
    assert out["household_coverage"].tolist() == [1.0, 1.0, 0.5, 1.0]
    assert out["demand_observed_kwh"].tolist() == pytest.approx([5.0, 5.0, 2.5, 5.0])


def test_partial_households_do_not_look_like_a_demand_drop():
    index = pd.date_range("2013-01-01", periods=4, freq="30min")
    ids = [f"H{i}" for i in range(10)]
    reads = _reads(ids, index)
    reads = reads[~((reads["timestamp"] == index[2]) & reads["household_id"].isin(ids[:3]))]

    out = aggregate_to_neighbourhoods(reads, n_neighbourhoods=1, households_per_neighbourhood=10)
    # observed total dips with the missing meters, the comparable total does not
    assert out.loc[2, "demand_observed_kwh"] == pytest.approx(3.5)
    assert out["demand_kwh"].tolist() == pytest.approx([5.0] * 4)
    assert out["demand_per_household_kwh"].tolist() == pytest.approx([0.5] * 4)


def test_low_coverage_half_hours_are_masked():
    index = pd.date_range("2013-01-01", periods=3, freq="30min")
    ids = [f"H{i}" for i in range(10)]
    reads = _reads(ids, index)
    reads = reads[~((reads["timestamp"] == index[1]) & reads["household_id"].isin(ids[:8]))]

    out = aggregate_to_neighbourhoods(
        reads, n_neighbourhoods=1, households_per_neighbourhood=10, min_household_coverage=0.5
    )
    assert np.isnan(out.loc[1, "demand_kwh"])
    assert out.loc[1, "n_households"] == 2, "the real count is kept even when demand is masked"
    assert out.loc[1, "demand_observed_kwh"] == pytest.approx(1.0)


def test_duplicate_reads_are_counted_once():
    index = pd.date_range("2013-01-01", periods=2, freq="30min")
    reads = _reads(["H1", "H2"], index)
    reads = pd.concat([reads, reads.iloc[[0]]], ignore_index=True)
    partial = aggregate_household_reads(reads, {"H1": "N01", "H2": "N01"})
    assert partial["n_households"].tolist() == [2, 2]
    assert partial["demand_observed_kwh"].tolist() == pytest.approx([1.0, 1.0])


def test_unassigned_households_are_excluded():
    index = pd.date_range("2013-01-01", periods=2, freq="30min")
    reads = _reads(["H1", "H2", "OUTSIDER"], index)
    partial = aggregate_household_reads(reads, {"H1": "N01", "H2": "N02"})
    assert set(partial["neighbourhood_id"]) == {"N01", "N02"}
    assert partial["n_households"].sum() == 4


def test_chunk_partials_combine_to_the_one_shot_result():
    index = pd.date_range("2013-01-01", periods=6, freq="30min")
    ids = [f"H{i}" for i in range(20)]
    reads = _reads(ids, index)
    membership = assign_neighbourhoods(ids, 2, 10)

    one_shot = finalise_neighbourhood_demand(
        aggregate_household_reads(reads, membership), registered_counts(membership)
    )
    chunks = [reads.iloc[i : i + 37] for i in range(0, len(reads), 37)]
    chunked = finalise_neighbourhood_demand(
        combine_partial_aggregates(aggregate_household_reads(c, membership) for c in chunks),
        registered_counts(membership),
    )
    pd.testing.assert_frame_equal(one_shot, chunked)


# --------------------------------------------------------------------------
# pipeline integration
# --------------------------------------------------------------------------
def test_lcl_loader_end_to_end(cfg, tmp_path):
    index = pd.date_range("2013-01-01", periods=48, freq="30min")
    ids = [f"MAC{i:06d}" for i in range(500)]
    raw = _reads(ids, index, kwh=0.2)
    raw.columns = ["LCLid", "DateTime", "KWH/hh (per half hour) "]
    raw.insert(1, "stdorToU", "Std")
    path = tmp_path / "lcl.csv"
    raw.to_csv(path, index=False)

    out = load_lcl_halfhourly(cfg, files=[path])
    assert out["neighbourhood_id"].nunique() == 4
    assert (out["n_households_registered"] == 120).all()
    assert (out["n_households"] == 120).all()
    assert out["demand_kwh"].to_numpy() == pytest.approx(24.0)


def test_synthetic_matches_the_aggregation_schema():
    df = generate_synthetic_neighbourhoods("2013-01-01", "2013-03-01", 2, 120, seed=11)
    for col in ["n_households", "n_households_registered", "household_coverage", "demand_observed_kwh"]:
        assert col in df.columns
    assert (df["n_households"] <= df["n_households_registered"]).all()
    assert df["n_households"].nunique() > 1, "the reporting count must vary over time"


def test_cleaning_keeps_counts_and_flags_imputed_rows(cfg):
    index = pd.date_range("2014-01-01", periods=96, freq="30min")
    reads = _reads([f"H{i}" for i in range(10)], index)
    agg = aggregate_to_neighbourhoods(reads, 1, 10)
    agg = agg.drop(index=[40, 41]).reset_index(drop=True)

    out = clean_demand(agg, cfg)
    assert len(out) == len(index)
    gap = out["timestamp"].isin(index[[40, 41]])
    assert out.loc[gap, "is_imputed"].all()
    assert (out.loc[gap, "n_households"] == 0).all()
    assert (out["n_households_registered"] == 10).all()
    assert not out.loc[~gap, "is_imputed"].any()


def test_same_period_aggregation_columns_are_not_features():
    df = generate_synthetic_neighbourhoods("2013-01-01", "2013-01-05", 1, 50, seed=2)
    cols = feature_columns(df)
    for leaky in ["demand_observed_kwh", "demand_per_household_kwh", "n_households", "household_coverage"]:
        assert leaky not in cols
    assert "n_households_registered" in cols
