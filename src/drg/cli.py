"""DRG command line interface.

python -m drg.cli run-all              # full pipeline, end to end
python -m drg.cli ingest --force       # rebuild the demand + context data
python -m drg.cli eda
python -m drg.cli features
python -m drg.cli train --no-lstm
python -m drg.cli stress
python -m drg.cli scenarios
python -m drg.cli explain
python -m drg.cli replay --ticks 96
python -m drg.cli context              # live weather + carbon intensity
python -m drg.cli serve                # FastAPI decision-support service
python -m drg.cli dashboard            # Streamlit dashboard
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from drg import __version__
from drg.config import load_config
from drg.utils.logging_utils import setup_logging

app = typer.Typer(add_completion=False, help="Dynamic Resilient Grid (DRG) toolkit")
console = Console()

ConfigOpt = typer.Option(None, "--config", "-c", help="Path to config.yaml")


def _cfg(config: Optional[str]):
    setup_logging()
    return load_config(config)


def _print_df(df, title: str, max_rows: int = 25) -> None:
    table = Table(title=title, header_style="bold cyan")
    for col in df.columns:
        table.add_column(str(col), overflow="fold")
    for _, row in df.head(max_rows).iterrows():
        table.add_row(*[f"{v:,.4f}" if isinstance(v, float) else str(v) for v in row.to_numpy()])
    console.print(table)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, version: bool = typer.Option(False, "--version")) -> None:
    if version:
        console.print(f"DRG {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command()
def ingest(
    config: Optional[str] = ConfigOpt,
    force: bool = typer.Option(False, help="Rebuild even if cached"),
    offline: bool = typer.Option(False, help="Do not call external APIs"),
) -> None:
    """Load smart-meter data and the weather / carbon context series."""
    from drg.pipeline import stage_ingest

    cfg = _cfg(config)
    df = stage_ingest(cfg, force=force, allow_network=not offline)
    console.print(f"[green]OK[/] {len(df):,} rows -> {cfg.paths.neighbourhood_demand}")


@app.command()
def eda(config: Optional[str] = ConfigOpt) -> None:
    """Exploratory data analysis: load curves, seasonality, peak patterns."""
    from drg.pipeline import stage_eda

    cfg = _cfg(config)
    summary = stage_eda(cfg)
    console.print_json(json.dumps(summary, default=str))


@app.command()
def features(
    config: Optional[str] = ConfigOpt,
    force: bool = typer.Option(False, help="Rebuild even if cached"),
) -> None:
    """Build the engineered feature table."""
    from drg.pipeline import stage_features

    cfg = _cfg(config)
    df = stage_features(cfg, force=force)
    console.print(f"[green]OK[/] {len(df):,} rows x {df.shape[1]} columns -> {cfg.paths.feature_table}")


@app.command()
def train(
    config: Optional[str] = ConfigOpt,
    lstm: bool = typer.Option(True, "--lstm/--no-lstm", help="Include the deep model"),
) -> None:
    """Train and evaluate the forecasting model ladder."""
    from drg.pipeline import stage_train

    cfg = _cfg(config)
    result = stage_train(cfg, train_lstm=lstm)
    cols = [c for c in ["model", "mae", "rmse", "mape", "r2", "stress_f1"] if c in result.metrics]
    _print_df(result.metrics[cols], "Test-window performance (sorted by RMSE)")
    if len(result.cv_metrics):
        _print_df(
            result.cv_metrics[["fold", "mae", "rmse", "r2"]],
            "Rolling-origin cross-validation (champion)",
        )
    console.print(f"[green]champion:[/] {result.best.name} -> {result.model_path}")


@app.command()
def stress(config: Optional[str] = ConfigOpt) -> None:
    """Detect statistical stress periods and summarise them."""
    from drg.pipeline import stage_stress

    cfg = _cfg(config)
    art = stage_stress(cfg)
    _print_df(
        art.summary[
            [
                "neighbourhood_id",
                "threshold_kwh",
                "stress_frequency_pct",
                "stress_hours_per_week",
                "n_events",
                "mean_event_hours",
                "peak_to_threshold_ratio",
            ]
        ],
        "Historical stress profile",
    )


@app.command()
def scenarios(
    config: Optional[str] = ConfigOpt,
) -> None:
    """Run the EV / heat-pump adoption grid and sensitivity analysis."""
    from drg.pipeline import stage_scenarios

    cfg = _cfg(config)
    grid, headline, _ = stage_scenarios(cfg)
    _print_df(
        grid[
            [
                "scenario",
                "ev_adoption",
                "hp_adoption",
                "peak_amplification_pct",
                "stress_frequency_pct",
                "mean_event_hours",
                "energy_growth_pct",
            ]
        ],
        "Electrification sensitivity grid",
        max_rows=40,
    )
    console.print_json(json.dumps(headline, default=str))


@app.command()
def explain(config: Optional[str] = ConfigOpt, sample: int = 4000) -> None:
    """SHAP explainability for the champion model."""
    from drg.pipeline import stage_explain

    cfg = _cfg(config)
    out = stage_explain(cfg, sample_size=sample)
    console.print_json(json.dumps(out["top_global_drivers"][:12], default=str))


@app.command("run-all")
def run_all_cmd(
    config: Optional[str] = ConfigOpt,
    force: bool = typer.Option(False, help="Ignore caches"),
    offline: bool = typer.Option(False, help="Do not call external APIs"),
    lstm: bool = typer.Option(True, "--lstm/--no-lstm"),
    explain_stage: bool = typer.Option(True, "--explain/--no-explain"),
) -> None:
    """Run every stage: ingest -> EDA -> features -> train -> stress -> scenarios -> SHAP."""
    from drg.pipeline import run_all

    report = run_all(
        config,
        force=force,
        skip_explain=not explain_stage,
        skip_lstm=not lstm,
        allow_network=not offline,
    )
    console.print(f"[green]pipeline complete in {report['duration_s']:.1f}s[/]")
    console.print(f"report -> {load_config(config).paths.report_dir / 'run_report.json'}")


@app.command()
def replay(
    config: Optional[str] = ConfigOpt,
    ticks: int = typer.Option(96, help="Number of half-hourly steps to replay"),
    neighbourhood: Optional[str] = typer.Option(None),
    realtime: bool = typer.Option(False, help="Throttle to the configured speed factor"),
) -> None:
    """Replay historical demand as a simulated live feed with stress alerts."""
    import pandas as pd

    from drg.models.registry import load_best
    from drg.streaming.replay import StreamingReplayEngine
    from drg.stress.detection import compute_thresholds

    cfg = _cfg(config)
    demand = pd.read_parquet(cfg.paths.neighbourhood_demand)
    thresholds = compute_thresholds(
        demand,
        percentile=float(cfg.stress.get("primary_percentile", 95)),
        sigma=float(cfg.stress.get("sensitivity_sigma", 2.0)),
    )
    engine = StreamingReplayEngine(
        demand,
        load_best(cfg.paths.model_dir),
        thresholds,
        cfg,
        neighbourhood_id=neighbourhood,
        start_index=max(
            len(demand[demand["neighbourhood_id"] == (neighbourhood or demand["neighbourhood_id"].iloc[0])])
            - ticks
            - 1,
            int(cfg.streaming.get("window_periods", 336)) + 1,
        ),
    )
    frame = engine.run(n=ticks, realtime=realtime)
    frame["alert"] = frame.apply(
        lambda r: "STRESS" if r["is_stress"] else ("PRE-EMPTIVE" if r["forecast_is_stress"] else "ok"),
        axis=1,
    )
    _print_df(
        frame[["timestamp", "actual_kwh", "forecast_next_kwh", "threshold_kwh", "severity", "alert"]],
        f"Streaming replay ({engine.neighbourhood_id})",
        max_rows=ticks,
    )
    out = cfg.paths.report_dir / "replay_log.parquet"
    frame.to_parquet(out, index=False)
    console.print(f"[green]OK[/] alert log -> {out}")


@app.command()
def context(config: Optional[str] = ConfigOpt) -> None:
    """Fetch the live weather and carbon-intensity snapshot."""
    from drg.data.external_apis import fetch_context_snapshot

    cfg = _cfg(config)
    snapshot = fetch_context_snapshot(
        float(cfg.external["latitude"]),
        float(cfg.external["longitude"]),
        api_key=cfg.openweather_key,
        carbon_base_url=cfg.carbon_base_url,
        region_id=int(cfg.external.get("region_id", 13)),
        cache_dir=cfg.paths.external_dir,
    )
    console.print_json(json.dumps(snapshot, default=str))


@app.command()
def serve(
    config: Optional[str] = ConfigOpt,
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False),
) -> None:
    """Start the FastAPI decision-support service."""
    import uvicorn

    _cfg(config)
    uvicorn.run("drg.api.main:app", host=host, port=port, reload=reload)


@app.command()
def dashboard(
    config: Optional[str] = ConfigOpt,
    port: int = typer.Option(8501),
) -> None:
    """Launch the Streamlit dashboard."""
    import subprocess
    import sys

    app_path = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.port",
            str(port),
            "--server.address",
            "0.0.0.0",
        ],
        check=False,
    )


if __name__ == "__main__":
    app()
