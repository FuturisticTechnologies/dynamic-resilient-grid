"""Typed configuration loaded from ``configs/config.yaml`` + environment.

Environment variables (``DRG_*``, loaded from ``.env`` when present) override
YAML values, which lets the same code run locally, in CI and on Azure
Container Apps without edits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "config.yaml"


def _deep_update(base: dict, other: dict) -> dict:
    for key, value in other.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


@dataclass
class Paths:
    root: Path
    data_dir: Path
    raw_dir: Path
    interim_dir: Path
    processed_dir: Path
    external_dir: Path
    artifact_dir: Path
    model_dir: Path
    figure_dir: Path
    report_dir: Path

    # canonical dataset locations -------------------------------------------
    @property
    def neighbourhood_demand(self) -> Path:
        return self.processed_dir / "neighbourhood_demand.parquet"

    @property
    def feature_table(self) -> Path:
        return self.processed_dir / "feature_table.parquet"

    @property
    def weather(self) -> Path:
        return self.external_dir / "weather_hourly.parquet"

    @property
    def carbon(self) -> Path:
        return self.external_dir / "carbon_intensity.parquet"

    @property
    def forecast_output(self) -> Path:
        return self.report_dir / "forecast_test.parquet"

    @property
    def scenario_output(self) -> Path:
        return self.report_dir / "scenario_results.parquet"

    @property
    def sensitivity_output(self) -> Path:
        return self.report_dir / "sensitivity_grid.parquet"

    @property
    def metrics_output(self) -> Path:
        return self.report_dir / "model_metrics.json"

    @property
    def stress_output(self) -> Path:
        return self.report_dir / "stress_events.parquet"

    def make_all(self) -> None:
        for p in (
            self.data_dir,
            self.raw_dir,
            self.interim_dir,
            self.processed_dir,
            self.external_dir,
            self.artifact_dir,
            self.model_dir,
            self.figure_dir,
            self.report_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    raw: dict[str, Any]
    paths: Paths

    # ------------------------------------------------------------------ misc
    @property
    def seed(self) -> int:
        return int(self.raw["project"]["random_seed"])

    @property
    def timezone(self) -> str:
        return self.raw["project"]["timezone"]

    # -------------------------------------------------------------- sections
    @property
    def data(self) -> dict[str, Any]:
        return self.raw["data"]

    @property
    def external(self) -> dict[str, Any]:
        return self.raw["external"]

    @property
    def features(self) -> dict[str, Any]:
        return self.raw["features"]

    @property
    def models(self) -> dict[str, Any]:
        return self.raw["models"]

    @property
    def stress(self) -> dict[str, Any]:
        return self.raw["stress"]

    @property
    def electrification(self) -> dict[str, Any]:
        return self.raw["electrification"]

    @property
    def streaming(self) -> dict[str, Any]:
        return self.raw["streaming"]

    @property
    def api(self) -> dict[str, Any]:
        return self.raw["api"]

    # ------------------------------------------------------------- secrets
    @property
    def openweather_key(self) -> str:
        return os.getenv("DRG_OPENWEATHER_API_KEY", "").strip()

    @property
    def carbon_base_url(self) -> str:
        return os.getenv("DRG_CARBON_INTENSITY_BASE_URL", "https://api.carbonintensity.org.uk").rstrip("/")

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Config:
    """Load YAML config, apply ``.env`` + environment + explicit overrides."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    cfg_path = Path(path or os.getenv("DRG_CONFIG", DEFAULT_CONFIG))
    with open(cfg_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    # --- environment overrides ---------------------------------------------
    env_map = {
        "DRG_DATA_DIR": ("paths", "data_dir"),
        "DRG_ARTIFACT_DIR": ("paths", "artifact_dir"),
        "DRG_LATITUDE": ("external", "latitude"),
        "DRG_LONGITUDE": ("external", "longitude"),
        "DRG_REGION_ID": ("external", "region_id"),
    }
    for env_key, (section, key) in env_map.items():
        val = os.getenv(env_key)
        if val:
            current = raw[section].get(key)
            if isinstance(current, float):
                raw[section][key] = float(val)
            elif isinstance(current, int) and not isinstance(current, bool):
                raw[section][key] = int(val)
            else:
                raw[section][key] = val

    if overrides:
        _deep_update(raw, overrides)

    root = PROJECT_ROOT
    p = raw["paths"]

    def _abs(key: str, fallback: str) -> Path:
        value = Path(p.get(key, fallback))
        return value if value.is_absolute() else root / value

    data_dir = _abs("data_dir", "data")
    artifact_dir = _abs("artifact_dir", "artifacts")
    paths = Paths(
        root=root,
        data_dir=data_dir,
        raw_dir=_abs("raw_dir", "data/raw"),
        interim_dir=_abs("interim_dir", "data/interim"),
        processed_dir=_abs("processed_dir", "data/processed"),
        external_dir=_abs("external_dir", "data/external"),
        artifact_dir=artifact_dir,
        model_dir=_abs("model_dir", "artifacts/models"),
        figure_dir=_abs("figure_dir", "artifacts/figures"),
        report_dir=_abs("report_dir", "artifacts/reports"),
    )
    paths.make_all()
    return Config(raw=raw, paths=paths)


@lru_cache(maxsize=4)
def get_config(path: str | None = None) -> Config:
    """Cached accessor used by the API / dashboard / streaming layers."""
    return load_config(path)
