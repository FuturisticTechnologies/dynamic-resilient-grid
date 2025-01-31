"""Filesystem helpers.

All readers/writers go through here so that a local path can transparently be
swapped for an Azure Blob / ADLS Gen2 URI (``az://container/path``) when the
``adlfs`` extra is installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


def _is_remote(path: str | Path) -> bool:
    return str(path).startswith(("az://", "abfs://", "abfss://", "https://"))


def ensure_dir(path: str | Path) -> Path:
    """Create ``path`` (treated as a directory) and return it."""
    p = Path(path)
    if not _is_remote(path):
        p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_parent(path: str | Path) -> Path:
    p = Path(path)
    if not _is_remote(path):
        p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _storage_options() -> dict[str, Any]:
    """Credentials for remote object stores, resolved from the environment."""
    import os

    account = os.getenv("DRG_AZURE_STORAGE_ACCOUNT", "")
    if not account:
        return {}
    opts: dict[str, Any] = {"account_name": account}
    key = os.getenv("DRG_AZURE_STORAGE_KEY", "")
    if key:
        opts["account_key"] = key
    else:  # managed identity / az login
        opts["anon"] = False
    return opts


def write_table(df: pd.DataFrame, path: str | Path, *, index: bool = False) -> Path:
    """Write a DataFrame to parquet (preferred) or CSV based on suffix."""
    path = Path(path)
    ensure_parent(path)
    kwargs: dict[str, Any] = {}
    if _is_remote(path):
        kwargs["storage_options"] = _storage_options()
    if path.suffix in {".parquet", ".pq"}:
        df.to_parquet(path, index=index, **kwargs)
    elif path.suffix == ".csv":
        df.to_csv(path, index=index, **kwargs)
    elif path.suffix == ".json":
        df.to_json(path, orient="records", date_format="iso", **kwargs)
    else:
        raise ValueError(f"Unsupported table suffix: {path.suffix}")
    log.debug("wrote %s rows -> %s", len(df), path)
    return path


def read_table(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    path = Path(path)
    if _is_remote(path):
        kwargs.setdefault("storage_options", _storage_options())
    if path.suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path, **kwargs)
    if path.suffix == ".csv":
        return pd.read_csv(path, **kwargs)
    if path.suffix == ".json":
        return pd.read_json(path, **kwargs)
    raise ValueError(f"Unsupported table suffix: {path.suffix}")


def table_exists(path: str | Path) -> bool:
    return not _is_remote(path) and Path(path).exists()
