"""Train / validation / test window definition tests (DRG-57)."""

from __future__ import annotations

import pandas as pd
import pytest

from drg.features.engineering import build_feature_table, chronological_split
from drg.models.train import train_models
from drg.models.windows import (
    SplitWindows,
    WindowError,
    define_windows,
    windows_from_config,
)
from drg.pipeline import project_windows


def _grid(start="2013-01-01", end="2014-01-01", sites=("N01", "N02")) -> pd.DataFrame:
    index = pd.date_range(start, end, freq="30min", inclusive="left")
    return pd.concat(
        [pd.DataFrame({"timestamp": index, "neighbourhood_id": s, "target": 1.0}) for s in sites],
        ignore_index=True,
    )


def test_configured_windows_match_the_ticket(cfg):
    assert int(cfg.models["test_size_days"]) == 60
    assert int(cfg.models["val_size_days"]) > 0
    assert cfg.models.get("train_start") is None, "training starts at the start of the usable series"


def test_sixty_day_test_window_is_2880_half_hours_per_site(cfg):
    df = _grid()
    train, val, test = windows_from_config(cfg, df["timestamp"]).split(df)
    per_site = test.groupby("neighbourhood_id").size()
    assert (per_site == 60 * 48).all()
    assert test["timestamp"].max() == df["timestamp"].max(), "test runs to the end of the series"


def test_windows_are_chronological_disjoint_and_complete(cfg):
    df = _grid()
    windows = windows_from_config(cfg, df["timestamp"])
    train, val, test = windows.split(df)
    assert train["timestamp"].max() < val["timestamp"].min()
    assert val["timestamp"].max() < test["timestamp"].min()
    assert len(train) + len(val) + len(test) == len(df), "every usable row lands in exactly one window"
    assert train["timestamp"].min() == df["timestamp"].min(), "training starts at the first usable row"


def test_train_start_override_and_clamp():
    df = _grid()
    w = define_windows(df["timestamp"], test_days=60, val_days=30, train_start="2013-03-01")
    assert w.train_start == pd.Timestamp("2013-03-01")
    early = define_windows(df["timestamp"], test_days=60, val_days=30, train_start="2000-01-01")
    assert early.train_start == df["timestamp"].min()


def test_series_too_short_is_rejected():
    df = _grid("2013-11-01", "2014-01-01")
    with pytest.raises(WindowError):
        define_windows(df["timestamp"], test_days=60, val_days=30)
    with pytest.raises(WindowError):
        define_windows(_grid()["timestamp"], test_days=60, val_days=30, min_train_days=400)


def test_split_refuses_empty_windows():
    windows = define_windows(_grid()["timestamp"], test_days=60, val_days=30)
    only_train = _grid("2013-01-01", "2013-02-01")
    with pytest.raises(WindowError):
        windows.split(only_train)
    train, val, test = windows.split(only_train, require_all=False)
    assert len(train) and val.empty and test.empty


def test_windows_roundtrip(tmp_path):
    windows = define_windows(_grid()["timestamp"], test_days=60, val_days=30)
    restored = SplitWindows.load(windows.save(tmp_path / "w.json"))
    assert restored == windows
    assert restored.to_dict()["test_days"] == 60


def test_invalid_window_order_is_rejected():
    with pytest.raises(WindowError):
        SplitWindows("2014-01-01", "2013-06-01", "2013-12-01", "2014-02-01")


def test_chronological_split_uses_the_same_geometry():
    df = _grid()
    expected = define_windows(df["timestamp"], test_days=14, val_days=7).split(df)
    actual = chronological_split(df, test_days=14, val_days=7)
    for a, b in zip(actual, expected):
        pd.testing.assert_frame_equal(a, b)


def test_project_windows_prefers_the_saved_file(cfg, tmp_path, monkeypatch):
    df = _grid()
    saved = define_windows(df["timestamp"], test_days=20, val_days=10)
    path = saved.save(tmp_path / "split_windows.json")
    monkeypatch.setattr(type(cfg.paths), "split_windows", property(lambda self: path))
    assert project_windows(cfg, df) == saved

    path.unlink()
    assert project_windows(cfg, df) == windows_from_config(cfg, df["timestamp"])


@pytest.fixture(scope="module")
def trained(cfg, demand):
    # the fixture series is ~4 months, so use shorter windows than production
    table = build_feature_table(demand, cfg)
    windows = define_windows(table["timestamp"], test_days=14, val_days=7)
    return table, windows, train_models(table, cfg, train_lstm=False, save=False, windows=windows)


def test_harness_uses_one_window_set_for_every_model(trained):
    table, windows, result = trained
    assert result.windows == windows

    test = result.windows.test_frame(table)
    assert len(result.predictions) == len(test)
    assert result.predictions["timestamp"].min() >= result.windows.test_start

    expected = result.windows.to_dict()
    for name, bundle in result.bundles.items():
        assert bundle.metadata["windows"] == expected, f"{name} trained on different windows"


def test_champion_is_selected_on_validation_not_test(trained):
    _, _, result = trained
    val = result.validation_metrics
    assert set(val["model"]) == set(result.metrics["model"])
    eligible = val[val["model"].isin(result.bundles)]
    assert result.best.name == eligible.sort_values("rmse")["model"].iloc[0]
    assert result.headline()["model"] == result.best.name
