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
site_demand = demand[demand["neighbourhood_id"] == site].sort_values("timestamp")
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

tab_live, tab_stress, tab_scenario, tab_sens = st.tabs(
    ["Live & forecast", "Stress profile", "Scenario studio", "Sensitivity"]
)


# ===========================================================================
# 1. live replay
# ===========================================================================
with tab_live:
    st.subheader("Streaming replay with rolling forecast")
    bundle = load_bundle()
    if bundle is None:
        st.warning("No trained model found — run `python -m drg.cli train` to enable forecasting.")
    else:
        from drg.streaming.replay import StreamingReplayEngine

        steps = st.slider("Replay length (half-hourly steps)", 48, 672, 336, 48)
        window = int(cfg.streaming.get("window_periods", 336))
        engine = StreamingReplayEngine(
            demand,
            bundle,
            thresholds,
            cfg,
            neighbourhood_id=site,
            start_index=max(len(site_demand) - steps - 1, window + 1),
        )
        ticks = pd.DataFrame([t.to_dict() for t in engine.stream(n=steps)])
        ticks["timestamp"] = pd.to_datetime(ticks["timestamp"])

        latest = ticks.iloc[-1]
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.markdown(
            f"**Current state** &nbsp; {severity_badge(str(latest['severity']))}",
            unsafe_allow_html=True,
        )
        c2.metric(
            "Headroom to threshold", f"{latest['headroom_kwh']:,.1f} kWh", f"{latest['headroom_pct']:.1f}%"
        )
        c3.metric("Alerts in window", int(ticks["is_stress"].sum() + ticks["forecast_is_stress"].sum()))

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=ticks["timestamp"],
                y=ticks["actual_kwh"],
                name="Measured demand",
                mode="lines",
                line={"color": SERIES[0], "width": 2},
                hovertemplate="%{y:.1f} kWh<extra>Measured</extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=ticks["forecast_timestamp"].astype("datetime64[ns]"),
                y=ticks["forecast_next_kwh"],
                name="One-step forecast",
                mode="lines",
                line={"color": SERIES[1], "width": 2, "dash": "dot"},
                hovertemplate="%{y:.1f} kWh<extra>Forecast</extra>",
            )
        )
        stressed = ticks[ticks["is_stress"]]
        if len(stressed):
            fig.add_trace(
                go.Scatter(
                    x=stressed["timestamp"],
                    y=stressed["actual_kwh"],
                    name="Stress period",
                    mode="markers",
                    marker={"color": STATUS["critical"], "size": 9, "line": {"color": "#fcfcfb", "width": 2}},
                    hovertemplate="%{y:.1f} kWh<extra>Stress</extra>",
                )
            )
        fig.add_hline(
            y=threshold,
            line={"color": INK_MUTED, "width": 1, "dash": "dash"},
            annotation_text=f"P{int(cfg.stress['primary_percentile'])} threshold " f"{threshold:,.0f} kWh",
            annotation_position="top left",
            annotation_font={"color": INK_MUTED, "size": 11},
        )
        fig.update_layout(**base_layout("Measured vs forecast demand", height=430))
        fig.update_yaxes(title_text="kWh per half hour")
        st.plotly_chart(fig, use_container_width=True)

        table_view(
            ticks[
                [
                    "timestamp",
                    "actual_kwh",
                    "forecast_next_kwh",
                    "threshold_kwh",
                    "severity",
                    "is_stress",
                    "forecast_is_stress",
                ]
            ].round(2),
            "Replay tick log",
        )


# ===========================================================================
# 2. stress profile
# ===========================================================================
with tab_stress:
    st.subheader("Historical statistical stress")
    events = stress_events(flagged_hist, min_periods=int(cfg.stress["min_event_periods"]))
    summary = stress_summary(flagged_hist, events)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stress events", int(len(events)))
    c2.metric("Stress hours / week", f"{summary['stress_hours_per_week'].iloc[0]:.1f}")
    c3.metric("Mean event duration", f"{summary['mean_event_hours'].iloc[0]:.1f} h")
    c4.metric("Peak / threshold", f"{summary['peak_to_threshold_ratio'].iloc[0]:.2f}×")

    diurnal = diurnal_stress_profile(flagged_hist)
    diurnal = diurnal[diurnal["neighbourhood_id"] == site]
    fig = go.Figure(
        go.Bar(
            x=diurnal["period_of_day"] / 2.0,
            y=diurnal["stress_rate_pct"],
            marker={"color": SERIES[0], "line": {"color": "#fcfcfb", "width": 2}},
            hovertemplate="%{y:.1f}% of half-hours<extra>%{x}:00</extra>",
            name="Stress rate",
        )
    )
    fig.update_layout(**base_layout("When does stress occur? (share of half-hours above threshold)"))
    fig.update_xaxes(title_text="Hour of day", dtick=2)
    fig.update_yaxes(title_text="% of periods in stress")
    st.plotly_chart(fig, use_container_width=True)

    if len(events):
        monthly = (
            events.assign(month=lambda d: pd.to_datetime(d["start"]).dt.to_period("M").astype(str))
            .groupby("month")
            .agg(events=("duration_hours", "size"), hours=("duration_hours", "sum"))
            .reset_index()
        )
        fig = go.Figure(
            go.Bar(
                x=monthly["month"],
                y=monthly["hours"],
                marker={"color": SERIES[2], "line": {"color": "#fcfcfb", "width": 2}},
                hovertemplate="%{y:.1f} stress hours<extra>%{x}</extra>",
                name="Stress hours",
            )
        )
        fig.update_layout(**base_layout("Seasonal concentration of stress"))
        fig.update_yaxes(title_text="Stress hours in month")
        st.plotly_chart(fig, use_container_width=True)
        table_view(events.tail(50).round(2), "Stress event log (most recent 50)")


# ===========================================================================
# 3. scenario studio
# ===========================================================================
with tab_scenario:
    st.subheader("Electrification scenario studio")
    cutoff = site_demand["timestamp"].max() - pd.Timedelta(days=window_days)
    base_window = site_demand[site_demand["timestamp"] >= cutoff]

    ev_cfg = EVConfig.from_config(cfg.electrification["ev"])
    ev_cfg.charger_kw = charger_kw
    hp_cfg = HeatPumpConfig.from_config(cfg.electrification["heat_pump"])

    result = apply_scenario(
        base_window,
        ev_adoption,
        hp_adoption,
        ev_config=ev_cfg,
        hp_config=hp_cfg,
        seed=cfg.seed,
        runs=1,
    )
    scen_flagged = detect_stress(result.frame, thresholds, value_col="electrified_kwh")
    base_rate = 100.0 * flagged_hist[flagged_hist["timestamp"] >= cutoff]["is_stress"].mean()
    scen_rate = 100.0 * scen_flagged["is_stress"].mean()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Peak amplification", f"{result.summary['peak_amplification_pct']:+.1f}%")
    c2.metric("Energy growth", f"{result.summary['energy_growth_pct']:+.1f}%")
    c3.metric("Stress frequency", f"{scen_rate:.2f}%", f"{scen_rate - base_rate:+.2f} pp")
    c4.metric(
        "New peak",
        f"{result.summary['electrified_peak_kwh']:,.0f} kWh/hh",
        f"{result.summary['electrified_peak_kwh'] - result.summary['base_peak_kwh']:+,.0f}",
    )

    profile = (
        result.frame.assign(period=lambda d: d["timestamp"].dt.hour * 2 + d["timestamp"].dt.minute // 30)
        .groupby("period")[["base_kwh", "ev_kwh", "heat_pump_kwh", "electrified_kwh"]]
        .mean()
        .reset_index()
    )
    hours = profile["period"] / 2.0
    fig = go.Figure()
    for name, col, colour in (
        ("Base demand", "base_kwh", SERIES[0]),
        ("EV charging", "ev_kwh", SERIES[1]),
        ("Heat pumps", "heat_pump_kwh", SERIES[2]),
    ):
        fig.add_trace(
            go.Scatter(
                x=hours,
                y=profile[col],
                name=name,
                mode="lines",
                stackgroup="load",
                line={"color": colour, "width": 2},
                hovertemplate="%{y:.1f} kWh<extra>" + name + "</extra>",
            )
        )
    fig.add_hline(
        y=threshold,
        line={"color": INK_MUTED, "width": 1, "dash": "dash"},
        annotation_text=f"Stress threshold {threshold:,.0f} kWh",
        annotation_position="top left",
        annotation_font={"color": INK_MUTED, "size": 11},
    )
    fig.update_layout(
        **base_layout(f"Mean daily profile · EV {ev_adoption:.0%} · heat pumps {hp_adoption:.0%}", height=430)
    )
    fig.update_xaxes(title_text="Hour of day", dtick=2)
    fig.update_yaxes(title_text="kWh per half hour")
    st.plotly_chart(fig, use_container_width=True)
    table_view(profile.round(2), "Mean daily profile by component")

    worst_day = (
        result.frame.assign(date=lambda d: d["timestamp"].dt.date)
        .groupby("date")["electrified_kwh"]
        .max()
        .idxmax()
    )
    day = result.frame[result.frame["timestamp"].dt.date == worst_day]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=day["timestamp"],
            y=day["base_kwh"],
            name="Base demand",
            mode="lines",
            line={"color": SERIES[0], "width": 2},
            hovertemplate="%{y:.1f} kWh<extra>Base</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=day["timestamp"],
            y=day["electrified_kwh"],
            name="Electrified demand",
            mode="lines",
            line={"color": SERIES[1], "width": 2},
            hovertemplate="%{y:.1f} kWh<extra>Electrified</extra>",
        )
    )
    fig.add_hline(y=threshold, line={"color": INK_MUTED, "width": 1, "dash": "dash"})
    fig.update_layout(**base_layout(f"Worst modelled day ({worst_day})"))
    fig.update_yaxes(title_text="kWh per half hour")
    st.plotly_chart(fig, use_container_width=True)


# ===========================================================================
# 4. sensitivity
# ===========================================================================
with tab_sens:
    st.subheader("Adoption sensitivity")
    grid = load_report("sensitivity_grid.parquet")
    if grid is None:
        st.info("Run `python -m drg.cli scenarios` to build the sensitivity grid.")
    else:
        pivot = grid.pivot_table(index="hp_adoption", columns="ev_adoption", values="peak_amplification_pct")
        fig = go.Figure(
            go.Heatmap(
                z=pivot.to_numpy(),
                x=[f"{c:.0%}" for c in pivot.columns],
                y=[f"{i:.0%}" for i in pivot.index],
                colorscale=SEQUENTIAL_BLUE,
                colorbar={"title": "% peak<br>increase"},
                hovertemplate="EV %{x} · HP %{y}<br>%{z:.1f}% peak increase<extra></extra>",
                text=np.round(pivot.to_numpy(), 1),
                texttemplate="%{text}",
                textfont={"size": 11},
            )
        )
        fig.update_layout(**base_layout("Peak amplification across the adoption grid", height=420))
        fig.update_xaxes(title_text="EV adoption")
        fig.update_yaxes(title_text="Heat pump adoption")
        st.plotly_chart(fig, use_container_width=True)

        fig = go.Figure()
        for i, (hp_level, sub) in enumerate(grid.groupby("hp_adoption")):
            sub = sub.sort_values("ev_adoption")
            fig.add_trace(
                go.Scatter(
                    x=sub["ev_adoption"],
                    y=sub["stress_frequency_pct"],
                    name=f"Heat pumps {hp_level:.0%}",
                    mode="lines+markers",
                    line={"color": SERIES[i % len(SERIES)], "width": 2},
                    marker={"size": 8, "line": {"color": "#fcfcfb", "width": 2}},
                    hovertemplate="%{y:.2f}% of half-hours<extra>"
                    f"HP {hp_level:.0%}" + " · EV %{x:.0%}</extra>",
                )
            )
        fig.update_layout(**base_layout("Stress escalation with EV adoption"))
        fig.update_xaxes(title_text="EV adoption", tickformat=".0%")
        fig.update_yaxes(title_text="% of half-hours in stress")
        st.plotly_chart(fig, use_container_width=True)

        headline = load_report("sensitivity_summary.json")
        if headline:
            st.markdown(
                f"**Worst modelled case — {headline['worst_case_scenario']}:** "
                f"peak +{headline['worst_case_peak_amplification_pct']:.1f}%, "
                f"stress frequency {headline['worst_case_stress_frequency_pct']:.2f}% of half-hours "
                f"({headline.get('worst_case_stress_escalation_x', float('nan')):.1f}× the base case), "
                f"mean event duration {headline['worst_case_mean_event_hours']:.1f} h."
            )
        table_view(
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
            ].round(2),
            "Sensitivity grid",
        )
