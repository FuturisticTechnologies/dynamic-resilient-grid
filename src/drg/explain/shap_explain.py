"""SHAP explainability for the demand and stress models.

TreeSHAP gives exact Shapley values for the XGBoost champion in near-linear
time, so the framework can answer research question 4 -- *which temporal and
statistical features drive high-demand stress* -- both globally (mean absolute
SHAP ranking) and locally (why this particular half-hour was flagged).

The module deliberately separates two views:

* **global drivers** over a representative sample of the test window;
* **stress-period drivers**, restricted to observations above the stress
  threshold, which is what a network planner actually needs to interpret.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


@dataclass
class ShapReport:
    global_importance: pd.DataFrame
    stress_importance: pd.DataFrame = field(default_factory=pd.DataFrame)
    values: np.ndarray | None = None
    sample: pd.DataFrame | None = None
    base_value: float = 0.0
    figures: list[Path] = field(default_factory=list)

    def top(self, n: int = 15) -> pd.DataFrame:
        return self.global_importance.head(n)

    def explain_row(self, i: int, n: int = 8) -> pd.DataFrame:
        """Local attribution for one observation, largest contribution first."""
        if self.values is None or self.sample is None:
            raise RuntimeError("SHAP values were not retained")
        contrib = pd.DataFrame(
            {
                "feature": self.sample.columns,
                "value": self.sample.iloc[i].to_numpy(),
                "shap_value": self.values[i],
            }
        )
        contrib["abs"] = contrib["shap_value"].abs()
        return contrib.sort_values("abs", ascending=False).head(n).drop(columns="abs")


def _mean_abs_importance(values: np.ndarray, columns: list[str]) -> pd.DataFrame:
    mean_abs = np.abs(values).mean(axis=0)
    mean_signed = values.mean(axis=0)
    df = pd.DataFrame(
        {
            "feature": columns,
            "mean_abs_shap": mean_abs,
            "mean_shap": mean_signed,
        }
    ).sort_values("mean_abs_shap", ascending=False)
    total = df["mean_abs_shap"].sum()
    df["contribution_pct"] = 100.0 * df["mean_abs_shap"] / total if total else 0.0
    return df.reset_index(drop=True)


def explain_model(
    model: Any,
    X: pd.DataFrame,
    *,
    stress_mask: np.ndarray | pd.Series | None = None,
    sample_size: int = 4000,
    seed: int = 42,
    figure_dir: str | Path | None = None,
) -> ShapReport:
    """Compute global + stress-conditional SHAP attributions.

    ``model`` may be a DRG forecaster wrapper (``XGBoostForecaster``), a raw
    xgboost/sklearn estimator, or anything SHAP can wrap; tree models take the
    exact TreeSHAP path, everything else falls back to a sampled explainer.
    """
    import shap

    estimator = getattr(model, "model", None) or getattr(model, "pipeline", None) or model
    columns = list(getattr(model, "feature_columns", X.columns))
    X = X[columns]

    rng = np.random.default_rng(seed)
    if len(X) > sample_size:
        idx = rng.choice(len(X), size=sample_size, replace=False)
        idx.sort()
    else:
        idx = np.arange(len(X))
    sample = X.iloc[idx]

    try:
        explainer = shap.TreeExplainer(estimator)
        values = explainer.shap_values(sample)
        base_value = float(np.ravel(explainer.expected_value)[0])
    except Exception as exc:
        log.warning("TreeExplainer unavailable (%s); using sampled KernelExplainer", exc)
        background = shap.utils.sample(X, min(100, len(X)), random_state=seed)
        predict = model.predict if hasattr(model, "predict") else estimator.predict
        explainer = shap.KernelExplainer(
            lambda data: predict(pd.DataFrame(data, columns=columns)), background
        )
        small = sample.head(min(200, len(sample)))
        values = np.asarray(explainer.shap_values(small, nsamples=100))
        sample = small
        base_value = float(np.ravel(explainer.expected_value)[0])

    values = np.asarray(values)
    if values.ndim == 3:  # (n, f, outputs)
        values = values[:, :, 0]

    report = ShapReport(
        global_importance=_mean_abs_importance(values, columns),
        values=values,
        sample=sample,
        base_value=base_value,
    )

    if stress_mask is not None:
        mask = np.asarray(stress_mask, dtype=bool)[idx][: len(sample)]
        if mask.any():
            report.stress_importance = _mean_abs_importance(values[mask], columns)
            log.info(
                "stress-period SHAP computed on %s of %s sampled rows",
                int(mask.sum()),
                len(sample),
            )

    if figure_dir is not None:
        report.figures = _save_shap_figures(values, sample, Path(figure_dir))

    log.info(
        "top SHAP drivers: %s",
        ", ".join(report.global_importance["feature"].head(5).tolist()),
    )
    return report


def _save_shap_figures(values: np.ndarray, sample: pd.DataFrame, figure_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    figure_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for name, kind in (("shap_beeswarm", "dot"), ("shap_importance_bar", "bar")):
        try:
            plt.figure(figsize=(9, 7))
            shap.summary_plot(values, sample, plot_type=kind, show=False, max_display=20)
            path = figure_dir / f"{name}.png"
            plt.tight_layout()
            plt.savefig(path, dpi=140)
            plt.close("all")
            written.append(path)
        except Exception as exc:  # pragma: no cover - plotting is best-effort
            log.warning("could not render %s: %s", name, exc)
            plt.close("all")
    return written
