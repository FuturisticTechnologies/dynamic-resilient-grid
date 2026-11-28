"""Operator alarm handling for the replay (DRG-117).

A replay tick says whether *this* half-hour is stressed. An operator does not
want 48 identical messages for a four-hour event; they want an alarm that is
**raised** once, **escalated** if it gets worse, **acknowledged** by them and
**cleared** when the condition goes away -- the lifecycle a control-room
alarm list uses. :class:`AlarmManager` turns the tick stream into exactly
that.

Two alarm kinds:

* ``measured``    -- measured demand is at or above the stress threshold;
  its level follows the tick severity (``elevated`` / ``high`` /
  ``critical``);
* ``pre-emptive`` -- the one-step forecast breaches the threshold while the
  measurement does not yet. It is cleared when the forecast falls back, or
  superseded when the measured alarm is raised.

All times are *replay* (simulated) timestamps, never wall-clock time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MEASURED, PRE_EMPTIVE = "measured", "pre-emptive"
LEVELS = ("elevated", "high", "critical")
RANK = {level: i for i, level in enumerate(LEVELS, start=1)}

ACTIVE, ACKNOWLEDGED, CLEARED = "active", "acknowledged", "cleared"


@dataclass
class Alarm:
    id: int
    kind: str
    level: str
    neighbourhood_id: str
    raised_at: pd.Timestamp
    threshold_kwh: float
    peak_kwh: float
    state: str = ACTIVE
    last_seen: pd.Timestamp | None = None
    cleared_at: pd.Timestamp | None = None
    acknowledged_at: pd.Timestamp | None = None
    escalations: int = 0
    message: str = ""

    @property
    def is_open(self) -> bool:
        return self.state in (ACTIVE, ACKNOWLEDGED)

    @property
    def duration_h(self) -> float:
        """Hours the condition held: to the clearing tick, or through the last stressed one."""
        if self.cleared_at is not None:
            return float((self.cleared_at - self.raised_at) / pd.Timedelta(hours=1))
        end = self.last_seen or self.raised_at
        return float((end - self.raised_at) / pd.Timedelta(hours=1)) + 0.5

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in ("raised_at", "last_seen", "cleared_at", "acknowledged_at"):
            d[key] = None if d[key] is None else str(d[key])
        d["duration_h"] = self.duration_h
        return d


@dataclass
class AlarmEvent:
    timestamp: pd.Timestamp
    alarm_id: int
    action: str  # raised | escalated | acknowledged | cleared | superseded
    kind: str
    level: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = str(self.timestamp)
        return d


@dataclass
class AlarmManager:
    """Stateful alarm list fed one replay tick at a time."""

    clear_after: int = 1  # consecutive non-stressed ticks before a measured alarm clears
    alarms: list[Alarm] = field(default_factory=list)
    events: list[AlarmEvent] = field(default_factory=list)
    _calm: int = 0
    _next_id: int = 1

    # ------------------------------------------------------------- queries
    def open_alarm(self, kind: str) -> Alarm | None:
        return next((a for a in reversed(self.alarms) if a.kind == kind and a.is_open), None)

    def active(self) -> list[Alarm]:
        """Open alarms, most severe first."""
        open_ = [a for a in self.alarms if a.is_open]
        return sorted(open_, key=lambda a: (-RANK.get(a.level, 0), a.raised_at))

    def unacknowledged(self) -> list[Alarm]:
        return [a for a in self.alarms if a.state == ACTIVE]

    def alarms_frame(self) -> pd.DataFrame:
        return pd.DataFrame([a.to_dict() for a in self.alarms])

    def events_frame(self) -> pd.DataFrame:
        return pd.DataFrame([e.to_dict() for e in self.events])

    # ------------------------------------------------------------- actions
    def acknowledge(self, alarm_id: int, at: pd.Timestamp | None = None) -> bool:
        alarm = next((a for a in self.alarms if a.id == alarm_id), None)
        if alarm is None or alarm.state != ACTIVE:
            return False
        alarm.state = ACKNOWLEDGED
        alarm.acknowledged_at = pd.Timestamp(at) if at is not None else alarm.last_seen
        at_ts = alarm.acknowledged_at or alarm.raised_at
        self._emit(at_ts, alarm, "acknowledged", "acknowledged by operator")
        return True

    def acknowledge_all(self, at: pd.Timestamp | None = None) -> int:
        return sum(self.acknowledge(a.id, at) for a in list(self.unacknowledged()))

    def reset(self) -> None:
        self.alarms.clear()
        self.events.clear()
        self._calm = 0
        self._next_id = 1

    # -------------------------------------------------------------- update
    def update(self, tick: Any) -> list[AlarmEvent]:
        """Feed one :class:`~drg.streaming.replay.ReplayTick`; return new events."""
        start = len(self.events)
        ts = pd.Timestamp(tick.timestamp)
        threshold = float(tick.threshold_kwh)
        if not np.isfinite(threshold):
            return []

        # ----------------------------------------------- measured stress
        measured = self.open_alarm(MEASURED)
        if tick.is_stress and tick.severity in RANK:
            self._calm = 0
            if measured is None:
                pre = self.open_alarm(PRE_EMPTIVE)
                if pre is not None:
                    self._close(pre, ts, "superseded", "superseded by measured stress")
                self._raise(
                    MEASURED,
                    tick.severity,
                    tick,
                    ts,
                    f"Measured demand {tick.actual_kwh:,.1f} kWh at or above threshold "
                    f"{threshold:,.1f} kWh ({tick.severity})",
                    tick.actual_kwh,
                )
            else:
                measured.last_seen = ts
                measured.peak_kwh = max(measured.peak_kwh, float(tick.actual_kwh))
                if RANK[tick.severity] > RANK.get(measured.level, 0):
                    measured.level = tick.severity
                    measured.escalations += 1
                    measured.state = ACTIVE  # an escalation needs re-acknowledging
                    self._emit(
                        ts,
                        measured,
                        "escalated",
                        f"Escalated to {tick.severity}: {tick.actual_kwh:,.1f} kWh",
                    )
        elif measured is not None:
            self._calm += 1
            if self._calm >= self.clear_after:
                message = f"Demand back below threshold ({tick.actual_kwh:,.1f} kWh)"
                self._close(measured, ts, "cleared", message)

        # ------------------------------------------- pre-emptive forecast
        pre = self.open_alarm(PRE_EMPTIVE)
        forecast_only = bool(tick.forecast_is_stress) and self.open_alarm(MEASURED) is None
        if forecast_only and pre is None:
            self._raise(
                PRE_EMPTIVE,
                "elevated",
                tick,
                ts,
                f"Forecast {tick.forecast_next_kwh:,.1f} kWh for "
                f"{pd.Timestamp(tick.forecast_timestamp):%H:%M} breaches threshold {threshold:,.1f} kWh",
                tick.forecast_next_kwh,
            )
        elif pre is not None:
            if forecast_only:
                pre.last_seen = ts
                pre.peak_kwh = max(pre.peak_kwh, float(tick.forecast_next_kwh))
            elif not tick.forecast_is_stress:
                self._close(pre, ts, "cleared", "Forecast back below threshold")

        return self.events[start:]

    # ------------------------------------------------------------ internals
    def _raise(self, kind: str, level: str, tick: Any, ts: pd.Timestamp, message: str, value: float) -> Alarm:
        alarm = Alarm(
            id=self._next_id,
            kind=kind,
            level=level,
            neighbourhood_id=str(tick.neighbourhood_id),
            raised_at=ts,
            last_seen=ts,
            threshold_kwh=float(tick.threshold_kwh),
            peak_kwh=float(value),
            message=message,
        )
        self._next_id += 1
        self.alarms.append(alarm)
        self._emit(ts, alarm, "raised", message)
        return alarm

    def _close(self, alarm: Alarm, ts: pd.Timestamp, action: str, message: str) -> None:
        alarm.state = CLEARED
        alarm.cleared_at = ts
        self._emit(ts, alarm, action, message)

    def _emit(self, ts: pd.Timestamp, alarm: Alarm, action: str, message: str) -> None:
        self.events.append(AlarmEvent(pd.Timestamp(ts), alarm.id, action, alarm.kind, alarm.level, message))
