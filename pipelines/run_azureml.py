"""Azure ML entry point for the full DRG pipeline.

Runs exactly the same stage functions as the local CLI, and additionally:

* logs parameters, metrics and artifacts to the workspace via MLflow;
* copies every artifact to the job output folder so it lands in the workspace
  datastore;
* registers the champion model so a managed online endpoint can serve it.

Locally it degrades gracefully: without MLflow or an Azure ML context it just
runs the pipeline and writes the artifacts.

    python pipelines/run_azureml.py --output-dir ./artifacts --register-model
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drg.config import load_config  # noqa: E402
from drg.pipeline import run_all  # noqa: E402
from drg.utils.logging_utils import get_logger, setup_logging  # noqa: E402

log = get_logger("drg.azureml")


def _mlflow():
    try:
        import mlflow

        return mlflow
    except Exception as exc:  # pragma: no cover - optional dependency
        log.warning("MLflow unavailable (%s); metrics will not be tracked", exc)
        return None


def _log_report(mlflow, report: dict) -> None:
    if mlflow is None:
        return
    champion = report["model"]["champion"]
    metrics = next((m for m in report["model"]["test_metrics"] if m["model"] == champion), {})
    for key in ("mae", "rmse", "mape", "r2", "stress_f1", "stress_precision", "stress_recall"):
        if key in metrics:
            mlflow.log_metric(f"test_{key}", float(metrics[key]))
    if report["model"].get("cv_mean_rmse") is not None:
        mlflow.log_metric("cv_mean_rmse", float(report["model"]["cv_mean_rmse"]))

    electrification = report.get("electrification", {})
    for key in (
        "worst_case_peak_amplification_pct",
        "worst_case_stress_frequency_pct",
        "worst_case_mean_event_hours",
        "ev_only_max_amplification_pct",
        "hp_only_max_amplification_pct",
    ):
        if key in electrification:
            mlflow.log_metric(key, float(electrification[key]))

    eda = report.get("eda", {})
    for key in ("peak_kwh", "p95_kwh", "load_factor", "winter_uplift_pct"):
        if key in eda:
            mlflow.log_metric(f"eda_{key}", float(eda[key]))

    mlflow.set_tags(
        {
            "champion_model": champion,
            "data_source": report["data"]["source"],
            "n_neighbourhoods": report["data"]["neighbourhoods"],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the DRG pipeline under Azure ML")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--output-dir", default=None, help="Job output folder (uri_folder mount)")
    parser.add_argument("--register-model", action="store_true", help="Register the champion model")
    parser.add_argument("--model-name", default="drg-champion")
    parser.add_argument("--no-lstm", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Skip external API calls")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)
    mlflow = _mlflow()

    if mlflow is not None:
        mlflow.log_params(
            {
                "primary_percentile": cfg.stress["primary_percentile"],
                "sensitivity_sigma": cfg.stress["sensitivity_sigma"],
                "lags": str(cfg.features["lags"]),
                "rolling_windows": str(cfg.features["rolling_windows"]),
                "test_size_days": cfg.models["test_size_days"],
                "ev_charger_kw": cfg.electrification["ev"]["charger_kw"],
                "heat_pump_rated_kw": cfg.electrification["heat_pump"]["rated_kw"],
                "monte_carlo_runs": cfg.electrification["monte_carlo_runs"],
            }
        )

    report = run_all(
        args.config,
        force=False,
        skip_lstm=args.no_lstm,
        allow_network=not args.offline,
    )
    _log_report(mlflow, report)

    # --- publish artifacts -------------------------------------------------
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for source in (cfg.paths.model_dir, cfg.paths.report_dir, cfg.paths.figure_dir):
            if source.exists():
                shutil.copytree(source, out / source.name, dirs_exist_ok=True)
        (out / "run_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log.info("artifacts published -> %s", out)

    if mlflow is not None:
        for source in (cfg.paths.report_dir, cfg.paths.figure_dir):
            if source.exists():
                mlflow.log_artifacts(str(source), artifact_path=source.name)

        if args.register_model:
            model_path = cfg.paths.model_dir / "best_model.joblib"
            if model_path.exists():
                try:
                    mlflow.log_artifact(str(model_path), artifact_path="model")
                    run_id = mlflow.active_run().info.run_id
                    mlflow.register_model(f"runs:/{run_id}/model", args.model_name)
                    log.info("registered model %s from run %s", args.model_name, run_id)
                except Exception as exc:  # pragma: no cover
                    log.warning("model registration failed: %s", exc)

    champion = report["model"]["champion"]
    metrics = next((m for m in report["model"]["test_metrics"] if m["model"] == champion), {})
    log.info(
        "DONE champion=%s MAE=%.4f RMSE=%.4f R2=%.4f | worst-case peak +%.1f%%",
        champion,
        metrics.get("mae", float("nan")),
        metrics.get("rmse", float("nan")),
        metrics.get("r2", float("nan")),
        report.get("electrification", {}).get("worst_case_peak_amplification_pct", float("nan")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
