"""Household -> neighbourhood half-hourly aggregation (DRG-29).

Stress detection and forecasting operate at the level a network planner cares
about: a low-voltage neighbourhood of roughly 120 households, not a single
meter. This module turns household meter reads into neighbourhood demand.

Partial households are handled explicitly. Smart meters drop out (comms loss,
replacement, churn), so the number of households reporting in a half-hour
varies. A raw sum built from a varying household count is not comparable over
time: a neighbourhood whose meters go quiet for a week looks exactly like a
neighbourhood whose demand fell. Every aggregated row therefore carries

* ``n_households``            households that actually reported in that half-hour;
* ``n_households_registered`` households assigned to the neighbourhood;
* ``household_coverage``      ``n_households / n_households_registered``;
* ``demand_observed_kwh``     the raw sum over the reporting households;
* ``demand_per_household_kwh`` the observed sum divided by ``n_households``;
* ``demand_kwh``              per-household demand scaled back up to the
  registered count, so the series is comparable over time.

Half-hours whose coverage falls below ``min_household_coverage`` are too thin
to be trusted and their ``demand_kwh`` is set to NaN, so the cleaning stage
treats them as gaps (short ones interpolated, long ones dropped) instead of
reading them as a drop in demand.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

AGGREGATE_COLUMNS = [
    "timestamp",
    "neighbourhood_id",
    "demand_kwh",
    "demand_observed_kwh",
    "demand_per_household_kwh",
    "n_households",
    "n_households_registered",
    "household_coverage",
]


def neighbourhood_label(index: int) -> str:
    """Zero-based group index -> canonical id (``0 -> "N01"``)."""
    return f"N{index + 1:02d}"


def _hash_key(meter_id: object) -> int:
    digest = hashlib.blake2b(str(meter_id).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


# --------------------------------------------------------------------------
# membership
# --------------------------------------------------------------------------
def assign_neighbourhoods(
    household_ids: Iterable[object],
    n_neighbourhoods: int = 4,
    households_per_neighbourhood: int = 120,
) -> dict[str, str]:
    """Deterministically assign households to fixed-size neighbourhoods.

    Households are ordered by a stable hash of the meter id (independent of
    file order, so reruns and re-exports give the same groups), the first
    ``n_neighbourhoods * households_per_neighbourhood`` are kept and dealt
    round-robin, giving every neighbourhood the same size. Households beyond
    that budget are left unassigned and excluded from the aggregate. When
    fewer households exist than the budget, they are still spread evenly.
    """
    if n_neighbourhoods < 1:
        raise ValueError("n_neighbourhoods must be >= 1")
    if households_per_neighbourhood < 1:
        raise ValueError("households_per_neighbourhood must be >= 1")

    unique = {str(h) for h in household_ids if h is not None and not pd.isna(h)}
    ordered = sorted(unique, key=lambda h: (_hash_key(h), h))
    budget = n_neighbourhoods * households_per_neighbourhood
    selected = ordered[:budget]
    if len(selected) < budget:
        log.warning(
            "only %s households available for %s neighbourhoods x %s; groups will be smaller",
            len(selected),
            n_neighbourhoods,
            households_per_neighbourhood,
        )
    return {hid: neighbourhood_label(i % n_neighbourhoods) for i, hid in enumerate(selected)}


def registered_counts(membership: Mapping[str, str]) -> dict[str, int]:
    """Households assigned per neighbourhood."""
    counts: dict[str, int] = {}
    for nid in membership.values():
        counts[nid] = counts.get(nid, 0) + 1
    return counts


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------
def aggregate_household_reads(readings: pd.DataFrame, membership: Mapping[str, str]) -> pd.DataFrame:
    """Sum household reads into neighbourhood half-hours.

    ``readings`` needs ``household_id, timestamp, demand_kwh``. Households not
    in ``membership`` are dropped, timestamps are floored to the half-hour and
    repeated reads of the same household/half-hour are collapsed to one so a
    duplicated row can neither inflate the total nor the household count.

    Returns partial sums ``timestamp, neighbourhood_id, demand_observed_kwh,
    n_households`` that can be combined across chunks with
    :func:`combine_partial_aggregates`.
    """
    cols = ["timestamp", "neighbourhood_id", "demand_observed_kwh", "n_households"]
    if readings.empty:
        return pd.DataFrame(columns=cols)

    df = readings[["household_id", "timestamp", "demand_kwh"]].copy()
    df["household_id"] = df["household_id"].astype(str)
    df["neighbourhood_id"] = df["household_id"].map(membership)
    df = df.dropna(subset=["neighbourhood_id", "timestamp", "demand_kwh"])
    if df.empty:
        return pd.DataFrame(columns=cols)

    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.floor("30min")
    df = df.drop_duplicates(subset=["household_id", "timestamp"], keep="first")

    return (
        df.groupby(["timestamp", "neighbourhood_id"], observed=True)
        .agg(demand_observed_kwh=("demand_kwh", "sum"), n_households=("household_id", "nunique"))
        .reset_index()
    )


def combine_partial_aggregates(parts: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Merge chunk-level partial sums.

    Each household/half-hour is counted once within a chunk, and the LCL
    release is ordered by household, so summing both the energy and the
    household count across chunks gives the neighbourhood totals.
    """
    frames = [p for p in parts if p is not None and not p.empty]
    if not frames:
        return pd.DataFrame(columns=["timestamp", "neighbourhood_id", "demand_observed_kwh", "n_households"])
    return (
        pd.concat(frames, ignore_index=True)
        .groupby(["timestamp", "neighbourhood_id"], observed=True)
        .agg(demand_observed_kwh=("demand_observed_kwh", "sum"), n_households=("n_households", "sum"))
        .reset_index()
    )


def finalise_neighbourhood_demand(
    partial: pd.DataFrame,
    registered: Mapping[str, int],
    min_household_coverage: float = 0.5,
) -> pd.DataFrame:
    """Attach household counts and make totals comparable over time.

    ``partial`` needs ``timestamp, neighbourhood_id, demand_observed_kwh,
    n_households``. ``registered`` maps each neighbourhood to its assigned
    household count. See the module docstring for the output columns.
    """
    out = partial.copy()
    out["n_households"] = out["n_households"].fillna(0).astype(int)
    out["n_households_registered"] = (
        out["neighbourhood_id"].map(registered).fillna(out["n_households"]).astype(int)
    )
    # a neighbourhood can never report more meters than it has
    out["n_households_registered"] = np.maximum(out["n_households_registered"], out["n_households"])

    reporting = out["n_households"].where(out["n_households"] > 0)
    registered_nonzero = out["n_households_registered"].replace(0, np.nan)
    out["household_coverage"] = (out["n_households"] / registered_nonzero).fillna(0.0)
    out["demand_per_household_kwh"] = out["demand_observed_kwh"] / reporting
    out["demand_kwh"] = out["demand_per_household_kwh"] * out["n_households_registered"]

    thin = out["household_coverage"] < float(min_household_coverage)
    if thin.any():
        log.info(
            "masking %s neighbourhood half-hours below %.0f%% household coverage",
            f"{int(thin.sum()):,}",
            100 * float(min_household_coverage),
        )
    out.loc[thin, ["demand_kwh", "demand_per_household_kwh"]] = np.nan

    return out[AGGREGATE_COLUMNS].sort_values(["neighbourhood_id", "timestamp"]).reset_index(drop=True)


def aggregate_to_neighbourhoods(
    readings: pd.DataFrame,
    n_neighbourhoods: int = 4,
    households_per_neighbourhood: int = 120,
    min_household_coverage: float = 0.5,
    membership: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """One-shot household -> neighbourhood aggregation for in-memory reads."""
    if membership is None:
        membership = assign_neighbourhoods(
            readings["household_id"].unique(), n_neighbourhoods, households_per_neighbourhood
        )
    partial = aggregate_household_reads(readings, membership)
    return finalise_neighbourhood_demand(partial, registered_counts(membership), min_household_coverage)
