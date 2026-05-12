"""DRG Streamlit dashboard.

Five panels, matching proposal section 7.10:

* **Live** - streaming replay of neighbourhood demand with the rolling
  one-step-ahead forecast, the fixed statistical stress threshold and the
  alert state;
* **Stress** - historical stress frequency, duration and diurnal pattern;
* **Scenarios** - interactive EV / heat-pump adoption sliders with the
  resulting electrified load profile and recomputed stress;
* **Sensitivity** - the full adoption grid, peak amplification surface and
  elasticity curves;
* **Explainability** - SHAP driver ranking, globally and during stress.

Every chart ships a matching data table (the palette carries a contrast
relief obligation), a legend whenever two or more series are drawn, and a
single y-axis.

Run with:  streamlit run src/drg/dashboard/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

if __package__ in (None, ""):  # allow `streamlit run src/drg/dashboard/app.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from drg import __version__  # noqa: E402
from drg.config import load_config  # noqa: E402
from drg.dashboard.theme import (  # noqa: E402
    INK_MUTED,
    SEQUENTIAL_BLUE,
    SERIES,
    STATUS,
    base_layout,
    severity_badge,
)
from drg.data.external_apis import fetch_context_snapshot  # noqa: E402
from drg.simulation.electrification import (  # noqa: E402
    EVConfig,
    HeatPumpConfig,
    apply_scenario,
)
from drg.stress.detection import (  # noqa: E402
    compute_thresholds,
    detect_stress,
    diurnal_stress_profile,
    stress_events,
    stress_summary,
)

st.set_page_config(
    page_title="Dynamic Resilient Grid",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ===========================================================================
# cached loaders
# ===========================================================================
@st.cache_resource(show_spinner=False)
def get_cfg():
    return load_config()


@st.cache_data(show_spinner="Loading demand data...")
def load_demand() -> pd.DataFrame:
    cfg = get_cfg()
    path = cfg.paths.neighbourhood_demand
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def load_thresholds_dict() -> dict:
    cfg = get_cfg()
    demand = load_demand()
    if demand.empty:
        return {}
    return compute_thresholds(
        demand,
        percentile=float(cfg.stress["primary_percentile"]),
        sigma=float(cfg.stress["sensitivity_sigma"]),
    )


@st.cache_resource(show_spinner=False)
def load_bundle():
    from drg.models.registry import load_best

    try:
        return load_best(get_cfg().paths.model_dir)
    except FileNotFoundError:
        return None


@st.cache_data(show_spinner=False)
def load_report(name: str):
    path = get_cfg().paths.report_dir / name
    if not path.exists():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return pd.read_parquet(path)


@st.cache_data(ttl=900, show_spinner=False)
def live_context() -> dict:
    cfg = get_cfg()
    return fetch_context_snapshot(
        float(cfg.external["latitude"]),
        float(cfg.external["longitude"]),
        api_key=cfg.openweather_key,
        carbon_base_url=cfg.carbon_base_url,
        region_id=int(cfg.external.get("region_id", 13)),
        cache_dir=cfg.paths.external_dir,
    )


def table_view(df: pd.DataFrame, label: str = "Data table") -> None:
    with st.expander(label):
        st.dataframe(df, use_container_width=True, hide_index=True)


# ===========================================================================
# sidebar
# ===========================================================================
cfg = get_cfg()
demand = load_demand()

st.sidebar.title("⚡ Dynamic Resilient Grid")
st.sidebar.caption(f"v{__version__} · AI-driven electrification stress analysis")

if demand.empty:
    st.title("Dynamic Resilient Grid")
    st.error("No processed data found.\n\n" "Build it first:\n\n" "```bash\npython -m drg.cli run-all\n```")
    st.stop()

sites = sorted(demand["neighbourhood_id"].unique())
site = st.sidebar.selectbox("Neighbourhood", sites, index=0)
st.sidebar.divider()

st.sidebar.subheader("Electrification scenario")
ev_adoption = st.sidebar.slider(
    "EV adoption", 0.0, 1.0, 0.4, 0.05, help="Share of households with a 7 kW home charger"
)
hp_adoption = st.sidebar.slider(
    "Heat pump adoption", 0.0, 1.0, 0.3, 0.05, help="Share of households with an electrified heating system"
)
charger_kw = st.sidebar.slider(
    "Charger rating (kW)", 3.0, 22.0, float(cfg.electrification["ev"]["charger_kw"]), 0.5
)
window_days = st.sidebar.slider("Scenario window (days)", 30, 365, 120, 15)
st.sidebar.divider()

ctx = live_context()
weather, carbon = ctx.get("weather", {}), ctx.get("carbon_intensity", {})
st.sidebar.subheader("Live context")
temp = weather.get("temperature_c")
st.sidebar.metric(
    "Temperature",
    f"{temp:.1f} °C" if temp is not None else "n/a",
    help=f"source: {weather.get('source', 'n/a')}",
)
ci = carbon.get("regional_forecast_gco2_kwh") or carbon.get("national_forecast_gco2_kwh")
st.sidebar.metric(
    "Carbon intensity",
    f"{ci:.0f} gCO₂/kWh" if ci else "n/a",
    help=f"{carbon.get('region', 'GB')} · source: {carbon.get('source', 'n/a')}",
)
st.sidebar.caption("Sources: Open-Meteo / OpenWeatherMap · National Grid ESO Carbon Intensity API")


# ===========================================================================
# header KPIs
# ===========================================================================
@st.cache_data(show_spinner=False)
def site_series(days: int) -> pd.DataFrame:
    return demand[demand["neighbourhood_id"] == site].sort_values("timestamp")


site_demand = site_series(window_days)
thresholds = load_thresholds_dict()
threshold = thresholds[site].primary_kwh if site in thresholds else float("nan")
flagged_hist = detect_stress(site_demand, thresholds)

st.title("Dynamic Resilient Grid")
st.caption(
    f"{site} · {int(site_demand['n_households'].iloc[0])} households · "
    f"{site_demand['timestamp'].min():%b %Y} – {site_demand['timestamp'].max():%b %Y} · "
    f"data source: {site_demand.get('source', pd.Series(['n/a'])).iloc[0]}"
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Peak demand", f"{site_demand['demand_kwh'].max():,.0f} kWh/hh")
k2.metric(f"P{int(cfg.stress['primary_percentile'])} stress threshold", f"{threshold:,.0f} kWh/hh")
k3.metric("Stress frequency", f"{100 * flagged_hist['is_stress'].mean():.2f}%")
k4.metric("Load factor", f"{site_demand['demand_kwh'].mean() / site_demand['demand_kwh'].max():.2f}")
metrics_json = load_report("model_metrics.json")
if metrics_json:
    best = metrics_json.get("champion", "n/a")
    row = next((m for m in metrics_json["test_metrics"] if m["model"] == best), {})
    k5.metric(
        f"Forecast R² ({best})",
        f"{row.get('r2', float('nan')):.3f}",
        help=f"MAE {row.get('mae', float('nan')):.2f} · RMSE {row.get('rmse', float('nan')):.2f}",
    )
else:
    k5.metric("Forecast R²", "n/a", help="Run: python -m drg.cli train")
