"""Replay session: controls, speed and the replay clock (DRG-117).

:class:`ReplaySession` wraps a :class:`~drg.streaming.replay.StreamingReplayEngine`
and an :class:`~drg.streaming.alarms.AlarmManager` with the controls an
operator view needs -- play / pause, single step, reset, seek to a date and a
speed setting -- and keeps the tick history the page draws from.

Speed is a ratio of simulated time to wall-clock time, as in
``streaming.speed_factor``: at 240x one real second replays four simulated
minutes, so a half-hour period arrives every 7.5 s. :meth:`advance` converts
elapsed wall time into whole periods and carries the remainder, so the replay
clock keeps the configured pace whatever the page refresh interval is.

Everything here is clearly *replay*: the clock is the historical timestamp
being replayed, and :meth:`label` produces the banner text the page shows so a
replay of historical data cannot be mistaken for a live feed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from drg.streaming.alarms import AlarmEvent, AlarmManager
from drg.streaming.replay import ReplayTick, StreamingReplayEngine

PERIOD_S = 1800.0
SPEED_CHOICES: dict[str, float] = {
    "60x (1 min = 1 h)": 60.0,
    "240x (configured default)": 240.0,
    "720x (1 s = 12 min)": 720.0,
    "1800x (1 s = 30 min)": 1800.0,
    "7200x (1 s = 2 h)": 7200.0,
}
REPLAY_LABEL = "HISTORICAL REPLAY"


@dataclass
class ReplaySession:
    engine: StreamingReplayEngine
    speed: float = 240.0
    alarms: AlarmManager = field(default_factory=AlarmManager)
    playing: bool = False
    history_limit: int = 2016  # six weeks of half-hours kept for the page
    source: str = "historical data"
    ticks: list[ReplayTick] = field(default_factory=list)
    _carry: float = 0.0

    # ------------------------------------------------------------ controls
    def play(self) -> None:
        if not self.engine.exhausted:
            self.playing = True

    def pause(self) -> None:
        self.playing = False

    def toggle(self) -> bool:
        self.pause() if self.playing else self.play()
        return self.playing

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("replay speed must be positive")
        self.speed = float(speed)

    def reset(self, start_index: int | None = None) -> None:
        """Rewind to the start (or ``start_index``) and clear ticks and alarms."""
        self.engine.reset(start_index)
        self.ticks.clear()
        self.alarms.reset()
        self.playing = False
        self._carry = 0.0

    def seek(self, timestamp: pd.Timestamp | str) -> None:
        """Restart the replay at the first period at or after ``timestamp``."""
        ts = pd.Timestamp(timestamp)
        times = self.engine.series["timestamp"]
        idx = int(times.searchsorted(ts))
        lo = self.engine.window_periods + 1
        hi = len(self.engine.series) - 2
        self.reset(min(max(idx, lo), hi))

    def step(self, n: int = 1) -> list[AlarmEvent]:
        """Advance ``n`` half-hours; returns the alarm events they produced."""
        events: list[AlarmEvent] = []
        for _ in range(max(int(n), 0)):
            if self.engine.exhausted:
                self.playing = False
                break
            tick = self.engine.tick()
            self.ticks.append(tick)
            events.extend(self.alarms.update(tick))
        if len(self.ticks) > self.history_limit:
            del self.ticks[: len(self.ticks) - self.history_limit]
        return events

    def periods_for(self, elapsed_s: float) -> int:
        """Whole periods due after ``elapsed_s`` wall seconds at the current speed."""
        due = self._carry + max(float(elapsed_s), 0.0) * self.speed / PERIOD_S
        periods = int(due)
        self._carry = due - periods
        return periods

    def advance(self, elapsed_s: float, max_steps: int = 48) -> list[AlarmEvent]:
        """Advance by wall-clock time when playing (capped per refresh)."""
        if not self.playing:
            return []
        return self.step(min(self.periods_for(elapsed_s), max_steps))

    # -------------------------------------------------------------- state
    @property
    def clock(self) -> pd.Timestamp | None:
        """The historical timestamp the replay has reached."""
        return self.ticks[-1].timestamp if self.ticks else None

    @property
    def latest(self) -> ReplayTick | None:
        return self.ticks[-1] if self.ticks else None

    @property
    def progress(self) -> float:
        start = self.engine.window_periods + 1
        total = max(len(self.engine.series) - 1 - start, 1)
        return min(max((self.engine.cursor - start) / total, 0.0), 1.0)

    @property
    def period(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        """First and last timestamps available to replay."""
        times = self.engine.series["timestamp"]
        return pd.Timestamp(times.iloc[self.engine.window_periods + 1]), pd.Timestamp(times.iloc[-1])

    @property
    def seconds_per_period(self) -> float:
        return PERIOD_S / self.speed

    def ticks_frame(self) -> pd.DataFrame:
        if not self.ticks:
            return pd.DataFrame()
        frame = pd.DataFrame([t.to_dict() for t in self.ticks])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame["forecast_timestamp"] = pd.to_datetime(frame["forecast_timestamp"])
        return frame

    def label(self, include_tag: bool = True) -> str:
        """Banner text: states plainly that this is a replay, not a live feed."""
        start, end = self.period
        clock = f"{self.clock:%a %d %b %Y %H:%M}" if self.clock is not None else "not started"
        tag = f"{REPLAY_LABEL} - " if include_tag else ""
        return (
            f"{tag}Not a live feed. Replaying {self.source} for "
            f"{self.engine.neighbourhood_id} ({start:%d %b %Y} to {end:%d %b %Y}) at "
            f"{self.speed:,.0f}x speed. Replay clock: {clock}."
        )

    def status(self) -> dict[str, Any]:
        return {
            "mode": "replay",
            "label": REPLAY_LABEL,
            "neighbourhood_id": self.engine.neighbourhood_id,
            "clock": None if self.clock is None else str(self.clock),
            "playing": self.playing,
            "speed": self.speed,
            "progress": self.progress,
            "ticks": len(self.ticks),
            "open_alarms": len(self.alarms.active()),
            "unacknowledged_alarms": len(self.alarms.unacknowledged()),
            "exhausted": self.engine.exhausted,
        }
