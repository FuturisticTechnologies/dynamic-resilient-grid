"""Scenario reporting artefacts (DRG-84).

The figures and tables that carry the electrification finding, regenerated on
every ``run-all`` and written to ``artifacts/``:

* peak amplification by scenario (EV x heat-pump adoption grid);
* the diversity gap -- combined peak versus the sum of the single-technology
  peaks;
* stress frequency and duration by scenario;
* the load-shape overlay, showing where in the day the amplification lands
  and how the evening peak grows *and widens*.

Every function takes the sensitivity grid (or scenario frames) produced by
:mod:`drg.analysis.sensitivity` and returns a tidy table; the ``plot_*``
functions draw the matching figure.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from drg.utils.logging_utils import get_logger  # noqa: E402

log = get_logger(__name__)

DPI = 140


def _pct_label(value: float) -> str:
    return f"{int(round(100 * float(value)))}%"


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


# ===========================================================================
# peak amplification
# ===========================================================================
def peak_amplification_table(grid: pd.DataFrame) -> pd.DataFrame:
    """Peak amplification (%) as an EV-adoption x heat-pump-adoption matrix."""
    table = grid.pivot_table(
        index="ev_adoption", columns="hp_adoption", values="peak_amplification_pct", aggfunc="mean"
    ).sort_index().sort_index(axis=1)
    table.index.name = "ev_adoption"
    table.columns.name = "hp_adoption"
    return table


def plot_peak_amplification(grid: pd.DataFrame, path: Path) -> Path:
    """Heatmap of peak amplification across the adoption grid."""
    table = peak_amplification_table(grid)
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(table.to_numpy(), cmap="OrRd", origin="lower", aspect="auto")
    ax.set_xticks(range(table.shape[1]), [_pct_label(c) for c in table.columns])
    ax.set_yticks(range(table.shape[0]), [_pct_label(i) for i in table.index])
    ax.set_xlabel("Heat-pump adoption")
    ax.set_ylabel("EV adoption")
    ax.set_title("Peak amplification by scenario (% above the un-electrified peak)")
    vmax = float(np.nanmax(table.to_numpy())) if table.size else 0.0
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            value = table.iat[i, j]
            if np.isfinite(value):
                colour = "white" if vmax and value > 0.6 * vmax else "black"
                ax.text(j, i, f"+{value:.0f}%", ha="center", va="center", fontsize=9, color=colour)
    fig.colorbar(im, ax=ax, label="Peak amplification (%)")
    return _save(fig, path)


# ===========================================================================
# diversity gap
# ===========================================================================
def diversity_gap_table(grid: pd.DataFrame) -> pd.DataFrame:
    """Combined peak amplification against the sum of its single-technology parts.

    One row per scenario with both technologies. ``ev_only`` / ``heat_pump_only``
    come from the grid's single-technology scenarios at the same adoption
    levels (or, when the grid carries them, from the same draws via
    ``ev_only_peak_amplification_pct`` / ``heat_pump_only_peak_amplification_pct``).
    ``diversity_gap_pp`` is how far the combined peak sits below additive.
    """
    amp = grid.set_index(["ev_adoption", "hp_adoption"])["peak_amplification_pct"]
    rows = []
    for _, row in grid[(grid["ev_adoption"] > 0) & (grid["hp_adoption"] > 0)].iterrows():
        ev, hp = float(row["ev_adoption"]), float(row["hp_adoption"])
        ev_only = row.get("ev_only_peak_amplification_pct", amp.get((ev, 0.0), np.nan))
        hp_only = row.get("heat_pump_only_peak_amplification_pct", amp.get((0.0, hp), np.nan))
        combined = float(row["peak_amplification_pct"])
        additive = float(ev_only) + float(hp_only)
        rows.append(
            {
                "scenario": row.get("scenario", f"EV{int(ev * 100)}_HP{int(hp * 100)}"),
                "ev_adoption": ev,
                "hp_adoption": hp,
                "ev_only_amplification_pct": float(ev_only),
                "heat_pump_only_amplification_pct": float(hp_only),
                "additive_amplification_pct": additive,
                "combined_amplification_pct": combined,
                "diversity_gap_pp": additive - combined,
                "combined_share_of_additive": combined / additive if additive else np.nan,
            }
        )
    cols = [
        "scenario",
        "ev_adoption",
        "hp_adoption",
        "ev_only_amplification_pct",
        "heat_pump_only_amplification_pct",
        "additive_amplification_pct",
        "combined_amplification_pct",
        "diversity_gap_pp",
        "combined_share_of_additive",
    ]
    return pd.DataFrame(rows, columns=cols).sort_values(["ev_adoption", "hp_adoption"]).reset_index(drop=True)


def ladder(grid: pd.DataFrame) -> list[tuple[float, float]]:
    """The diagonal of the adoption grid: matching EV / heat-pump adoption steps."""
    ev_levels = sorted(grid["ev_adoption"].unique())
    hp_levels = sorted(grid["hp_adoption"].unique())
    return list(zip(ev_levels, hp_levels))


def plot_diversity_gap(grid: pd.DataFrame, path: Path) -> Path:
    """Additive (EV-only + heat-pump-only) versus combined peak, along the ladder."""
    table = diversity_gap_table(grid)
    steps = {(ev, hp) for ev, hp in ladder(grid)}
    table = table[[(r.ev_adoption, r.hp_adoption) in steps for r in table.itertuples()]]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(table))
    width = 0.38
    ax.bar(x - width / 2, table["ev_only_amplification_pct"], width, label="EV alone", color="#4C72B0")
    ax.bar(
        x - width / 2,
        table["heat_pump_only_amplification_pct"],
        width,
        bottom=table["ev_only_amplification_pct"],
        label="Heat pumps alone",
        color="#DD8452",
    )
    ax.bar(x + width / 2, table["combined_amplification_pct"], width, label="Combined", color="#55A868")
    for xi, row in zip(x, table.itertuples()):
        ax.annotate(
            f"{-row.diversity_gap_pp:+.0f} pp vs additive",
            (xi + width / 2, row.combined_amplification_pct),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=9,
        )
    labels = [f"EV {_pct_label(r.ev_adoption)}\nHP {_pct_label(r.hp_adoption)}" for r in table.itertuples()]
    ax.set_xticks(x, labels)
    ax.set_ylabel("Peak amplification (%)")
    ax.set_title("Diversity gap: combined peak versus EV alone + heat pumps alone")
    ax.legend(loc="upper left")
    ax.grid(axis="y", alpha=0.3)
    return _save(fig, path)


# ===========================================================================
# stress frequency and duration
# ===========================================================================
STRESS_COLUMNS = [
    "scenario",
    "ev_adoption",
    "hp_adoption",
    "peak_amplification_pct",
    "stress_frequency_pct",
    "stress_frequency_delta_pp",
    "stress_escalation_x",
    "stress_hours_per_week",
    "n_stress_events",
    "mean_event_hours",
    "max_event_hours",
    "event_duration_growth_x",
    "winter_stress_frequency_pct",
    "energy_above_threshold_kwh",
]


def stress_escalation_table(grid: pd.DataFrame) -> pd.DataFrame:
    """Stress frequency and duration per scenario, against the fixed thresholds."""
    cols = [c for c in STRESS_COLUMNS if c in grid.columns]
    return grid[cols].sort_values(["ev_adoption", "hp_adoption"]).reset_index(drop=True)


def plot_stress_frequency_duration(grid: pd.DataFrame, path: Path) -> Path:
    """Stress frequency and mean event duration against EV adoption, per heat-pump level."""
    table = stress_escalation_table(grid)
    fig, (ax_f, ax_d) = plt.subplots(1, 2, figsize=(13, 5.2), sharex=True)
    cmap = plt.get_cmap("viridis")
    hp_levels = sorted(table["hp_adoption"].unique())
    for i, hp in enumerate(hp_levels):
        sub = table[table["hp_adoption"] == hp].sort_values("ev_adoption")
        colour = cmap(i / max(len(hp_levels) - 1, 1))
        label = f"HP {_pct_label(hp)}"
        ax_f.plot(100 * sub["ev_adoption"], sub["stress_frequency_pct"], "o-", color=colour, label=label)
        ax_d.plot(100 * sub["ev_adoption"], sub["mean_event_hours"], "o-", color=colour, label=label)
        if "max_event_hours" in sub:
            ax_d.plot(100 * sub["ev_adoption"], sub["max_event_hours"], ":", color=colour, alpha=0.7)

    ax_f.set_title("Stress frequency (% of half-hours above threshold)")
    ax_f.set_ylabel("Stress frequency (%)")
    ax_d.set_title("Stress event duration (solid: mean, dotted: longest)")
    ax_d.set_ylabel("Event duration (hours)")
    for ax in (ax_f, ax_d):
        ax.set_xlabel("EV adoption (%)")
        ax.grid(alpha=0.3)
    ax_f.legend(title="Heat-pump adoption", fontsize=8)
    return _save(fig, path)


# ===========================================================================
# load-shape overlay
# ===========================================================================
WINTER_MONTHS = (12, 1, 2)
EVENING = (16.0, 22.0)  # hours; the window the evening peak is judged against
BASE_LABEL = "Base (no EV, no heat pump)"


def _winter(frame: pd.DataFrame) -> pd.DataFrame:
    winter = frame[frame["timestamp"].dt.month.isin(WINTER_MONTHS)]
    return winter if len(winter) else frame


def _diurnal(frame: pd.DataFrame, value_col: str) -> pd.Series:
    """Mean winter day per neighbourhood, averaged across neighbourhoods."""
    d = _winter(frame)
    period = d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30
    per_site = d.groupby([d["neighbourhood_id"], period], observed=True)[value_col].mean()
    profile = per_site.groupby(level=1).mean()
    return profile.reindex(range(48))


def load_shape_profiles(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Mean winter-day load shape for the base case and each scenario.

    ``frames`` maps a scenario label to an ``apply_scenario`` frame (with
    ``base_kwh`` and ``electrified_kwh``). The base profile is taken from the
    first frame. Returns a tidy table ``scenario, period, time, demand_kwh``.
    """
    if not frames:
        return pd.DataFrame(columns=["scenario", "period", "time", "demand_kwh"])
    first = next(iter(frames.values()))
    profiles = {BASE_LABEL: _diurnal(first, "base_kwh")}
    for label, frame in frames.items():
        profiles[label] = _diurnal(frame, "electrified_kwh")
    rows = []
    for label, profile in profiles.items():
        for period, value in profile.items():
            rows.append(
                {
                    "scenario": label,
                    "period": int(period),
                    "time": f"{int(period) // 2:02d}:{30 * (int(period) % 2):02d}",
                    "demand_kwh": float(value),
                }
            )
    return pd.DataFrame(rows)


def load_shape_summary(profiles: pd.DataFrame) -> pd.DataFrame:
    """Where the amplification lands, and how far the peak widens.

    Per scenario: the profile peak and its time, the peak amplification of the
    mean winter day, the hours per day spent above the base-case peak (the
    widening), and the share of the added energy that lands in the evening
    window.
    """
    base = profiles[profiles["scenario"] == BASE_LABEL].set_index("period")["demand_kwh"]
    base_peak = float(base.max())
    evening = (profiles["period"] >= EVENING[0] * 2) & (profiles["period"] < EVENING[1] * 2)
    rows = []
    for label, sub in profiles.groupby("scenario", sort=False):
        series = sub.set_index("period")["demand_kwh"]
        added = (series - base).clip(lower=0.0)
        in_evening = evening[sub.index].to_numpy()
        peak_period = int(series.idxmax())
        peak = float(series.max())
        rows.append(
            {
                "scenario": label,
                "peak_kwh": peak,
                "peak_time": f"{peak_period // 2:02d}:{30 * (peak_period % 2):02d}",
                "peak_amplification_pct": 100.0 * (peak / base_peak - 1.0) if base_peak else 0.0,
                "hours_above_base_peak": 0.5 * float((series > base_peak + 1e-9).sum()),
                "evening_share_of_added_energy": (
                    float(added[in_evening].sum() / added.sum()) if added.sum() > 0 else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def plot_load_shape_overlay(profiles: pd.DataFrame, path: Path) -> Path:
    """Overlay of the mean winter-day load shape, base case and scenario ladder."""
    fig, ax = plt.subplots(figsize=(11, 5.8))
    hours = np.arange(48) / 2.0
    labels = [s for s in profiles["scenario"].unique() if s != BASE_LABEL]
    cmap = plt.get_cmap("plasma")
    base = profiles[profiles["scenario"] == BASE_LABEL].sort_values("period")["demand_kwh"].to_numpy()

    ax.axvspan(*EVENING, color="grey", alpha=0.08, label="Evening window")
    ax.axhline(np.nanmax(base), color="black", linewidth=0.8, linestyle=":", label="Base-case peak")
    ax.plot(hours, base, color="black", linewidth=2.2, linestyle="--", label=BASE_LABEL)
    for i, label in enumerate(labels):
        series = profiles[profiles["scenario"] == label].sort_values("period")["demand_kwh"].to_numpy()
        colour = cmap(0.1 + 0.8 * i / max(len(labels) - 1, 1))
        ax.plot(hours, series, linewidth=1.8, color=colour, label=label)

    ax.set_xlim(0, 23.5)
    ax.set_xticks(range(0, 24, 2), [f"{h:02d}:00" for h in range(0, 24, 2)])
    ax.set_xlabel("Time of day")
    ax.set_ylabel("Mean winter-day demand per neighbourhood (kWh per half hour)")
    ax.set_title("Load shape: where in the day electrification lands")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper left")
    return _save(fig, path)
