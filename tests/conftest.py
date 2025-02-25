"""Shared fixtures.

Tests run entirely offline against a small synthetic dataset so the suite is
fast, deterministic and independent of the licensed Low Carbon London extract
and of any external API.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from drg.config import load_config
from drg.data.synthetic import generate_synthetic_neighbourhoods


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def demand() -> pd.DataFrame:
    """~4 months of half-hourly demand for two neighbourhoods."""
    return (
        generate_synthetic_neighbourhoods(
            start="2013-10-01",
            end="2014-02-01",
            n_neighbourhoods=2,
            households_per_neighbourhood=80,
            seed=7,
        )
        .dropna(subset=["demand_kwh"])
        .reset_index(drop=True)
    )


@pytest.fixture(scope="session")
def small_index() -> pd.DatetimeIndex:
    return pd.date_range("2014-01-01", "2014-01-15", freq="30min", inclusive="left")


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(0)
