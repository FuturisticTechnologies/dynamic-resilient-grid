"""Low Carbon London (UK Data Service study 7857) ingestion.

The published half-hourly release is a set of very large CSVs with the
columns ``LCLid, stdorToU, DateTime, KWH/hh (per half hour)``. They are read
in chunks so the pipeline runs inside the 8 GB RAM stated in the proposal
system requirements; households are folded into fixed-size low-voltage
"neighbourhood" groups (4 x ~120 by default) ordered by a stable hash of the
meter id, and each chunk is aggregated immediately so peak memory stays
proportional to the chunk, not to the dataset. The number of households that
reported in every half-hour is kept alongside the total (DRG-29).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
import pandas as pd

from drg.config import Config
from drg.data.aggregation import (
    aggregate_household_reads,
    assign_neighbourhoods,
    combine_partial_aggregates,
    finalise_neighbourhood_demand,
    registered_counts,
)
from drg.data.synthetic import generate_synthetic_neighbourhoods
from drg.utils.io import write_table
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------
def discover_lcl_files(cfg: Config) -> list[Path]:
    """Return every candidate raw LCL CSV, sorted for deterministic runs."""
    pattern = cfg.data.get("lcl_glob", "data/raw/**/*.csv")
    root = cfg.paths.root
    if Path(pattern).is_absolute():
        base = Path(pattern)
        files = sorted(base.parent.glob(base.name))
    else:
        files = sorted(root.glob(pattern))
    return [f for f in files if f.is_file() and f.stat().st_size > 0]


def _stable_group(meter_id: str, n_groups: int) -> int:
    digest = hashlib.blake2b(str(meter_id).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % n_groups


def _resolve_columns(columns: Iterable[str], mapping: dict[str, str]) -> dict[str, str]:
    """Match configured column names case/whitespace-insensitively."""
    norm = {str(c).strip().lower(): c for c in columns}
    resolved: dict[str, str] = {}
    for canonical, configured in mapping.items():
        key = str(configured).strip().lower()
        if key in norm:
            resolved[canonical] = norm[key]
            continue
        # tolerate the several published spellings of the energy column
        if canonical == "energy_kwh":
            for candidate in norm:
                if "kwh" in candidate:
                    resolved[canonical] = norm[candidate]
                    break
        elif canonical == "timestamp":
            for candidate in norm:
                if "date" in candidate or "time" in candidate:
                    resolved[canonical] = norm[candidate]
                    break
        elif canonical == "household_id":
            for candidate in norm:
                if "id" in candidate:
                    resolved[canonical] = norm[candidate]
                    break
    return resolved


# --------------------------------------------------------------------------
# chunked load + aggregation
# --------------------------------------------------------------------------
def _iter_chunks(path: Path, chunk_size: int) -> Iterator[pd.DataFrame]:
    yield from pd.read_csv(
        path,
        chunksize=chunk_size,
        low_memory=False,
        on_bad_lines="skip",
    )


def _normalise_chunk(chunk: pd.DataFrame, cols: dict[str, str]) -> pd.DataFrame:
    df = chunk[[cols["household_id"], cols["timestamp"], cols["energy_kwh"]]].copy()
    df.columns = ["household_id", "timestamp", "demand_kwh"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    df["demand_kwh"] = pd.to_numeric(df["demand_kwh"], errors="coerce")
    return df.dropna(subset=["timestamp", "household_id", "demand_kwh"])


def _scan_household_ids(files: list[Path], mapping: dict[str, str], chunk_size: int) -> set[str]:
    """First pass: collect meter ids only, so membership can be fixed up front."""
    ids: set[str] = set()
    for path in files:
        header = pd.read_csv(path, nrows=0)
        cols = _resolve_columns(header.columns, mapping)
        if "household_id" not in cols:
            log.warning("skipping %s: cannot resolve the household id column", path.name)
            continue
        for chunk in pd.read_csv(
            path, usecols=[cols["household_id"]], chunksize=chunk_size, on_bad_lines="skip"
        ):
            ids.update(chunk[cols["household_id"]].dropna().astype(str).unique().tolist())
    return ids


def load_lcl_halfhourly(cfg: Config, files: list[Path] | None = None) -> pd.DataFrame:
    """Aggregate raw LCL meter readings into neighbourhood half-hourly demand.

    Households are assigned to ``n_neighbourhoods`` fixed-size groups of
    ``households_per_neighbourhood`` meters (see
    :func:`drg.data.aggregation.assign_neighbourhoods`). Returns the columns in
    :data:`drg.data.aggregation.AGGREGATE_COLUMNS`, including the number of
    households that actually reported in each half-hour.
    """
    files = files if files is not None else discover_lcl_files(cfg)
    if not files:
        raise FileNotFoundError(
            "No Low Carbon London CSV files found. Place the study 7857 "
            f"half-hourly extract under {cfg.paths.raw_dir} or leave "
            "data.synthetic.enabled true to use the calibrated fallback."
        )

    n_groups = int(cfg.data.get("n_neighbourhoods", 4))
    per_group = int(cfg.data.get("households_per_neighbourhood", 120))
    min_cov = float(cfg.data.get("min_household_coverage", 0.5))
    mapping = cfg.data["column_map"]
    chunk_size = int(cfg.data.get("chunk_size", 1_000_000))

    membership = assign_neighbourhoods(_scan_household_ids(files, mapping, chunk_size), n_groups, per_group)
    log.info(
        "neighbourhood membership: %s",
        ", ".join(f"{k}={v}" for k, v in sorted(registered_counts(membership).items())),
    )

    parts: list[pd.DataFrame] = []
    total_rows = 0
    for path in files:
        log.info("reading %s (%.1f MB)", path.name, path.stat().st_size / 1e6)
        for chunk in _iter_chunks(path, chunk_size):
            cols = _resolve_columns(chunk.columns, mapping)
            missing = {"household_id", "timestamp", "energy_kwh"} - cols.keys()
            if missing:
                log.warning("skipping %s: cannot resolve columns %s", path.name, missing)
                break
            df = _normalise_chunk(chunk, cols)
            if df.empty:
                continue
            parts.append(aggregate_household_reads(df, membership))
            total_rows += len(df)

    partial = combine_partial_aggregates(parts)
    if partial.empty:
        raise ValueError("LCL files were found but no usable rows could be parsed.")

    out = finalise_neighbourhood_demand(partial, registered_counts(membership), min_cov)
    log.info(
        "aggregated %s raw readings -> %s neighbourhood rows",
        f"{total_rows:,}",
        f"{len(out):,}",
    )
    return out


# --------------------------------------------------------------------------
# cleaning
# --------------------------------------------------------------------------
def clean_demand(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Regularise the grid, repair short gaps, clip outliers, drop thin days.

    Half-hours masked for low household coverage arrive as NaN demand and are
    repaired or dropped exactly like missing readings. ``n_households`` keeps
    the count that actually reported (0 for a filled-in half-hour) and
    ``is_imputed`` flags rows whose demand was interpolated.
    """
    q = cfg.data.get("quality", {})
    max_gap = int(q.get("max_gap_periods", 6))
    z_thresh = float(q.get("outlier_z", 6.0))
    min_cov = float(q.get("min_coverage", 0.8))

    cleaned: list[pd.DataFrame] = []
    for nid, sub in df.groupby("neighbourhood_id", observed=True):
        sub = sub.sort_values("timestamp").drop_duplicates("timestamp")
        full = pd.date_range(sub["timestamp"].min(), sub["timestamp"].max(), freq="30min")
        sub = sub.set_index("timestamp").reindex(full)
        sub.index.name = "timestamp"
        sub["neighbourhood_id"] = nid
        # Household counts: a half-hour with no row had no meter reporting, so
        # its contributing count is 0; the registered size is a site property.
        if "n_households_registered" not in sub:
            sub["n_households_registered"] = sub["n_households"]
        sub["n_households_registered"] = sub["n_households_registered"].ffill().bfill()
        sub["n_households"] = sub["n_households"].fillna(0)
        if "demand_observed_kwh" in sub:
            sub["household_coverage"] = (
                sub["n_households"] / sub["n_households_registered"].replace(0, np.nan)
            ).fillna(0.0)

        series = sub["demand_kwh"]
        was_missing = series.isna()

        # robust outlier clip (median absolute deviation)
        med = series.median()
        mad = (series - med).abs().median()
        scale = 1.4826 * mad if mad > 0 else series.std(ddof=0)
        if scale and np.isfinite(scale) and scale > 0:
            upper = med + z_thresh * scale
            lower = max(0.0, med - z_thresh * scale)
            n_clipped = int(((series > upper) | (series < lower)).sum())
            series = series.clip(lower=lower, upper=upper)
            if n_clipped:
                log.debug("%s: clipped %s outliers", nid, n_clipped)

        # interpolate short gaps only; long gaps stay NaN and are dropped
        series = series.interpolate(method="time", limit=max_gap, limit_area="inside")
        sub["demand_kwh"] = series
        sub["is_imputed"] = was_missing & series.notna()
        if "demand_per_household_kwh" in sub:
            sub["demand_per_household_kwh"] = series / sub["n_households_registered"].replace(0, np.nan)

        # drop days with insufficient coverage
        sub["date"] = sub.index.date
        coverage = sub.groupby("date")["demand_kwh"].apply(lambda s: s.notna().mean())
        good_days = set(coverage[coverage >= min_cov].index)
        sub = sub[sub["date"].isin(good_days)].drop(columns="date")
        sub = sub.dropna(subset=["demand_kwh"])
        cleaned.append(sub.reset_index())

    out = pd.concat(cleaned, ignore_index=True)
    out["n_households"] = out["n_households"].astype(int)
    out["n_households_registered"] = out["n_households_registered"].astype(int)
    log.info(
        "cleaning: %s -> %s rows retained (%.1f%%)",
        f"{len(df):,}",
        f"{len(out):,}",
        100.0 * len(out) / max(len(df), 1),
    )
    return out.sort_values(["neighbourhood_id", "timestamp"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------
def _observed_temperature(cfg: Config, index: pd.DatetimeIndex) -> pd.Series | None:
    """Real ERA5 temperature for the study period, or None when offline."""
    try:
        from drg.data.external_apis import build_temperature_series

        frame = build_temperature_series(
            index,
            latitude=float(cfg.external["latitude"]),
            longitude=float(cfg.external["longitude"]),
            api_key=cfg.openweather_key,
            cache_dir=cfg.paths.external_dir,
            allow_network=True,
            seed=cfg.seed,
        )
        if frame.empty or frame["source"].iloc[0] == "synthetic":
            return None
        return pd.Series(frame["temperature_c"].to_numpy(), index=index)
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("could not fetch observed temperature for the fallback dataset: %s", exc)
        return None


def build_neighbourhood_demand(cfg: Config, force: bool = False) -> pd.DataFrame:
    """Produce (and cache) the processed neighbourhood demand table.

    Uses real Low Carbon London data when present, otherwise falls back to the
    calibrated synthetic generator so the whole framework is runnable offline.
    """
    target = cfg.paths.neighbourhood_demand
    if target.exists() and not force:
        log.info("using cached %s", target.name)
        return pd.read_parquet(target)

    try:
        raw = load_lcl_halfhourly(cfg)
        source = "low-carbon-london"
    except FileNotFoundError as exc:
        if not cfg.data.get("synthetic", {}).get("enabled", True):
            raise
        log.warning("%s", exc)
        log.warning("falling back to the calibrated synthetic generator")
        syn = cfg.data["synthetic"]
        index = pd.date_range(syn["start"], syn["end"], freq="30min", inclusive="left")
        raw = generate_synthetic_neighbourhoods(
            start=syn["start"],
            end=syn["end"],
            n_neighbourhoods=int(syn["n_neighbourhoods"]),
            households_per_neighbourhood=int(syn["households_per_neighbourhood"]),
            seed=cfg.seed,
            temperature=_observed_temperature(cfg, index),
            min_household_coverage=float(cfg.data.get("min_household_coverage", 0.5)),
        )
        source = "synthetic"

    keep_temp = "temperature_c" in raw.columns
    cleaned = clean_demand(raw[[c for c in raw.columns if c != "temperature_c"]], cfg)
    if keep_temp:
        cleaned = cleaned.merge(
            raw[["timestamp", "neighbourhood_id", "temperature_c"]],
            on=["timestamp", "neighbourhood_id"],
            how="left",
        )
    cleaned["source"] = source
    write_table(cleaned, target)
    log.info("wrote %s (%s rows, source=%s)", target, f"{len(cleaned):,}", source)
    return cleaned
