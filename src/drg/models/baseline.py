"""Interpretable baselines: seasonal naive and regularised linear regression.

The proposal names Linear Regression as the baseline. In practice a plain OLS
on 40+ correlated lag/rolling features is numerically unstable, so the module
exposes both an unpenalised ``LinearRegression`` (for the literal baseline
required by the write-up) and a ``Ridge`` variant used as the reported
benchmark; both sit behind a median-imputer + standard-scaler pipeline.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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


class BaselineForecaster:
    """Linear / Ridge regression pipeline over the engineered features."""

    def __init__(self, ridge: bool = True, alpha: float = 1.0, fit_intercept: bool = True) -> None:
        estimator = (
            Ridge(alpha=alpha, fit_intercept=fit_intercept)
            if ridge
            else LinearRegression(fit_intercept=fit_intercept)
        )
        self.name = "ridge_regression" if ridge else "linear_regression"
        self.pipeline = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", estimator),
            ]
        )
        self.feature_columns: list[str] = []

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "BaselineForecaster":
        self.feature_columns = list(X.columns)
        self.pipeline.fit(X, y)
        log.info("%s fitted on %s rows x %s features", self.name, f"{len(X):,}", X.shape[1])
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X[self.feature_columns] if self.feature_columns else X
        return np.clip(self.pipeline.predict(X), 0.0, None)

    # ------------------------------------------------------------- insight
    def coefficients(self) -> pd.DataFrame:
        model = self.pipeline.named_steps["model"]
        coefs = getattr(model, "coef_", None)
        if coefs is None:
            return pd.DataFrame(columns=["feature", "coefficient"])
        return (
            pd.DataFrame({"feature": self.feature_columns, "coefficient": coefs})
            .assign(abs_coefficient=lambda d: d["coefficient"].abs())
            .sort_values("abs_coefficient", ascending=False)
            .reset_index(drop=True)
        )

    def get_params(self) -> dict[str, Any]:
        return self.pipeline.named_steps["model"].get_params()
