"""Replay page: session controls, operator alarms and forecast explanations (DRG-117)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from drg.dashboard.theme import severity_badge
from drg.explain.local import local_contributions
from drg.features.engineering import build_feature_table, feature_columns
from drg.models.baseline import BaselineForecaster, SeasonalNaiveForecaster
from drg.models.gbm import XGBoostForecaster
from drg.models.registry import ModelBundle
from drg.streaming import REPLAY_LABEL, AlarmManager, ReplaySession, StreamingReplayEngine
from drg.stress.detection import compute_thresholds


@pytest.fixture(scope="module")
def table(cfg, demand):
    return build_feature_table(demand, cfg)


@pytest.fixture(scope="module")
def bundle(table):
    cols = feature_columns(table)
    model = XGBoostForecaster(n_estimators=60, max_depth=4).fit(table[cols], table["target"].to_numpy())
    return ModelBundle(name="test_gbm", estimator=model, feature_columns=cols, kind="xgboost")


@pytest.fixture
def session(cfg, demand, bundle):
    engine = StreamingReplayEngine(
        demand,
        bundle,
        compute_thresholds(demand),
        cfg,
        neighbourhood_id="N01",
        carbon=pd.DataFrame(),
        explain=True,
    )
    return ReplaySession(engine, speed=1800.0, source="synthetic data")


def _tick(ts, actual, forecast, severity, *, threshold=10.0):
    ts = pd.Timestamp(ts)
    return SimpleNamespace(
        timestamp=ts,
        neighbourhood_id="N01",
        actual_kwh=actual,
        forecast_next_kwh=forecast,
        forecast_timestamp=ts + pd.Timedelta(minutes=30),
        threshold_kwh=threshold,
        is_stress=actual >= threshold,
        forecast_is_stress=forecast >= threshold,
        severity=severity,
    )


# ------------------------------------------------------------- labelling ---
def test_replay_is_labelled_as_historical_not_live(session):
    session.step(2)
    label = session.label()
    assert label.startswith(REPLAY_LABEL)
    assert "not a live feed" in label.lower()
    assert f"{session.clock:%d %b %Y}" in label
    assert REPLAY_LABEL not in session.label(include_tag=False)
    assert session.status()["mode"] == "replay"


# -------------------------------------------------------------- controls ---
def test_play_pause_and_wall_clock_pacing(session):
    assert session.advance(10.0) == [] and not session.ticks, "paused replay must not advance"
    session.play()
    session.advance(2.5)  # 2.5 s at 1800x = 2.5 periods -> 2 now, 0.5 carried
    assert len(session.ticks) == 2
    session.advance(0.5)
    assert len(session.ticks) == 3, "the fractional period must carry over"
    session.pause()
    session.advance(100.0)
    assert len(session.ticks) == 3


def test_advance_is_capped_per_refresh(session):
    session.play()
    session.advance(3600.0, max_steps=10)
    assert len(session.ticks) == 10


def test_step_seek_and_reset(session):
    session.step(5)
    first = session.ticks[0].timestamp
    assert session.clock == first + pd.Timedelta(hours=2)

    target = pd.Timestamp(session.engine.series["timestamp"].iloc[-200])
    session.seek(target)
    assert not session.ticks and not session.alarms.events
    session.step(1)
    assert session.clock == target

    session.reset()
    assert not session.ticks and not session.playing


def test_replay_stops_at_the_end(session):
    session.seek(session.period[1])
    session.play()
    session.step(10)
    assert session.engine.exhausted and not session.playing


def test_speed_must_be_positive(session):
    with pytest.raises(ValueError):
        session.set_speed(0)
    session.set_speed(240)
    assert session.seconds_per_period == pytest.approx(7.5)


# ---------------------------------------------------------------- alarms ---
def test_alarm_lifecycle_raise_escalate_acknowledge_clear():
    alarms = AlarmManager()
    t = pd.date_range("2014-01-01 16:00", periods=6, freq="30min")
    alarms.update(_tick(t[0], 10.2, 9.0, "elevated"))
    alarms.update(_tick(t[1], 10.4, 9.0, "elevated"))
    assert len(alarms.alarms) == 1, "one alarm per condition, not one per half-hour"

    alarm = alarms.alarms[0]
    assert alarms.acknowledge(alarm.id, t[1]) and alarm.state == "acknowledged"
    assert not alarms.acknowledge(alarm.id), "already acknowledged"

    alarms.update(_tick(t[2], 12.6, 9.0, "critical"))
    assert alarm.level == "critical" and alarm.escalations == 1
    assert alarm.state == "active", "an escalation needs re-acknowledging"

    alarms.update(_tick(t[3], 9.0, 8.0, "watch"))
    assert alarm.state == "cleared" and alarm.cleared_at == t[3]
    assert alarm.duration_h == pytest.approx(1.5)
    assert alarm.peak_kwh == pytest.approx(12.6)
    assert [e.action for e in alarms.events] == ["raised", "acknowledged", "escalated", "cleared"]


def test_pre_emptive_alarm_is_superseded_by_measured_stress():
    alarms = AlarmManager()
    t = pd.date_range("2014-01-01 16:00", periods=3, freq="30min")
    alarms.update(_tick(t[0], 9.0, 10.5, "watch"))
    pre = alarms.alarms[0]
    assert pre.kind == "pre-emptive" and pre.is_open
    alarms.update(_tick(t[1], 10.3, 10.8, "elevated"))
    assert pre.state == "cleared"
    assert alarms.events[1].action == "superseded"
    assert alarms.open_alarm("measured") is not None


def test_pre_emptive_alarm_clears_when_forecast_falls_back():
    alarms = AlarmManager()
    t = pd.date_range("2014-01-01 16:00", periods=2, freq="30min")
    alarms.update(_tick(t[0], 9.0, 10.5, "watch"))
    alarms.update(_tick(t[1], 9.0, 9.2, "watch"))
    assert not alarms.active()
    assert alarms.events[-1].action == "cleared"


def test_active_alarms_are_most_severe_first():
    alarms = AlarmManager()
    ts = pd.Timestamp("2014-01-01 17:00")
    alarms.update(_tick(ts, 12.6, 13.0, "critical"))
    assert alarms.active()[0].level == "critical"
    assert alarms.acknowledge_all(ts) == 1 and not alarms.unacknowledged()


def test_session_feeds_alarms_from_real_ticks(session):
    session.engine.explain = False  # alarms only; keeps the one-week replay quick
    session.seek(session.period[1] - pd.Timedelta(days=14))
    session.step(336)
    assert len(session.ticks) == 336
    flagged = session.ticks_frame()["is_stress"].sum()
    assert flagged > 0, "the fixture series has stress periods"
    measured = [a for a in session.alarms.alarms if a.kind == "measured"]
    assert 0 < len(measured) <= flagged
    for event in session.alarms.events:
        assert session.ticks[0].timestamp <= event.timestamp <= session.clock, "replay timestamps only"


# ----------------------------------------------------------- explanation ---
def test_each_tick_explains_its_forecast(session):
    session.step(1)
    drivers = session.latest.drivers
    assert 0 < len(drivers) <= 5
    assert {"feature", "value", "contribution"} <= set(drivers[0])
    mags = [abs(d["contribution"]) for d in drivers]
    assert mags == sorted(mags, reverse=True)


def test_local_contributions_for_each_model_kind(table, bundle):
    cols = feature_columns(table)
    row = table[cols].iloc[[500]]
    xgb = local_contributions(bundle, row, top_n=3)
    assert len(xgb) == 3 and set(xgb["feature"]) <= set(cols)

    linear = BaselineForecaster().fit(table[cols], table["target"].to_numpy())
    lin = local_contributions(linear, row, top_n=4)
    assert len(lin) == 4

    naive = local_contributions(SeasonalNaiveForecaster(), row)
    assert list(naive["feature"]) == ["lag_48"]
    assert naive["contribution"].iloc[0] == pytest.approx(row["lag_48"].iloc[0])

    assert local_contributions(object(), row).empty


def test_replay_log_stays_parquet_writable(session, tmp_path):
    frame = session.engine.run(n=4)
    assert frame["drivers"].map(lambda v: isinstance(v, str)).all()
    frame.to_parquet(tmp_path / "log.parquet")


# ----------------------------------------------------------------- theme ---
def test_severity_badge_html_is_well_formed():
    badge = severity_badge("high")
    style = badge.split('style="', 1)[1].split('"', 1)[0]
    assert "Segoe UI" in style, "the whole font stack must stay inside the style attribute"
    assert badge.endswith("</span>")
