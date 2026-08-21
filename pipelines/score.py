"""Scoring script for the Azure ML managed online endpoint.

Request body::

    {
      "records": [
        {"lag_1": 21.4, "lag_48": 20.9, "period_of_day": 37, "is_weekend": 0, ...}
      ],
      "threshold_kwh": 33.1
    }

Response::

    {
      "forecast_kwh": [22.7],
      "is_stress": [false],
      "model": "xgboost",
      "n_features": 47
    }

Any feature the caller omits is filled with NaN, which the gradient-boosted
champion handles natively; the response reports which ones were missing so a
caller can spot a degraded request.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("drg.score")

_bundle = None


def init() -> None:
    """Called once when the deployment container starts."""
    global _bundle
    from drg.models.registry import load_model

    root = Path(os.getenv("AZUREML_MODEL_DIR", "artifacts/models"))
    candidates = sorted(root.rglob("best_model.joblib")) or sorted(root.rglob("*.joblib"))
    if not candidates:
        raise FileNotFoundError(f"No model artifact found under {root}")
    _bundle = load_model(candidates[0])
    log.info("loaded model %s with %s features", _bundle.name, len(_bundle.feature_columns))


def run(raw_data: str | bytes | dict) -> dict[str, Any]:
    """Score one batch of feature records."""
    if _bundle is None:  # pragma: no cover - endpoint always calls init() first
        init()

    payload = raw_data if isinstance(raw_data, dict) else json.loads(raw_data)
    records = payload.get("records") or payload.get("data") or []
    if not records:
        return {"error": "no records supplied", "expected_features": _bundle.feature_columns}

    frame = pd.DataFrame(records)
    missing = [c for c in _bundle.feature_columns if c not in frame.columns]
    design = frame.reindex(columns=_bundle.feature_columns)

    preds = np.clip(np.asarray(_bundle.predict(design), dtype=float), 0.0, None)

    response: dict[str, Any] = {
        "forecast_kwh": [round(float(p), 4) for p in preds],
        "model": _bundle.name,
        "n_features": len(_bundle.feature_columns),
        "missing_features": missing,
    }

    threshold = payload.get("threshold_kwh") or _bundle.metadata.get("stress_threshold")
    if threshold:
        threshold = float(threshold)
        response["threshold_kwh"] = threshold
        response["is_stress"] = [bool(p >= threshold) for p in preds]
        response["headroom_kwh"] = [round(float(threshold - p), 4) for p in preds]
    return response
