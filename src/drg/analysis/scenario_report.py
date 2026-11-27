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
