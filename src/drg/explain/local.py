"""Per-forecast explanations for the replay page (DRG-117).

The global SHAP report explains the model on average. An operator watching a
replay needs something smaller and immediate: *why is this half-hour's
forecast what it is?* :func:`local_contributions` returns the few features
that move the current one-step-ahead forecast most, cheaply enough to run on
every replay tick:

* XGBoost -- exact TreeSHAP contributions from the booster
  (``pred_contribs``);
* linear / ridge pipelines -- coefficient x standardised feature value, which
  is the exact additive decomposition of a linear model;
* seasonal naive -- the whole forecast is ``lag_48``.

Anything else yields an empty table rather than an error, so the replay keeps
running with an older or unusual champion model.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

COLUMNS = ["feature", "value", "contribution"]


def _xgboost_contributions(estimator: Any, row: pd.DataFrame) -> pd.Series | None:
    import xgboost as xgb

    model = getattr(estimator, "model", estimator)
    if not hasattr(model, "get_booster"):
        return None
    cols = list(getattr(estimator, "feature_columns", None) or row.columns)
    matrix = xgb.DMatrix(row[cols].astype(float), feature_names=cols)
    contribs = model.get_booster().predict(matrix, pred_contribs=True)[0]
    return pd.Series(contribs[:-1], index=cols)  # last column is the bias


def _linear_contributions(estimator: Any, row: pd.DataFrame) -> pd.Series | None:
    pipeline = getattr(estimator, "pipeline", None)
    if pipeline is None or not hasattr(pipeline, "named_steps"):
        return None
    model = pipeline.named_steps.get("model")
    coefs = getattr(model, "coef_", None)
    if coefs is None:
        return None
    cols = list(getattr(estimator, "feature_columns", None) or row.columns)
    transformed = pipeline[:-1].transform(row[cols])
    return pd.Series(np.ravel(transformed) * np.ravel(coefs), index=cols)


def local_contributions(estimator: Any, row: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Top ``top_n`` feature contributions to the forecast for one design row.

    ``estimator`` is a model or a :class:`~drg.models.registry.ModelBundle`;
    ``row`` is the single-row design matrix the forecast was made from.
    Returns ``feature, value, contribution`` (kWh), largest magnitude first.
    """
    estimator = getattr(estimator, "estimator", estimator)
    if row.empty:
        return pd.DataFrame(columns=COLUMNS)
    row = row.iloc[[0]]

    contribs: pd.Series | None = None
    try:
        if getattr(estimator, "name", "") == "seasonal_naive":
            col = getattr(estimator, "lag_column", "lag_48")
            contribs = pd.Series({col: float(row[col].iloc[0])})
        else:
            contribs = _xgboost_contributions(estimator, row)
            if contribs is None:
                contribs = _linear_contributions(estimator, row)
    except Exception as exc:  # pragma: no cover - never break the replay
        log.debug("local explanation unavailable: %s", exc)
        contribs = None

    if contribs is None or contribs.empty:
        return pd.DataFrame(columns=COLUMNS)

    top = contribs.reindex(contribs.abs().sort_values(ascending=False).index).head(top_n)
    values = row.reindex(columns=top.index).iloc[0]
    return pd.DataFrame(
        {
            "feature": top.index,
            "value": values.to_numpy(dtype=float),
            "contribution": top.to_numpy(dtype=float),
        }
    ).reset_index(drop=True)
