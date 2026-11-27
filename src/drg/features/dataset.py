"""The processed, model-ready dataset (DRG-51).

Training used to rebuild every feature on every run and let each model stage
choose its own train / validation / test split. This module materialises the
feature table once, as **one artefact per neighbourhood** under
``data/processed/model_ready/``, with:

* every engineered feature and the ``target`` already computed;
* a ``split`` column (``train`` / ``validation`` / ``test``) assigned once,
  from ``models.val_size_days`` / ``models.test_size_days``, so no stage can
  pick its own split and model comparisons stay comparisons;
* the **config hash** in the file name and in ``manifest.json``.

The artefacts are rebuilt only when the configuration that shapes them or the
upstream data changes. The manifest records a hash of the dataset-relevant
config and a content fingerprint of each upstream file (the cleaned demand
table and the weather / carbon context); if both still match and every file is
present, the existing artefacts are reused.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from drg.features.engineering import build_feature_table, feature_columns
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

SPLIT_COL = "split"
TRAIN, VALIDATION, TEST = "train", "validation", "test"
SPLITS = (TRAIN, VALIDATION, TEST)
MANIFEST = "manifest.json"
SUBDIR = "model_ready"
SCHEMA_VERSION = 1


# ===========================================================================
# split labelling
# ===========================================================================
def split_boundaries(timestamps: pd.Series, test_days: float, val_days: float) -> dict[str, pd.Timestamp]:
    """Validation and test start times, measured back from the last timestamp.

    The same boundaries as :func:`drg.features.engineering.chronological_split`.
    """
    end = pd.Timestamp(pd.to_datetime(timestamps).max())
    test_start = end - pd.Timedelta(days=float(test_days))
    val_start = test_start - pd.Timedelta(days=float(val_days))
    return {"val_start": val_start, "test_start": test_start, "end": end}


def assign_split(df: pd.DataFrame, test_days: float = 60, val_days: float = 30) -> pd.Series:
    """``train`` / ``validation`` / ``test`` per row, chronologically."""
    bounds = split_boundaries(df["timestamp"], test_days, val_days)
    ts = pd.to_datetime(df["timestamp"])
    labels = pd.Series(TRAIN, index=df.index, dtype="object")
    labels[(ts >= bounds["val_start"]) & (ts < bounds["test_start"])] = VALIDATION
    labels[ts >= bounds["test_start"]] = TEST
    return labels


def split_frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(train, validation, test) taken from the artefact's own ``split`` label."""
    if SPLIT_COL not in df.columns:
        raise KeyError(f"frame has no '{SPLIT_COL}' column; build it with materialise_model_ready")
    unknown = set(df[SPLIT_COL].unique()) - set(SPLITS)
    if unknown:
        raise ValueError(f"unexpected split labels: {sorted(unknown)}")
    parts = tuple(df[df[SPLIT_COL] == s].copy() for s in SPLITS)
    log.info(
        "split (from dataset label) -> train %s | validation %s | test %s",
        *(f"{len(p):,}" for p in parts),
    )
    return parts  # type: ignore[return-value]


# ===========================================================================
# change detection
# ===========================================================================
def dataset_config(cfg: Any) -> dict[str, Any]:
    """The configuration that determines the model-ready dataset's contents."""
    return {
        "schema_version": SCHEMA_VERSION,
        "seed": cfg.seed,
        "data": {k: v for k, v in cfg.data.items() if k not in {"lcl_glob", "chunk_size"}},
        "features": cfg.features,
        "split": {
            "test_size_days": cfg.models.get("test_size_days", 60),
            "val_size_days": cfg.models.get("val_size_days", 30),
        },
        "external": {
            k: cfg.external.get(k) for k in ("latitude", "longitude", "use_weather", "use_carbon_intensity")
        },
        "heat_pump_base_temperature_c": cfg.get("electrification.heat_pump.base_temperature_c", 15.5),
    }


def config_hash(cfg: Any, length: int = 12) -> str:
    """Stable short hash of :func:`dataset_config`."""
    payload = json.dumps(dataset_config(cfg), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def file_fingerprint(path: Path) -> str | None:
    """SHA-256 of a file's bytes, or ``None`` when it does not exist."""
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def upstream_fingerprints(cfg: Any) -> dict[str, str | None]:
    paths = cfg.paths
    return {
        "neighbourhood_demand": file_fingerprint(paths.neighbourhood_demand),
        "weather": file_fingerprint(paths.weather),
        "carbon": file_fingerprint(paths.carbon),
    }


# ===========================================================================
# artefacts
# ===========================================================================
@dataclass
class ModelReadyDataset:
    """Location and provenance of the materialised per-neighbourhood artefacts."""

    directory: Path
    config_hash: str
    files: dict[str, Path] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    rebuilt: bool = False

    def load(self, neighbourhoods: list[str] | None = None) -> pd.DataFrame:
        """Concatenate the artefacts (optionally a subset of neighbourhoods)."""
        wanted = neighbourhoods or sorted(self.files)
        frames = [pd.read_parquet(self.files[n]) for n in wanted]
        out = pd.concat(frames, ignore_index=True)
        return out.sort_values(["neighbourhood_id", "timestamp"]).reset_index(drop=True)


def _site_file(directory: Path, neighbourhood_id: str, digest: str) -> Path:
    return directory / f"model_ready_{neighbourhood_id}_{digest}.parquet"


def _read_manifest(directory: Path) -> dict[str, Any] | None:
    path = directory / MANIFEST
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_current(
    manifest: dict[str, Any] | None, digest: str, upstream: dict[str, Any], directory: Path
) -> bool:
    if not manifest:
        return False
    if manifest.get("config_hash") != digest or manifest.get("upstream") != upstream:
        return False
    files = manifest.get("files", {})
    return bool(files) and all((directory / f["file"]).exists() for f in files.values())


def materialise_model_ready(
    cfg: Any,
    *,
    force: bool = False,
    demand: pd.DataFrame | None = None,
    weather: pd.DataFrame | None = None,
    carbon: pd.DataFrame | None = None,
) -> ModelReadyDataset:
    """Write (or reuse) one feature-complete, split-labelled artefact per neighbourhood.

    Reuses the existing artefacts unless ``force`` is set, or the config hash
    or an upstream fingerprint differs from the manifest, or a file is
    missing. ``demand`` / ``weather`` / ``carbon`` default to the processed
    and cached tables.
    """
    directory = getattr(cfg.paths, "model_ready_dir", cfg.paths.processed_dir / SUBDIR)
    directory.mkdir(parents=True, exist_ok=True)
    digest = config_hash(cfg)
    upstream = upstream_fingerprints(cfg)
    manifest = _read_manifest(directory)

    if not force and _is_current(manifest, digest, upstream, directory):
        files = {nid: directory / f["file"] for nid, f in manifest["files"].items()}
        log.info("model-ready dataset is current (config %s); reusing %s artefacts", digest, len(files))
        return ModelReadyDataset(directory, digest, files, manifest, rebuilt=False)

    reason = "forced" if force else ("no manifest" if manifest is None else "config or upstream data changed")
    log.info("materialising model-ready dataset (config %s): %s", digest, reason)

    if demand is None:
        from drg.data.lcl_loader import build_neighbourhood_demand

        demand = build_neighbourhood_demand(cfg)
    if weather is None:
        weather = pd.read_parquet(cfg.paths.weather) if cfg.paths.weather.exists() else pd.DataFrame()
    if carbon is None:
        carbon = pd.read_parquet(cfg.paths.carbon) if cfg.paths.carbon.exists() else pd.DataFrame()

    table = build_feature_table(demand, cfg, weather=weather, carbon=carbon)
    test_days = float(cfg.models.get("test_size_days", 60))
    val_days = float(cfg.models.get("val_size_days", 30))
    table[SPLIT_COL] = assign_split(table, test_days=test_days, val_days=val_days)
    bounds = split_boundaries(table["timestamp"], test_days, val_days)

    for old in directory.glob("model_ready_*.parquet"):
        old.unlink()

    files: dict[str, Path] = {}
    entries: dict[str, Any] = {}
    for nid, sub in table.groupby("neighbourhood_id", observed=True, sort=True):
        path = _site_file(directory, str(nid), digest)
        sub.reset_index(drop=True).to_parquet(path, index=False)
        files[str(nid)] = path
        entries[str(nid)] = {
            "file": path.name,
            "rows": int(len(sub)),
            "split_rows": {s: int((sub[SPLIT_COL] == s).sum()) for s in SPLITS},
            "start": str(sub["timestamp"].min()),
            "end": str(sub["timestamp"].max()),
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "config_hash": digest,
        "config": dataset_config(cfg),
        "upstream": upstream,
        "created_utc": str(pd.Timestamp.now(tz="UTC")),
        "split": {
            "column": SPLIT_COL,
            "test_days": test_days,
            "val_days": val_days,
            "val_start": str(bounds["val_start"]),
            "test_start": str(bounds["test_start"]),
            "end": str(bounds["end"]),
        },
        "target": "target",
        "feature_columns": feature_columns(table),
        "files": entries,
    }
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    log.info("wrote %s model-ready artefacts -> %s", len(files), directory)
    return ModelReadyDataset(directory, digest, files, manifest, rebuilt=True)


def load_model_ready(cfg: Any, *, force: bool = False) -> pd.DataFrame:
    """The full model-ready table, materialising it first if it is stale."""
    return materialise_model_ready(cfg, force=force).load()
