"""Exploratory data analysis (proposal section 7.2).

Produces the load-curve, seasonality and peak-pattern evidence base, writing
publication-quality PNGs to ``artifacts/figures`` and a machine-readable
summary to ``artifacts/reports/eda_summary.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from drg.utils.logging_utils import get_logger  # noqa: E402

log = get_logger(__name__)

_SEASON_ORDER = ["winter", "spring", "summer", "autumn"]


def _season(month: pd.Series) -> pd.Series:
    return pd.Series(
        np.select(
            [month.isin([12, 1, 2]), month.isin([3, 4, 5]), month.isin([6, 7, 8])],
            ["winter", "spring", "summer"],
            default="autumn",
        ),
        index=month.index,
    )


def daily_load_curve(df: pd.DataFrame, value_col: str = "demand_kwh") -> pd.DataFrame:
    d = df.copy()
    d["period_of_day"] = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    d["day_type"] = np.where(d["timestamp"].dt.dayofweek >= 5, "weekend", "weekday")
    return (
        d.groupby(["neighbourhood_id", "day_type", "period_of_day"], observed=True)[value_col]
        .agg(["mean", "median", lambda s: np.percentile(s, 95)])
        .rename(columns={"<lambda_0>": "p95"})
        .reset_index()
    )


def seasonal_profile(df: pd.DataFrame, value_col: str = "demand_kwh") -> pd.DataFrame:
    d = df.copy()
    d["season"] = _season(d["timestamp"].dt.month)
    d["period_of_day"] = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    return d.groupby(["season", "period_of_day"], observed=True)[value_col].mean().reset_index()


def winter_amplification(df: pd.DataFrame, value_col: str = "demand_kwh") -> dict[str, Any]:
    d = df.copy()
    d["season"] = _season(d["timestamp"].dt.month)
    by_season = d.groupby("season", observed=True)[value_col].agg(["mean", "max"])
    summer_mean = float(by_season.loc["summer", "mean"]) if "summer" in by_season.index else np.nan
    winter_mean = float(by_season.loc["winter", "mean"]) if "winter" in by_season.index else np.nan
    return {
        "winter_mean_kwh": winter_mean,
        "summer_mean_kwh": summer_mean,
        "winter_uplift_pct": (
            float(100.0 * (winter_mean / summer_mean - 1.0)) if summer_mean else float("nan")
        ),
        "winter_peak_kwh": float(by_season.loc["winter", "max"]) if "winter" in by_season.index else np.nan,
        "summer_peak_kwh": float(by_season.loc["summer", "max"]) if "summer" in by_season.index else np.nan,
    }


def peak_pattern(df: pd.DataFrame, value_col: str = "demand_kwh", top_n: int = 50) -> pd.DataFrame:
    d = df.copy()
    d["period_of_day"] = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    top = d.sort_values(value_col, ascending=False).groupby("neighbourhood_id", observed=True).head(top_n)
    return (
        top.groupby(["neighbourhood_id", "period_of_day"], observed=True)
        .size()
        .reset_index(name="count_in_top_peaks")
    )


def run_eda(
    df: pd.DataFrame,
    figure_dir: str | Path,
    report_dir: str | Path,
    value_col: str = "demand_kwh",
) -> dict[str, Any]:
    """Generate every EDA figure and return the numeric summary."""
    figure_dir, report_dir = Path(figure_dir), Path(report_dir)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    curves = daily_load_curve(df, value_col)
    seasons = seasonal_profile(df, value_col)
    peaks = peak_pattern(df, value_col)

    # --- figure 1: weekday vs weekend load curve ---------------------------
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for day_type, style in (("weekday", "-"), ("weekend", "--")):
        sub = curves[curves["day_type"] == day_type].groupby("period_of_day")["mean"].mean()
        ax.plot(sub.index / 2.0, sub.to_numpy(), style, linewidth=2, label=day_type)
    ax.set_xlabel("Hour of day")
    ax.set_ylabel(f"Mean {value_col} (kWh per half hour)")
    ax.set_title("Neighbourhood load curve: weekday vs weekend")
    ax.axvspan(17, 22, alpha=0.12, color="tab:red", label="evening peak window")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(figure_dir / "eda_load_curve.png", dpi=140)
    plt.close(fig)

    # --- figure 2: seasonal profiles ---------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for season in _SEASON_ORDER:
        sub = seasons[seasons["season"] == season]
        if len(sub):
            ax.plot(sub["period_of_day"] / 2.0, sub[value_col], linewidth=2, label=season)
    ax.set_xlabel("Hour of day")
    ax.set_ylabel(f"Mean {value_col} (kWh per half hour)")
    ax.set_title("Seasonal load curves")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(figure_dir / "eda_seasonal_profile.png", dpi=140)
    plt.close(fig)

    # --- figure 3: demand distribution + stress threshold ------------------
    fig, ax = plt.subplots(figsize=(10, 5))
    values = df[value_col].dropna()
    ax.hist(values, bins=80, color="tab:blue", alpha=0.75)
    for pct, colour in ((95, "tab:red"), (99, "darkred")):
        ax.axvline(
            np.percentile(values, pct),
            color=colour,
            linestyle="--",
            label=f"P{pct} = {np.percentile(values, pct):.1f} kWh",
        )
    ax.set_xlabel(f"{value_col} (kWh per half hour)")
    ax.set_ylabel("Frequency")
    ax.set_title("Demand distribution and statistical stress thresholds")
    ax.legend()
    fig.tight_layout()
    fig.savefig(figure_dir / "eda_demand_distribution.png", dpi=140)
    plt.close(fig)

    # --- figure 4: monthly demand heat map (period x month) ----------------
    d = df.copy()
    d["period_of_day"] = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    d["month"] = d["timestamp"].dt.month
    pivot = d.pivot_table(index="period_of_day", columns="month", values=value_col, aggfunc="mean")
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(pivot.to_numpy(), aspect="auto", origin="lower", cmap="magma")
    ax.set_yticks(range(0, 48, 4))
    ax.set_yticklabels([f"{h:02d}:00" for h in range(0, 24, 2)])
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_xlabel("Month")
    ax.set_ylabel("Time of day")
    ax.set_title("Mean demand by month and half-hour")
    fig.colorbar(im, ax=ax, label="kWh per half hour")
    fig.tight_layout()
    fig.savefig(figure_dir / "eda_month_hour_heatmap.png", dpi=140)
    plt.close(fig)

    # --- figure 5: temperature response ------------------------------------
    if "temperature_c" in df.columns and df["temperature_c"].notna().any():
        d2 = df.dropna(subset=["temperature_c"]).copy()
        d2["temp_bin"] = pd.cut(d2["temperature_c"], bins=np.arange(-6, 34, 2))
        resp = d2.groupby("temp_bin", observed=True)[value_col].mean()
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot([iv.mid for iv in resp.index], resp.to_numpy(), "o-", linewidth=2)
        ax.set_xlabel("Air temperature (deg C)")
        ax.set_ylabel(f"Mean {value_col} (kWh per half hour)")
        ax.set_title("Temperature response of neighbourhood demand")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(figure_dir / "eda_temperature_response.png", dpi=140)
        plt.close(fig)

    summary: dict[str, Any] = {
        "n_rows": int(len(df)),
        "n_neighbourhoods": int(df["neighbourhood_id"].nunique()),
        "period_start": str(df["timestamp"].min()),
        "period_end": str(df["timestamp"].max()),
        "mean_kwh": float(df[value_col].mean()),
        "median_kwh": float(df[value_col].median()),
        "peak_kwh": float(df[value_col].max()),
        "p95_kwh": float(np.percentile(df[value_col].dropna(), 95)),
        "load_factor": float(df[value_col].mean() / df[value_col].max()),
        "peak_period_of_day": int(peaks.groupby("period_of_day")["count_in_top_peaks"].sum().idxmax()),
        **winter_amplification(df, value_col),
    }
    weekday = curves[curves["day_type"] == "weekday"].groupby("period_of_day")["mean"].mean()
    weekend = curves[curves["day_type"] == "weekend"].groupby("period_of_day")["mean"].mean()
    summary["weekday_peak_kwh"] = float(weekday.max())
    summary["weekend_peak_kwh"] = float(weekend.max())
    summary["weekend_peak_shift_periods"] = int(weekend.idxmax() - weekday.idxmax())

    (report_dir / "eda_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("EDA complete: %s figures in %s", len(list(figure_dir.glob("eda_*.png"))), figure_dir)
    return summary
