"""End-to-end DRG pipeline stages.

Each stage is idempotent and cached on disk, so stages can be re-run
individually (``python -m drg.cli features``) or chained (``... run-all``).
The same functions are called by the Azure ML training job and by the local
CLI, which keeps cloud and laptop runs identical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from drg.analysis.eda import run_eda
from drg.analysis.sensitivity import (
    elasticity_curve,
    run_sensitivity_grid,
    summarise_amplification,
)
from drg.config import Config, load_config
from drg.data.external_apis import build_carbon_intensity_series, build_temperature_series
from drg.data.lcl_loader import build_neighbourhood_demand
from drg.features.engineering import build_feature_table
from drg.models.registry import ModelBundle, load_best
from drg.models.train import TrainingResult, train_models
from drg.simulation.electrification import EVConfig, HeatPumpConfig, apply_scenario
from drg.stress.detection import (
    StressThresholds,
    compute_thresholds,
    detect_stress,
    diurnal_stress_profile,
    seasonal_stress_profile,
    stress_events,
    stress_summary,
)
from drg.utils.io import write_table
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


# ===========================================================================
# stage 1 -- ingestion + context
# ===========================================================================
def stage_ingest(cfg: Config, force: bool = False, allow_network: bool = True) -> pd.DataFrame:
    """Build the cleaned neighbourhood demand table and its context series."""
    demand = build_neighbourhood_demand(cfg, force=force)
    index = pd.DatetimeIndex(sorted(demand["timestamp"].unique()))

    if cfg.external.get("use_weather", True):
        weather_path = cfg.paths.weather
        if weather_path.exists() and not force:
            weather = pd.read_parquet(weather_path)
        else:
            weather = build_temperature_series(
                index,
                latitude=float(cfg.external["latitude"]),
                longitude=float(cfg.external["longitude"]),
                api_key=cfg.openweather_key,
                cache_dir=cfg.paths.external_dir,
                allow_network=allow_network,
                seed=cfg.seed,
            )
            write_table(weather, weather_path)
    else:
        weather = pd.DataFrame()

    if cfg.external.get("use_carbon_intensity", True):
        carbon_path = cfg.paths.carbon
        if carbon_path.exists() and not force:
            carbon = pd.read_parquet(carbon_path)
        else:
            carbon = build_carbon_intensity_series(
                index,
                base_url=cfg.carbon_base_url,
                region_id=int(cfg.external.get("region_id", 13)),
                cache_dir=cfg.paths.external_dir,
                allow_network=allow_network,
            )
            write_table(carbon, carbon_path)
    else:
        carbon = pd.DataFrame()

    log.info(
        "ingest complete: %s demand rows | %s weather rows | %s carbon rows",
        f"{len(demand):,}",
        f"{len(weather):,}",
        f"{len(carbon):,}",
    )
    return demand


def load_context_tables(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    weather = pd.read_parquet(cfg.paths.weather) if cfg.paths.weather.exists() else pd.DataFrame()
    carbon = pd.read_parquet(cfg.paths.carbon) if cfg.paths.carbon.exists() else pd.DataFrame()
    return weather, carbon


# ===========================================================================
# stage 2 -- EDA
# ===========================================================================
def stage_eda(cfg: Config, demand: pd.DataFrame | None = None) -> dict[str, Any]:
    demand = demand if demand is not None else build_neighbourhood_demand(cfg)
    return run_eda(demand, cfg.paths.figure_dir, cfg.paths.report_dir)


# ===========================================================================
# stage 3 -- features
# ===========================================================================
def stage_features(cfg: Config, force: bool = False) -> pd.DataFrame:
    target = cfg.paths.feature_table
    if target.exists() and not force:
        log.info("using cached %s", target.name)
        return pd.read_parquet(target)

    demand = build_neighbourhood_demand(cfg)
    weather, carbon = load_context_tables(cfg)
    features = build_feature_table(demand, cfg, weather=weather, carbon=carbon)
    write_table(features, target)
    return features


# ===========================================================================
# stage 4 -- training
# ===========================================================================
def stage_train(cfg: Config, features: pd.DataFrame | None = None, **kwargs: Any) -> TrainingResult:
    features = features if features is not None else stage_features(cfg)
    result = train_models(features, cfg, **kwargs)
    log.info("\n%s", result.metrics.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    return result


# ===========================================================================
# stage 5 -- stress detection
# ===========================================================================
@dataclass
class StressArtifacts:
    thresholds: dict[str, StressThresholds]
    flagged: pd.DataFrame
    events: pd.DataFrame
    summary: pd.DataFrame
    seasonal: pd.DataFrame
    diurnal: pd.DataFrame


def stage_stress(cfg: Config, demand: pd.DataFrame | None = None) -> StressArtifacts:
    demand = demand if demand is not None else build_neighbourhood_demand(cfg)
    thresholds = compute_thresholds(
        demand,
        percentile=float(cfg.stress.get("primary_percentile", 95)),
        sigma=float(cfg.stress.get("sensitivity_sigma", 2.0)),
    )
    flagged = detect_stress(demand, thresholds)
    events = stress_events(flagged, min_periods=int(cfg.stress.get("min_event_periods", 2)))
    summary = stress_summary(flagged, events)
    seasonal = seasonal_stress_profile(flagged)
    diurnal = diurnal_stress_profile(flagged)

    write_table(events, cfg.paths.stress_output)
    write_table(summary, cfg.paths.report_dir / "stress_summary.parquet")
    write_table(seasonal, cfg.paths.report_dir / "stress_seasonal.parquet")
    write_table(diurnal, cfg.paths.report_dir / "stress_diurnal.parquet")
    (cfg.paths.report_dir / "stress_thresholds.json").write_text(
        json.dumps({k: v.to_dict() for k, v in thresholds.items()}, indent=2),
        encoding="utf-8",
    )
    log.info(
        "stress: %s events, mean frequency %.2f%% of half-hours",
        len(events),
        summary["stress_frequency_pct"].mean(),
    )
    return StressArtifacts(thresholds, flagged, events, summary, seasonal, diurnal)


# ===========================================================================
# stage 6 -- electrification scenarios + sensitivity
# ===========================================================================
def _scenario_window(cfg: Config, demand: pd.DataFrame) -> pd.DataFrame:
    """Evaluate scenarios on the most recent full year (bounded compute)."""
    end = demand["timestamp"].max()
    start = end - pd.Timedelta(days=int(cfg.get("models.test_size_days", 60)) * 6)
    window = demand[demand["timestamp"] >= start]
    return window if len(window) else demand


def stage_scenarios(
    cfg: Config,
    demand: pd.DataFrame | None = None,
    thresholds: dict[str, StressThresholds] | None = None,
    *,
    keep_frames: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any], dict[tuple[float, float], pd.DataFrame]]:
    demand = demand if demand is not None else build_neighbourhood_demand(cfg)
    if thresholds is None:
        thresholds = compute_thresholds(
            demand,
            percentile=float(cfg.stress.get("primary_percentile", 95)),
            sigma=float(cfg.stress.get("sensitivity_sigma", 2.0)),
        )

    window = _scenario_window(cfg, demand)
    ecfg = cfg.electrification
    ev_cfg = EVConfig.from_config(ecfg["ev"])
    hp_cfg = HeatPumpConfig.from_config(ecfg["heat_pump"])

    grid, frames = run_sensitivity_grid(
        window,
        thresholds,
        ev_levels=list(ecfg["ev"]["adoption_levels"]),
        hp_levels=list(ecfg["heat_pump"]["adoption_levels"]),
        ev_config=ev_cfg,
        hp_config=hp_cfg,
        min_event_periods=int(cfg.stress.get("min_event_periods", 2)),
        seed=cfg.seed,
        runs=1,
        keep_frames=keep_frames,
    )
    write_table(grid, cfg.paths.sensitivity_output)

    curves = pd.concat(
        [
            elasticity_curve(grid, hold="hp_adoption").assign(varying="ev"),
            elasticity_curve(grid, hold="ev_adoption").assign(varying="heat_pump"),
        ],
        ignore_index=True,
    )
    write_table(curves, cfg.paths.report_dir / "elasticity_curves.parquet")

    headline = summarise_amplification(grid)
    (cfg.paths.report_dir / "sensitivity_summary.json").write_text(
        json.dumps(headline, indent=2, default=str), encoding="utf-8"
    )

    # a single high-resolution headline scenario with Monte-Carlo uncertainty
    runs = int(ecfg.get("monte_carlo_runs", 30))
    headline_ev = max(ecfg["ev"]["adoption_levels"])
    headline_hp = max(ecfg["heat_pump"]["adoption_levels"])
    mc = apply_scenario(
        window,
        headline_ev,
        headline_hp,
        ev_config=ev_cfg,
        hp_config=hp_cfg,
        seed=cfg.seed,
        runs=runs,
    )
    write_table(mc.frame, cfg.paths.scenario_output)
    headline["monte_carlo_scenario"] = mc.summary
    (cfg.paths.report_dir / "sensitivity_summary.json").write_text(
        json.dumps(headline, indent=2, default=str), encoding="utf-8"
    )
    log.info("scenario headline: %s", json.dumps(headline, indent=2, default=str)[:600])
    return grid, headline, frames


# ===========================================================================
# stage 7 -- explainability
# ===========================================================================
def stage_explain(
    cfg: Config,
    bundle: ModelBundle | None = None,
    features: pd.DataFrame | None = None,
    sample_size: int = 4000,
) -> dict[str, Any]:
    from drg.explain.shap_explain import explain_model

    bundle = bundle or load_best(cfg.paths.model_dir)
    features = features if features is not None else stage_features(cfg)

    test_days = int(cfg.get("models.test_size_days", 60))
    cutoff = features["timestamp"].max() - pd.Timedelta(days=test_days)
    test = features[features["timestamp"] >= cutoff]
    if test.empty:
        test = features.tail(min(len(features), sample_size))

    threshold = float(np.percentile(features["target"], cfg.stress.get("primary_percentile", 95)))
    report = explain_model(
        bundle.estimator,
        test[bundle.feature_columns],
        stress_mask=(test["target"] >= threshold).to_numpy(),
        sample_size=sample_size,
        seed=cfg.seed,
        figure_dir=cfg.paths.figure_dir,
    )
    write_table(report.global_importance, cfg.paths.report_dir / "shap_global_importance.parquet")
    if len(report.stress_importance):
        write_table(report.stress_importance, cfg.paths.report_dir / "shap_stress_importance.parquet")
    out = {
        "top_global_drivers": report.global_importance.head(15).to_dict(orient="records"),
        "top_stress_drivers": (
            report.stress_importance.head(15).to_dict(orient="records")
            if len(report.stress_importance)
            else []
        ),
        "figures": [str(p) for p in report.figures],
    }
    (cfg.paths.report_dir / "shap_summary.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    return out


# ===========================================================================
# orchestration
# ===========================================================================
def run_all(
    config_path: str | Path | None = None,
    *,
    force: bool = False,
    skip_explain: bool = False,
    skip_lstm: bool = False,
    allow_network: bool = True,
) -> dict[str, Any]:
    """Run every stage end to end and return a consolidated run report."""
    cfg = load_config(config_path)
    started = pd.Timestamp.utcnow()

    demand = stage_ingest(cfg, force=force, allow_network=allow_network)
    eda = stage_eda(cfg, demand)
    features = stage_features(cfg, force=force)
    training = stage_train(cfg, features, train_lstm=not skip_lstm)
    stress = stage_stress(cfg, demand)
    grid, headline, _ = stage_scenarios(cfg, demand, stress.thresholds)

    explain: dict[str, Any] = {}
    if not skip_explain:
        try:
            explain = stage_explain(cfg, training.best, features)
        except Exception as exc:  # pragma: no cover
            log.warning("explainability stage failed: %s", exc)

    report = {
        "run_started_utc": str(started),
        "run_finished_utc": str(pd.Timestamp.utcnow()),
        "duration_s": float((pd.Timestamp.utcnow() - started).total_seconds()),
        "data": {
            "rows": int(len(demand)),
            "neighbourhoods": int(demand["neighbourhood_id"].nunique()),
            "source": str(demand.get("source", pd.Series(["unknown"])).iloc[0]),
            "period": [str(demand["timestamp"].min()), str(demand["timestamp"].max())],
        },
        "eda": eda,
        "model": {
            "champion": training.best.name,
            "test_metrics": training.metrics.to_dict(orient="records"),
            "cv_mean_rmse": float(training.cv_metrics["rmse"].mean()) if len(training.cv_metrics) else None,
            "model_path": str(training.model_path) if training.model_path else None,
        },
        "stress": {
            "n_events": int(len(stress.events)),
            "summary": stress.summary.to_dict(orient="records"),
        },
        "electrification": headline,
        "explainability": explain,
    }
    path = cfg.paths.report_dir / "run_report.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("run report written -> %s", path)
    return report
