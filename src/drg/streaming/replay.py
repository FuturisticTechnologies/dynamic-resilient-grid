"""Near-real-time streaming replay (proposal section 7.9).

Historical half-hourly demand is replayed as a simulated live feed. On every
tick the engine:

1. appends the newly "arrived" observation to a rolling window;
2. rebuilds features from that window and issues a fresh one-step-ahead
   forecast with the trained champion model;
3. compares both the observation and the forecast against the fixed
   statistical stress thresholds and raises an alert, including a
   *pre-emptive* alert when the forecast breaches the threshold before the
   measurement does;
4. optionally attaches the live weather / carbon-intensity context.

The engine is deliberately synchronous and pull-based so that the same code
drives the CLI demo, the Streamlit dashboard and the FastAPI service.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from drg.config import Config
from drg.features.engineering import (
    add_calendar_features,
    add_exogenous_features,
    add_lag_features,
)
from drg.models.registry import ModelBundle
from drg.stress.detection import StressThresholds
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)


@dataclass
class ReplayTick:
    timestamp: pd.Timestamp
    neighbourhood_id: str
    actual_kwh: float
    forecast_next_kwh: float
    forecast_timestamp: pd.Timestamp
    threshold_kwh: float
    is_stress: bool
    forecast_is_stress: bool
    severity: str
    headroom_kwh: float
    headroom_pct: float
    window: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "window"}
        d["timestamp"] = str(self.timestamp)
        d["forecast_timestamp"] = str(self.forecast_timestamp)
        return d


def _severity(ratio: float) -> str:
    if not np.isfinite(ratio):
        return "unknown"
    if ratio >= 1.25:
        return "critical"
    if ratio >= 1.10:
        return "high"
    if ratio >= 1.0:
        return "elevated"
    if ratio >= 0.9:
        return "watch"
    return "normal"


class StreamingReplayEngine:
    """Pull-based replay of a historical demand series with live forecasting."""

    def __init__(
        self,
        history: pd.DataFrame,
        bundle: ModelBundle,
        thresholds: dict[str, StressThresholds],
        cfg: Config,
        *,
        neighbourhood_id: str | None = None,
        start_index: int | None = None,
        carbon: pd.DataFrame | None = None,
    ) -> None:
        self.cfg = cfg
        self.bundle = bundle
        self.thresholds = thresholds
        self.window_periods = int(cfg.streaming.get("window_periods", 336))

        self.neighbourhood_id = neighbourhood_id or str(history["neighbourhood_id"].iloc[0])
        series = history[history["neighbourhood_id"] == self.neighbourhood_id]
        self.series = series.sort_values("timestamp").reset_index(drop=True)
        if len(self.series) < self.window_periods + 2:
            raise ValueError(
                f"Need at least {self.window_periods + 2} periods of history to replay; "
                f"got {len(self.series)}"
            )
        # start far enough in that all lags are warm
        self.cursor = int(start_index if start_index is not None else self.window_periods + 1)
        self._context: dict[str, Any] = {}

        # Reuse the cached carbon-intensity series so the online design matrix
        # matches the offline one exactly (no train/serve skew).
        self.carbon = carbon
        if self.carbon is None and cfg.paths.carbon.exists():
            try:
                self.carbon = pd.read_parquet(cfg.paths.carbon)
            except Exception as exc:  # pragma: no cover
                log.warning("could not load cached carbon intensity: %s", exc)

    # ------------------------------------------------------------------ API
    def __len__(self) -> int:
        return len(self.series)

    @property
    def exhausted(self) -> bool:
        return self.cursor >= len(self.series) - 1

    def reset(self, start_index: int | None = None) -> None:
        self.cursor = int(start_index if start_index is not None else self.window_periods + 1)

    def set_context(self, context: dict[str, Any]) -> None:
        """Attach the latest live weather / carbon snapshot to future ticks."""
        self._context = context or {}

    def tick(self) -> ReplayTick:
        """Advance one half-hour and return the resulting decision payload."""
        if self.exhausted:
            raise StopIteration("Replay series exhausted")

        idx = self.cursor
        window = self.series.iloc[max(0, idx - self.window_periods + 1) : idx + 1].copy()
        row = self.series.iloc[idx]
        actual = float(row["demand_kwh"])

        forecast, forecast_ts = self.forecast_next(window)

        th = self.thresholds.get(self.neighbourhood_id)
        threshold = float(th.primary_kwh) if th else float("nan")
        ratio = actual / threshold if threshold else float("nan")

        tick = ReplayTick(
            timestamp=pd.Timestamp(row["timestamp"]),
            neighbourhood_id=self.neighbourhood_id,
            actual_kwh=actual,
            forecast_next_kwh=float(forecast),
            forecast_timestamp=forecast_ts,
            threshold_kwh=threshold,
            is_stress=bool(actual >= threshold) if np.isfinite(threshold) else False,
            forecast_is_stress=bool(forecast >= threshold) if np.isfinite(threshold) else False,
            severity=_severity(ratio),
            headroom_kwh=float(threshold - actual) if np.isfinite(threshold) else float("nan"),
            headroom_pct=float(100.0 * (1.0 - ratio)) if np.isfinite(ratio) else float("nan"),
            window=window,
            context=self._context,
        )
        self.cursor += 1
        return tick

    def stream(self, n: int | None = None, delay_s: float = 0.0) -> Iterator[ReplayTick]:
        """Yield ticks, optionally throttled to a wall-clock cadence."""
        count = 0
        while not self.exhausted and (n is None or count < n):
            yield self.tick()
            count += 1
            if delay_s:
                time.sleep(delay_s)

    def run(self, n: int = 48, realtime: bool = False) -> pd.DataFrame:
        """Convenience: replay ``n`` ticks and return them as a frame."""
        speed = float(self.cfg.streaming.get("speed_factor", 240))
        delay = (1800.0 / speed) if realtime else 0.0
        rows = [t.to_dict() for t in self.stream(n=n, delay_s=delay)]
        frame = pd.DataFrame(rows)
        if "context" in frame.columns:
            # dict columns are not parquet-writable; keep them as JSON text
            if frame["context"].map(bool).any():
                frame["context"] = frame["context"].map(json.dumps)
            else:
                frame = frame.drop(columns="context")
        return frame

    # ------------------------------------------------------------ internals
    def forecast_next(self, window: pd.DataFrame) -> tuple[float, pd.Timestamp]:
        """One-step-ahead forecast built from the current rolling window."""
        next_ts = pd.Timestamp(window["timestamp"].iloc[-1]) + pd.Timedelta(minutes=30)
        future = window.iloc[[-1]].copy()
        future["timestamp"] = next_ts
        future["demand_kwh"] = np.nan

        frame = pd.concat([window, future], ignore_index=True)
        frame = add_calendar_features(frame)
        frame = add_lag_features(
            frame,
            lags=list(self.cfg.features.get("lags", [1, 2, 3, 48, 336])),
            rolling_windows=list(self.cfg.features.get("rolling_windows", [6, 48, 336])),
            target="demand_kwh",
            add_ramp=bool(self.cfg.features.get("add_ramp_rate", True)),
        )
        frame = add_exogenous_features(frame, None, self.carbon)

        cols = self.bundle.feature_columns
        design = frame.iloc[[-1]].reindex(columns=cols)
        for col in cols:
            if col not in frame.columns:
                design[col] = np.nan
        try:
            pred = float(np.ravel(self.bundle.predict(design))[0])
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("forecast failed at %s (%s); falling back to persistence", next_ts, exc)
            pred = float(window["demand_kwh"].iloc[-1])
        return max(pred, 0.0), next_ts


def replay_to_frame(engine: StreamingReplayEngine, n: int = 336) -> pd.DataFrame:
    """Run a full replay and return the alert log (used by the CLI/report)."""
    df = engine.run(n=n, realtime=False)
    if df.empty:
        return df
    df["alert"] = np.where(
        df["is_stress"],
        "STRESS",
        np.where(df["forecast_is_stress"], "PRE-EMPTIVE", "OK"),
    )
    return df
