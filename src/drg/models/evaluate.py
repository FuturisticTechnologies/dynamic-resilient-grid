"""Forecast evaluation metrics.

Beyond the headline accuracy metrics required by the proposal (MAE, RMSE,
MAPE, R2) the module reports metrics that matter for a *stress* application:
accuracy restricted to the evening peak, and the classification skill of the
forecast when it is used as a stress alarm against a percentile threshold.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100.0)


def _smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    denom = np.where(denom == 0, 1e-6, denom)
    return float(np.mean(np.abs(y_true - y_pred) / denom) * 100.0)


def evaluate_forecast(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    *,
    timestamps: pd.Series | None = None,
    stress_threshold: float | None = None,
    label: str = "model",
) -> dict[str, Any]:
    """Return the full metric dictionary for one model / one split."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]
    if y_true.size == 0:
        return {"model": label, "n": 0}

    err = y_true - y_pred
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))

    out: dict[str, Any] = {
        "model": label,
        "n": int(y_true.size),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mape": _safe_mape(y_true, y_pred),
        "smape": _smape(y_true, y_pred),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "bias": float(np.mean(err)),
        "max_abs_error": float(np.max(np.abs(err))),
        "p95_abs_error": float(np.percentile(np.abs(err), 95)),
    }
    denom = float(np.mean(y_true))
    out["nrmse_pct"] = float(out["rmse"] / denom * 100.0) if denom else float("nan")

    # ---- peak-period accuracy --------------------------------------------
    if timestamps is not None:
        ts = pd.Series(pd.to_datetime(pd.Series(timestamps).to_numpy()[mask]))
        period = ts.dt.hour * 2 + ts.dt.minute // 30
        peak = ((period >= 34) & (period <= 43)).to_numpy()
        if peak.any():
            pe = y_true[peak] - y_pred[peak]
            out["peak_mae"] = float(np.mean(np.abs(pe)))
            out["peak_rmse"] = float(np.sqrt(np.mean(pe**2)))
            out["peak_mape"] = _safe_mape(y_true[peak], y_pred[peak])

    # ---- stress-alarm skill ----------------------------------------------
    if stress_threshold is not None:
        actual = y_true >= stress_threshold
        predicted = y_pred >= stress_threshold
        tp = int(np.sum(actual & predicted))
        fp = int(np.sum(~actual & predicted))
        fn = int(np.sum(actual & ~predicted))
        tn = int(np.sum(~actual & ~predicted))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        out.update(
            {
                "stress_threshold": float(stress_threshold),
                "stress_tp": tp,
                "stress_fp": fp,
                "stress_fn": fn,
                "stress_tn": tn,
                "stress_precision": float(precision),
                "stress_recall": float(recall),
                "stress_f1": (
                    float(2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
                ),
            }
        )
    return out


def metrics_table(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Tidy comparison table sorted by RMSE (lower is better)."""
    df = pd.DataFrame(results)
    if "rmse" in df.columns:
        df = df.sort_values("rmse").reset_index(drop=True)
    return df


def seasonal_naive(df: pd.DataFrame, target: str = "demand_kwh", period: int = 48) -> np.ndarray:
    """Benchmark: demand equals the value at the same period yesterday."""
    return df.groupby("neighbourhood_id", observed=True)[target].shift(period).to_numpy()
