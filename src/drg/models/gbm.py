"""XGBoost forecaster -- the primary model of the DRG framework.

Gradient boosting is used because the target responds to sharp, threshold-like
interactions (evening peak x cold temperature x weekday) that tree ensembles
capture directly, and because it exposes a fast exact TreeSHAP explainer for
the explainability objective.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


class XGBoostForecaster:
    name = "xgboost"

    DEFAULTS: dict[str, Any] = {
        "n_estimators": 700,
        "max_depth": 7,
        "learning_rate": 0.05,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "min_child_weight": 5,
        "reg_lambda": 1.5,
        "objective": "reg:squarederror",
        "tree_method": "hist",
        "n_jobs": 4,
        "random_state": 42,
    }

    def __init__(self, **params: Any) -> None:
        self.early_stopping_rounds = params.pop("early_stopping_rounds", 50)
        cfg = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        self.params = cfg
        self.model = xgb.XGBRegressor(**cfg)
        self.feature_columns: list[str] = []
        self.best_iteration: int | None = None

    # ------------------------------------------------------------------ fit
    def fit(
        self,
        X: pd.DataFrame,
        y: np.ndarray,
        X_val: pd.DataFrame | None = None,
        y_val: np.ndarray | None = None,
    ) -> "XGBoostForecaster":
        self.feature_columns = list(X.columns)
        fit_kwargs: dict[str, Any] = {"verbose": False}

        if X_val is not None and y_val is not None and len(X_val):
            fit_kwargs["eval_set"] = [(X[self.feature_columns], y), (X_val[self.feature_columns], y_val)]
            # xgboost >= 2.0 takes early stopping on the estimator, not in fit()
            try:
                self.model.set_params(early_stopping_rounds=self.early_stopping_rounds)
            except (TypeError, ValueError):  # pragma: no cover - older xgboost
                fit_kwargs["early_stopping_rounds"] = self.early_stopping_rounds

        self.model.fit(X[self.feature_columns], y, **fit_kwargs)
        self.best_iteration = getattr(self.model, "best_iteration", None)
        log.info(
            "xgboost fitted on %s rows x %s features (best_iteration=%s)",
            f"{len(X):,}",
            X.shape[1],
            self.best_iteration,
        )
        return self

    # -------------------------------------------------------------- predict
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        cols = self.feature_columns or list(X.columns)
        return np.clip(self.model.predict(X[cols]), 0.0, None)

    # -------------------------------------------------------------- insight
    def feature_importance(self, kind: str = "gain") -> pd.DataFrame:
        booster = self.model.get_booster()
        scores = booster.get_score(importance_type=kind)
        # map fN back to real names when xgboost stored positional names
        mapped = {}
        for key, value in scores.items():
            if key.startswith("f") and key[1:].isdigit():
                idx = int(key[1:])
                key = self.feature_columns[idx] if idx < len(self.feature_columns) else key
            mapped[key] = value
        df = pd.DataFrame({"feature": list(mapped), "importance": list(mapped.values())}).sort_values(
            "importance", ascending=False
        )
        total = df["importance"].sum()
        df["importance_pct"] = 100.0 * df["importance"] / total if total else 0.0
        return df.reset_index(drop=True)


def rolling_origin_validate(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    n_splits: int = 5,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Expanding-window (rolling-origin) validation over the training period.

    ``TimeSeriesSplit`` is applied to the chronologically ordered frame so each
    fold trains only on the past -- the correct protocol for load forecasting.
    """
    from sklearn.model_selection import TimeSeriesSplit

    from drg.models.evaluate import evaluate_forecast

    df = df.sort_values("timestamp").reset_index(drop=True)
    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows = []
    for fold, (tr_idx, te_idx) in enumerate(splitter.split(df), start=1):
        train, test = df.iloc[tr_idx], df.iloc[te_idx]
        model = XGBoostForecaster(**(params or {}))
        model.fit(train[feature_cols], train[target_col].to_numpy())
        preds = model.predict(test[feature_cols])
        metrics = evaluate_forecast(
            test[target_col], preds, timestamps=test["timestamp"], label=f"fold_{fold}"
        )
        metrics["fold"] = fold
        metrics["train_end"] = str(train["timestamp"].max())
        metrics["test_end"] = str(test["timestamp"].max())
        rows.append(metrics)
        log.info(
            "fold %s/%s  MAE=%.4f RMSE=%.4f R2=%.4f",
            fold,
            n_splits,
            metrics["mae"],
            metrics["rmse"],
            metrics["r2"],
        )
    return pd.DataFrame(rows)
