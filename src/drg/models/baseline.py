"""Interpretable baselines: seasonal naive and regularised linear regression.

The proposal names Linear Regression as the baseline. In practice a plain OLS
on 40+ correlated lag/rolling features is numerically unstable, so the module
exposes both an unpenalised ``LinearRegression`` (for the literal baseline
required by the write-up) and a ``Ridge`` variant used as the reported
benchmark; both sit behind a median-imputer + standard-scaler pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


class SeasonalNaiveForecaster:
    """Predict the observed demand from the same half-hour one day earlier.

    This is the operational status quo it is fair to beat, and it needs no
    fitting -- it simply reads the ``lag_48`` feature.
    """

    name = "seasonal_naive"

    def __init__(self, lag_column: str = "lag_48") -> None:
        self.lag_column = lag_column
        self.feature_columns: list[str] = [lag_column]

    def fit(self, X: pd.DataFrame, y: np.ndarray | None = None) -> "SeasonalNaiveForecaster":
        if self.lag_column not in X.columns:
            raise KeyError(f"{self.lag_column} missing; cannot run seasonal naive")
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.asarray(X[self.lag_column], dtype=float)
