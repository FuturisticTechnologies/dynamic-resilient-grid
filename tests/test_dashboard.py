"""Dashboard smoke test.

``AppTest`` executes the Streamlit script in-process, so an exception in any
panel (a renamed column, a missing artifact, a bad Plotly argument) fails here
rather than in front of a user.
"""

from __future__ import annotations

import pytest

from drg.config import load_config
from drg.dashboard import theme


def test_theme_palette_is_a_fixed_ordered_set():
    assert len(theme.SERIES) == 8
    assert len(set(theme.SERIES)) == 8, "categorical hues must be distinct"
    assert theme.SERIES[0] == "#2a78d6"
    for severity in ("normal", "elevated", "high", "critical"):
        assert severity in theme.STATUS


def test_severity_badge_carries_icon_and_label_not_colour_alone():
    badge = theme.severity_badge("critical")
    assert "CRITICAL" in badge
    assert theme.STATUS["critical"] in badge
    assert "<b>" in badge, "status must ship with an icon, never colour alone"


def test_base_layout_uses_a_single_axis_and_recessive_chrome():
    layout = theme.base_layout("Title")
    assert "yaxis2" not in layout, "dual-axis charts are not permitted"
    assert layout["yaxis"]["gridcolor"] == theme.GRIDLINE
    assert layout["legend"]["orientation"] == "h"
    assert layout["title"]["text"] == "Title"


def test_dashboard_script_runs_without_exceptions():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    cfg = load_config()
    if not cfg.paths.neighbourhood_demand.exists():
        pytest.skip("processed demand not built; run `python -m drg.cli run-all`")

    app = AppTest.from_file(str(cfg.paths.root / "src" / "drg" / "dashboard" / "app.py"), default_timeout=180)
    app.run()

    assert not app.exception, f"dashboard raised: {[str(e) for e in app.exception]}"
    assert any("Dynamic Resilient Grid" in str(t.value) for t in app.title)
    assert len(app.tabs) >= 5, "all five panels must render"
