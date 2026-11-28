"""Train / validation / test window definition (DRG-57).

The windows are fixed once, from configuration, for the whole project:

* **train**      -- from the start of the usable series (the first row that
  survives the lag warm-up, or ``models.train_start`` when set) up to the
  validation window;
* **validation** -- ``models.val_size_days`` immediately before the test
  window, used only for early stopping and model / hyperparameter selection;
* **test**       -- the final ``models.test_size_days`` (60 by default) of the
  series, held out and untouched until final reporting.

Windows are half-open ``[start, end)`` intervals on the half-hourly grid, so a
60-day test window holds exactly 2,880 half-hours per neighbourhood and no
timestamp can fall into two windows. Every model in the harness is trained,
selected and reported on the *same* :class:`SplitWindows` instance; the
resolved dates are persisted so later stages (explainability, reporting)
reuse them instead of re-deriving their own.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

TRAIN, VALIDATION, TEST = "train", "validation", "test"
PERIOD = pd.Timedelta(minutes=30)


class WindowError(ValueError):
    """Raised when the series cannot support the configured windows."""


@dataclass(frozen=True)
class SplitWindows:
    """Chronological, non-overlapping, half-open windows."""

    train_start: pd.Timestamp
    val_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp  # exclusive: one period after the last reading

    def __post_init__(self) -> None:
        for name in ("train_start", "val_start", "test_start", "test_end"):
            object.__setattr__(self, name, pd.Timestamp(getattr(self, name)))
        if not (self.train_start < self.val_start <= self.test_start < self.test_end):
            raise WindowError(
                "windows must satisfy train_start < val_start <= test_start < test_end, got "
                f"{self.train_start} / {self.val_start} / {self.test_start} / {self.test_end}"
            )

    # ------------------------------------------------------------ geometry
    @property
    def train_end(self) -> pd.Timestamp:
        return self.val_start

    @property
    def val_end(self) -> pd.Timestamp:
        return self.test_start

    @property
    def test_days(self) -> float:
        return (self.test_end - self.test_start) / pd.Timedelta(days=1)

    @property
    def val_days(self) -> float:
        return (self.val_end - self.val_start) / pd.Timedelta(days=1)

    @property
    def train_days(self) -> float:
        return (self.train_end - self.train_start) / pd.Timedelta(days=1)

    # ------------------------------------------------------------ slicing
    def label(self, timestamps: pd.Series) -> pd.Series:
        """``train`` / ``validation`` / ``test`` per row; NaN outside all windows."""
        ts = pd.to_datetime(timestamps)
        out = pd.Series(pd.NA, index=ts.index, dtype="object")
        out[(ts >= self.train_start) & (ts < self.train_end)] = TRAIN
        out[(ts >= self.val_start) & (ts < self.val_end)] = VALIDATION
        out[(ts >= self.test_start) & (ts < self.test_end)] = TEST
        return out

    def split(
        self, df: pd.DataFrame, *, require_all: bool = True
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Slice ``df`` into (train, validation, test) copies."""
        labels = self.label(df["timestamp"])
        train = df[labels == TRAIN].copy()
        val = df[labels == VALIDATION].copy()
        test = df[labels == TEST].copy()
        if require_all:
            for name, part in ((TRAIN, train), (VALIDATION, val), (TEST, test)):
                if part.empty:
                    raise WindowError(f"the {name} window is empty for this frame ({self.describe()})")
        log.info(
            "split -> train %s | validation %s | test %s  [%s]",
            f"{len(train):,}",
            f"{len(val):,}",
            f"{len(test):,}",
            self.describe(),
        )
        return train, val, test

    def test_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rows of ``df`` inside the held-out test window."""
        ts = pd.to_datetime(df["timestamp"])
        return df[(ts >= self.test_start) & (ts < self.test_end)].copy()

    # ------------------------------------------------------------- io
    def describe(self) -> str:
        return (
            f"train {self.train_start:%Y-%m-%d %H:%M} -> {self.train_end:%Y-%m-%d %H:%M}, "
            f"validation -> {self.val_end:%Y-%m-%d %H:%M}, "
            f"test -> {self.test_end:%Y-%m-%d %H:%M}"
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {k: v.isoformat() for k, v in asdict(self).items()}
        out.update(
            train_end=self.train_end.isoformat(),
            val_end=self.val_end.isoformat(),
            train_days=round(self.train_days, 4),
            val_days=round(self.val_days, 4),
            test_days=round(self.test_days, 4),
        )
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SplitWindows:
        return cls(
            train_start=data["train_start"],
            val_start=data["val_start"],
            test_start=data["test_start"],
            test_end=data["test_end"],
        )

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> SplitWindows:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def define_windows(
    timestamps: pd.Series | pd.DatetimeIndex,
    *,
    test_days: float = 60,
    val_days: float = 30,
    train_start: str | pd.Timestamp | None = None,
    min_train_days: float = 0,
) -> SplitWindows:
    """Resolve concrete window dates from the end of the usable series.

    The test window is the final ``test_days`` ending one period after the last
    timestamp; validation is the ``val_days`` before it; training runs from
    ``train_start`` (default: the first usable timestamp) to the validation
    window.
    """
    ts = pd.to_datetime(pd.Series(timestamps)).dropna()
    if ts.empty:
        raise WindowError("cannot define windows on an empty series")
    if test_days <= 0 or val_days <= 0:
        raise WindowError("test_days and val_days must both be positive")

    first, last = ts.min(), ts.max()
    test_end = last + PERIOD
    test_start = test_end - pd.Timedelta(days=test_days)
    val_start = test_start - pd.Timedelta(days=val_days)
    start = pd.Timestamp(train_start) if train_start is not None else first
    start = max(start, first)

    if start >= val_start:
        raise WindowError(
            f"series {first} -> {last} is too short for {val_days} validation + {test_days} test days"
        )
    windows = SplitWindows(start, val_start, test_start, test_end)
    if windows.train_days < float(min_train_days):
        raise WindowError(
            f"training window is {windows.train_days:.1f} days, below models.min_train_days={min_train_days}"
        )
    return windows


def windows_from_config(cfg: Any, timestamps: pd.Series | pd.DatetimeIndex) -> SplitWindows:
    """The project windows, as configured under ``models``."""
    mcfg = cfg.models
    return define_windows(
        timestamps,
        test_days=float(mcfg.get("test_size_days", 60)),
        val_days=float(mcfg.get("val_size_days", 30)),
        train_start=mcfg.get("train_start"),
        min_train_days=float(mcfg.get("min_train_days", 0)),
    )
