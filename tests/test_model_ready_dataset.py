"""Processed model-ready dataset (DRG-51)."""

from __future__ import annotations

import copy
import dataclasses
import json

import pandas as pd
import pytest

from drg.features.dataset import (
    MANIFEST,
    SPLIT_COL,
    assign_split,
    config_hash,
    materialise_model_ready,
    split_frames,
)
from drg.features.engineering import build_feature_table, chronological_split, feature_columns
from drg.models.train import train_models


@pytest.fixture
def local_cfg(cfg, demand, tmp_path):
    """A private config whose processed / external dirs live in tmp_path."""
    local = dataclasses.replace(cfg, raw=copy.deepcopy(cfg.raw))
    local.paths = dataclasses.replace(
        cfg.paths, processed_dir=tmp_path / "processed", external_dir=tmp_path / "external"
    )
    local.paths.processed_dir.mkdir(parents=True)
    local.raw["models"]["test_size_days"] = 14
    local.raw["models"]["val_size_days"] = 7
    demand.to_parquet(local.paths.neighbourhood_demand, index=False)
    return local


# ------------------------------------------------------------ artefacts ----
def test_one_artefact_per_neighbourhood_named_with_the_config_hash(local_cfg, demand):
    ds = materialise_model_ready(local_cfg)
    assert ds.rebuilt
    assert sorted(ds.files) == sorted(demand["neighbourhood_id"].unique())
    digest = config_hash(local_cfg)
    for nid, path in ds.files.items():
        assert path.parent == local_cfg.paths.processed_dir / "model_ready"
        assert path.name == f"model_ready_{nid}_{digest}.parquet"
        site = pd.read_parquet(path)
        assert set(site["neighbourhood_id"]) == {nid}

    manifest = json.loads((ds.directory / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["config_hash"] == digest
    assert set(manifest["upstream"]) == {"neighbourhood_demand", "weather", "carbon"}
    assert manifest["upstream"]["neighbourhood_demand"]
    assert manifest["split"]["column"] == SPLIT_COL


def test_artefacts_are_feature_complete(local_cfg, demand):
    df = materialise_model_ready(local_cfg).load()
    expected = build_feature_table(demand, local_cfg)
    assert len(df) == len(expected)
    assert set(feature_columns(expected)) <= set(df.columns)
    assert "target" in df.columns
    assert not df[[c for c in df.columns if c.startswith("lag_")]].isna().any().any()
    assert SPLIT_COL not in feature_columns(df), "the split label is never a model input"


# ------------------------------------------------------- change detection --
def test_reused_until_config_or_data_changes(local_cfg, demand):
    first = materialise_model_ready(local_cfg)
    assert not materialise_model_ready(local_cfg).rebuilt, "unchanged inputs must be reused"
    assert materialise_model_ready(local_cfg, force=True).rebuilt

    local_cfg.raw["features"]["lags"] = [1, 2, 48]
    changed = materialise_model_ready(local_cfg)
    assert changed.rebuilt and changed.config_hash != first.config_hash
    names = sorted(p.name for p in changed.directory.glob("*.parquet"))
    assert all(changed.config_hash in n for n in names), "stale artefacts must be removed"

    demand.iloc[:-48].to_parquet(local_cfg.paths.neighbourhood_demand, index=False)
    assert materialise_model_ready(local_cfg).rebuilt, "new upstream data must trigger a rebuild"
    assert not materialise_model_ready(local_cfg).rebuilt


def test_missing_artefact_triggers_a_rebuild(local_cfg):
    ds = materialise_model_ready(local_cfg)
    next(iter(ds.files.values())).unlink()
    assert materialise_model_ready(local_cfg).rebuilt


def test_config_hash_ignores_unrelated_settings(local_cfg):
    before = config_hash(local_cfg)
    local_cfg.raw["electrification"]["ev"]["charger_kw"] = 11.0
    local_cfg.raw["api"]["port"] = 9000
    assert config_hash(local_cfg) == before
    local_cfg.raw["models"]["test_size_days"] = 20
    assert config_hash(local_cfg) != before, "the split windows shape the artefact"


# ------------------------------------------------------------- split label --
def test_split_label_matches_chronological_split(local_cfg, demand):
    table = build_feature_table(demand, local_cfg)
    labels = assign_split(table, test_days=14, val_days=7)
    train, val, test = chronological_split(table, test_days=14, val_days=7)
    assert (labels == "train").sum() == len(train)
    assert (labels == "validation").sum() == len(val)
    assert (labels == "test").sum() == len(test)


def test_split_frames_reads_the_label(local_cfg):
    df = materialise_model_ready(local_cfg).load()
    train, val, test = split_frames(df)
    assert len(train) + len(val) + len(test) == len(df)
    assert train["timestamp"].max() < val["timestamp"].min()
    assert val["timestamp"].max() < test["timestamp"].min()
    with pytest.raises(KeyError):
        split_frames(df.drop(columns=SPLIT_COL))
    bad = df.copy()
    bad.loc[bad.index[0], SPLIT_COL] = "holdout"
    with pytest.raises(ValueError):
        split_frames(bad)


def test_training_uses_the_dataset_split_not_its_own(local_cfg):
    local_cfg.raw["models"]["xgboost"]["n_estimators"] = 30
    df = materialise_model_ready(local_cfg).load()
    # move the first validation day into test: training must follow the label
    first_val_day = df.loc[df[SPLIT_COL] == "validation", "timestamp"].min().normalize()
    moved = (df[SPLIT_COL] == "validation") & (df["timestamp"].dt.normalize() == first_val_day)
    df.loc[moved, SPLIT_COL] = "test"

    result = train_models(df, local_cfg, train_lstm=False, save=False)
    assert len(result.predictions) == int((df[SPLIT_COL] == "test").sum())
    assert result.predictions["timestamp"].min() == df.loc[moved, "timestamp"].min()


def test_pipeline_features_stage_returns_the_labelled_dataset(local_cfg):
    from drg.pipeline import stage_features

    df = stage_features(local_cfg)
    assert SPLIT_COL in df.columns
    assert set(df[SPLIT_COL].unique()) == {"train", "validation", "test"}
    assert (local_cfg.paths.processed_dir / "model_ready" / MANIFEST).exists()
