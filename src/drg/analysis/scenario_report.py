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
