"""Training orchestration.

Trains the full model ladder on one set of chronological windows
(:class:`drg.models.windows.SplitWindows`, DRG-57) shared by every model:

1. seasonal naive (operational status quo),
2. linear regression and ridge (interpretable baselines),
3. XGBoost (primary model, early-stopped on the validation window),
4. LSTM (optional deep extension, skipped cleanly when torch is absent),

selects the champion on the *validation* window, then reports every model on
the held-out test window with MAE / RMSE / MAPE / R2 plus peak-period and
stress-alarm skill. The test window plays no part in fitting or selection.
Rolling-origin cross-validation runs on train + validation only, and the
resolved windows are persisted with the metrics and every model bundle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from drg.config import Config
from drg.features.engineering import feature_columns
from drg.models.baseline import BaselineForecaster, SeasonalNaiveForecaster
from drg.models.evaluate import evaluate_forecast, metrics_table
from drg.models.gbm import XGBoostForecaster, rolling_origin_validate
from drg.models.registry import ModelBundle, save_model
from drg.models.windows import SplitWindows, windows_from_config
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


@dataclass
class TrainingResult:
    best: ModelBundle
    metrics: pd.DataFrame
    cv_metrics: pd.DataFrame
    predictions: pd.DataFrame
    windows: SplitWindows | None = None
    validation_metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    bundles: dict[str, ModelBundle] = field(default_factory=dict)
    model_path: Path | None = None

    def headline(self) -> dict[str, Any]:
        """Test-window metrics of the champion (selected on validation)."""
        rows = self.metrics[self.metrics["model"] == self.best.name]
        row = (rows if len(rows) else self.metrics).iloc[0].to_dict()
        return {k: v for k, v in row.items() if not isinstance(v, (list, dict))}


def _global_stress_threshold(train: pd.DataFrame, percentile: float, target: str) -> float:
    return float(np.percentile(train[target].dropna(), percentile))


def train_models(
    features: pd.DataFrame,
    cfg: Config,
    *,
    train_lstm: bool | None = None,
    save: bool = True,
    windows: SplitWindows | None = None,
) -> TrainingResult:
    """Train, select and report the model ladder on one set of windows.

    ``windows`` defaults to the configured project windows resolved on
    ``features``. An empty window raises instead of borrowing rows from a
    neighbouring one, so training never leaks into validation or test.
    """
    mcfg = cfg.models
    target = "target"
    feat_cols = feature_columns(features)
    log.info("training on %s features: %s ...", len(feat_cols), ", ".join(feat_cols[:8]))

    windows = windows or windows_from_config(cfg, features["timestamp"])
    train, val, test = windows.split(features)
    window_meta = windows.to_dict()

    stress_threshold = _global_stress_threshold(
        train, float(cfg.stress.get("primary_percentile", 95)), target
    )

    results: list[dict[str, Any]] = []
    val_results: list[dict[str, Any]] = []
    bundles: dict[str, ModelBundle] = {}

    def _validate(label: str, pred: np.ndarray) -> None:
        val_results.append(
            evaluate_forecast(
                val[target],
                pred,
                timestamps=val["timestamp"],
                stress_threshold=stress_threshold,
                label=label,
            )
        )

    predictions = test[["timestamp", "neighbourhood_id", target]].copy()
    predictions = predictions.rename(columns={target: "actual"})

    # ---------------------------------------------------------------- naive
    naive = SeasonalNaiveForecaster()
    if "lag_48" in test.columns:
        naive.fit(train)
        _validate("seasonal_naive", naive.predict(val))
        pred = naive.predict(test)
        predictions["seasonal_naive"] = pred
        results.append(
            evaluate_forecast(
                test[target],
                pred,
                timestamps=test["timestamp"],
                stress_threshold=stress_threshold,
                label="seasonal_naive",
            )
        )

    # ------------------------------------------------------------- linear(s)
    for ridge, label in ((False, "linear_regression"), (True, "ridge_regression")):
        model = BaselineForecaster(
            ridge=ridge, fit_intercept=bool(cfg.get("models.baseline.fit_intercept", True))
        )
        model.fit(train[feat_cols], train[target].to_numpy())
        _validate(label, model.predict(val[feat_cols]))
        pred = model.predict(test[feat_cols])
        predictions[label] = pred
        results.append(
            evaluate_forecast(
                test[target],
                pred,
                timestamps=test["timestamp"],
                stress_threshold=stress_threshold,
                label=label,
            )
        )
        bundles[label] = ModelBundle(
            name=label,
            estimator=model,
            feature_columns=feat_cols,
            kind="sklearn",
            metadata={
                "train_rows": len(train),
                "train_end": str(train["timestamp"].max()),
                "windows": window_meta,
            },
            metrics=results[-1],
        )

    # -------------------------------------------------------------- xgboost
    xgb_params = dict(mcfg.get("xgboost", {}))
    xgb_params.setdefault("random_state", cfg.seed)
    gbm = XGBoostForecaster(**xgb_params)
    gbm.fit(train[feat_cols], train[target].to_numpy(), val[feat_cols], val[target].to_numpy())
    _validate("xgboost", gbm.predict(val[feat_cols]))
    pred = gbm.predict(test[feat_cols])
    predictions["xgboost"] = pred
    results.append(
        evaluate_forecast(
            test[target],
            pred,
            timestamps=test["timestamp"],
            stress_threshold=stress_threshold,
            label="xgboost",
        )
    )
    bundles["xgboost"] = ModelBundle(
        name="xgboost",
        estimator=gbm,
        feature_columns=feat_cols,
        kind="xgboost",
        metadata={
            "train_rows": len(train),
            "train_end": str(train["timestamp"].max()),
            "best_iteration": gbm.best_iteration,
            "windows": window_meta,
            "params": {k: str(v) for k, v in gbm.params.items()},
        },
        metrics=results[-1],
    )

    # ----------------------------------------------------------------- lstm
    want_lstm = bool(cfg.get("models.lstm.enabled", True)) if train_lstm is None else train_lstm
    if want_lstm:
        try:
            from drg.models.deep import (
                TORCH_AVAILABLE,
                LSTMForecaster,
                SequenceMLPForecaster,
            )

            deep_params = dict(mcfg.get("lstm", {}))
            deep_params.pop("enabled", None)
            deep_params.setdefault("seed", cfg.seed)

            if TORCH_AVAILABLE:
                deep: Any = LSTMForecaster(**deep_params)
                label, kind = "lstm", "torch"
            else:
                # PyTorch needs native runtime libraries that are not always
                # present; keep the neural arm of the study executable.
                log.warning(
                    "PyTorch unavailable -- training the scikit-learn sequence MLP instead "
                    "(install requirements-deep.txt plus the MSVC runtime for the LSTM)"
                )
                deep = SequenceMLPForecaster(**deep_params)
                label, kind = "mlp_sequence", "sklearn"

            deep.fit(train, feat_cols, target, val=val)
            _validate(label, deep.predict(val, target_col=target))
            pred = deep.predict(test, target_col=target)
            predictions[label] = pred
            results.append(
                evaluate_forecast(
                    test[target],
                    pred,
                    timestamps=test["timestamp"],
                    stress_threshold=stress_threshold,
                    label=label,
                )
            )
            bundles[label] = ModelBundle(
                name=label,
                estimator=deep,
                feature_columns=feat_cols,
                kind=kind,
                metadata={
                    "sequence_length": getattr(getattr(deep, "params", deep), "sequence_length", None),
                    "epochs_run": len(getattr(deep, "history", [])) or None,
                    "windows": window_meta,
                },
                metrics=results[-1],
            )
        except Exception as exc:
            log.warning("deep-learning stage skipped: %s", exc)

    # ------------------------------------------------------------ selection
    # The champion is chosen on the validation window; the test window is
    # only read below, for reporting.
    table = metrics_table(results)
    val_table = metrics_table(val_results)
    ranked = [r for r in val_table["model"].tolist() if r in bundles]
    best_name = ranked[0] if ranked else "xgboost"
    best = bundles[best_name]
    log.info(
        "champion model: %s (validation RMSE=%.4f)",
        best_name,
        float(val_table.loc[val_table["model"] == best_name, "rmse"].iloc[0]),
    )

    # ------------------------------------------- rolling-origin CV (champion)
    cv = pd.DataFrame()
    try:
        cv = rolling_origin_validate(
            pd.concat([train, val], ignore_index=True),
            feat_cols,
            target,
            n_splits=int(mcfg.get("n_splits", 5)),
            params=xgb_params,
        )
    except Exception as exc:  # pragma: no cover
        log.warning("rolling-origin validation skipped: %s", exc)

    model_path = None
    if save:
        for name, bundle in bundles.items():
            if bundle.kind != "torch":  # torch bundles are saved via their state dict
                save_model(bundle, cfg.paths.model_dir, filename=f"{name}.joblib")
        champion = ModelBundle(
            name=best.name,
            estimator=best.estimator,
            feature_columns=best.feature_columns,
            kind=best.kind,
            metadata={**best.metadata, "champion": True, "stress_threshold": stress_threshold},
            metrics=best.metrics,
        )
        # The API and the streaming engine call ``bundle.predict(design_matrix)``.
        # Sequence models need the full frame instead, so the served champion is
        # always a tabular model even when a sequence model scores better.
        if champion.name in {"lstm", "mlp_sequence"}:
            log.info(
                "%s scored best but is sequence-shaped; serving %s as the deployable champion",
                champion.name,
                "xgboost",
            )
            champion = bundles.get("xgboost", champion)
        model_path = save_model(champion, cfg.paths.model_dir, filename="best_model.joblib")

        cfg.paths.metrics_output.write_text(
            json.dumps(
                {
                    "test_metrics": results,
                    "cv_metrics": cv.to_dict(orient="records") if len(cv) else [],
                    "champion": best_name,
                    "selection_window": "validation",
                    "validation_metrics": val_results,
                    "windows": window_meta,
                    "stress_threshold_kwh": stress_threshold,
                    "n_features": len(feat_cols),
                    "features": feat_cols,
                    "train_window": [str(train["timestamp"].min()), str(train["timestamp"].max())],
                    "test_window": [str(test["timestamp"].min()), str(test["timestamp"].max())],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        predictions.to_parquet(cfg.paths.forecast_output, index=False)
        windows.save(cfg.paths.split_windows)

    return TrainingResult(
        best=best,
        metrics=table,
        cv_metrics=cv,
        predictions=predictions,
        windows=windows,
        validation_metrics=val_table,
        bundles=bundles,
        model_path=model_path,
    )
