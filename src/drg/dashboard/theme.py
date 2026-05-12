"""Shared visual language for every DRG chart.

Colour is assigned by the *job* it does, never by series index order chosen at
random: categorical hues in a fixed validated order, one blue ramp for
magnitude, and a reserved status palette for stress state that is always paired
with an icon and a label so state is never carried by colour alone.
"""

from __future__ import annotations

from typing import Any

# --- categorical slots (fixed order; never cycled) -------------------------
SERIES = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

# --- sequential ramp (magnitude) -------------------------------------------
SEQUENTIAL_BLUE = [
    [0.00, "#cde2fb"],
    [0.20, "#9ec5f4"],
    [0.40, "#6da7ec"],
    [0.60, "#3987e5"],
    [0.80, "#256abf"],
    [1.00, "#0d366b"],
]

# --- status (reserved; always with icon + label) ---------------------------
STATUS = {
    "normal": "#0ca30c",
    "watch": "#0ca30c",
    "elevated": "#fab219",
    "high": "#ec835a",
    "critical": "#d03b3b",
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "unknown": "#898781",
}
STATUS_ICON = {
    "normal": "OK",
    "watch": "OK",
    "elevated": "!",
    "high": "!!",
    "critical": "!!!",
    "unknown": "?",
}

# --- chrome ----------------------------------------------------------------
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def base_layout(title: str | None = None, height: int = 380, **kwargs: Any) -> dict[str, Any]:
    """Recessive chrome, single y-axis, legend always present for 2+ series."""
    layout: dict[str, Any] = {
        "height": height,
        "template": "plotly_white",
        "paper_bgcolor": SURFACE,
        "plot_bgcolor": SURFACE,
        "font": {"family": FONT, "color": INK_SECONDARY, "size": 13},
        "margin": {"l": 60, "r": 24, "t": 52 if title else 20, "b": 48},
        "hovermode": "x unified",
        "hoverlabel": {"font": {"family": FONT, "size": 12}, "bgcolor": SURFACE},
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 12},
        },
        "xaxis": {
            "showgrid": False,
            "linecolor": BASELINE,
            "ticks": "outside",
            "tickcolor": BASELINE,
            "tickfont": {"color": INK_MUTED, "size": 11},
        },
        "yaxis": {
            "gridcolor": GRIDLINE,
            "zeroline": False,
            "linecolor": BASELINE,
            "tickfont": {"color": INK_MUTED, "size": 11},
        },
    }
    if title:
        layout["title"] = {
            "text": title,
            "font": {"family": FONT, "size": 15, "color": INK_PRIMARY},
            "x": 0,
            "xanchor": "left",
        }
    layout.update(kwargs)
    return layout


def severity_badge(severity: str) -> str:
    """Icon + label + colour -- never colour alone."""
    colour = STATUS.get(severity, STATUS["unknown"])
    icon = STATUS_ICON.get(severity, "?")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:.4rem;'
        f"padding:.15rem .55rem;border-radius:999px;background:{colour}22;"
        f"border:1px solid {colour};color:{INK_PRIMARY};font-size:.82rem;"
        f'font-family:{FONT}"><b>{icon}</b> {severity.upper()}</span>'
    )
