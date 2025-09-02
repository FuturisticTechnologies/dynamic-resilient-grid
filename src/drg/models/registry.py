"""Model persistence.

A trained forecaster is stored as a :class:`ModelBundle` -- the estimator plus
everything needed to reproduce its inputs (feature column order, target name,
training window, metrics). Bundles are joblib artifacts, so the same file is
consumable by the local dashboard, the FastAPI service and an Azure ML managed
online endpoint.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import joblib

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


@dataclass
class ModelBundle:
    name: str
    estimator: Any
    feature_columns: list[str]
    target: str = "demand_kwh"
    kind: str = "sklearn"  # sklearn | xgboost | torch
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def predict(self, X):  # noqa: N803 - sklearn convention
        return self.estimator.predict(X)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("estimator")
        return d


def save_model(bundle: ModelBundle, model_dir: str | Path, filename: str | None = None) -> Path:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / (filename or f"{bundle.name}.joblib")
    joblib.dump(bundle, path)
    sidecar = path.with_suffix(".json")
    sidecar.write_text(json.dumps(bundle.to_dict(), indent=2, default=str), encoding="utf-8")
    log.info("saved model bundle -> %s", path)
    return path


def load_model(path: str | Path) -> ModelBundle:
    bundle = joblib.load(Path(path))
    if not isinstance(bundle, ModelBundle):
        raise TypeError(f"{path} does not contain a DRG ModelBundle")
    return bundle


def load_best(model_dir: str | Path, prefer: str = "best_model.joblib") -> ModelBundle:
    """Load the champion model, falling back to any bundle in the directory."""
    model_dir = Path(model_dir)
    candidate = model_dir / prefer
    if candidate.exists():
        return load_model(candidate)
    bundles = sorted(model_dir.glob("*.joblib"))
    if not bundles:
        raise FileNotFoundError(f"No trained model found in {model_dir}. Run: python -m drg.cli train")
    return load_model(bundles[0])
