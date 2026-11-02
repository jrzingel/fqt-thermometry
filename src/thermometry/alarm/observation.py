# -*- coding: utf-8 -*-
"""
One tick's worth of data for a single fridge.

The alarm system used to ask the web server for one sensor at a time, over HTTP, and could only
ever see the single most recent value. That is why `Critical` was written as an instantaneous
conjunction -- it had no way to express "the compressor stopped half an hour ago". An Observation
is fetched once per fridge per tick in a single query and carries a window of history, so
detectors can talk about trends, latches and the recent past.
"""

from datetime import datetime, timezone

import numpy as np


class Observation:
    """A window of recent readings for one fridge, plus the helpers detectors need to reason about it."""

    def __init__(self, fridge: str, window: dict, latest: dict, now: float = None):
        self.fridge = fridge
        self._window = window          # {sensor: [(unix_time, reading), ...]} oldest first
        self._latest = latest          # {sensor: (unix_time, reading)}
        self.now = now if now is not None else datetime.now(timezone.utc).timestamp()
        self.error = None              # set when the tick could not be fetched at all

    @classmethod
    def unavailable(cls, fridge: str, error: str):
        """An observation representing 'we could not read the database'. Never looks healthy."""
        obs = cls(fridge, {}, {})
        obs.error = error
        return obs

    # -- point values --------------------------------------------------------

    def latest(self, sensor: str):
        """Most recent reading, or None if the sensor has never reported."""
        entry = self._latest.get(sensor)
        if entry is None:
            series = self._window.get(sensor) or []
            if not series:
                return None
            return series[-1][1]
        return entry[1]

    def age(self, sensor: str):
        """Seconds since the sensor last reported, or None if it never has."""
        entry = self._latest.get(sensor)
        if entry is None:
            series = self._window.get(sensor) or []
            if not series:
                return None
            return self.now - series[-1][0]
        return self.now - entry[0]

    def has(self, *sensors) -> bool:
        """True only if every named sensor has a usable value."""
        return all(self.latest(s) is not None for s in sensors)

    # -- windows -------------------------------------------------------------

    def series(self, sensor: str, minutes: float) -> list:
        """The (time, reading) pairs for a sensor over the last `minutes`, oldest first."""
        cutoff = self.now - minutes * 60
        return [(t, v) for t, v in self._window.get(sensor, []) if t >= cutoff]

    def count(self, sensor: str, minutes: float) -> int:
        return len(self.series(sensor, minutes))

    def slope(self, sensor: str, minutes: float, min_points: int = 4):
        """Rate of change in units per minute over the window, or None if there is too little data.

        Uses a least-squares fit rather than a first/last difference so that a single noisy
        reading cannot by itself trigger or mask an alarm.
        """
        pts = self.series(sensor, minutes)
        if len(pts) < min_points:
            return None
        times = np.array([t for t, _ in pts], dtype=float)
        vals = np.array([v for _, v in pts], dtype=float)
        span = times[-1] - times[0]
        if span <= 0:
            return None
        times = (times - times[0]) / 60.0  # minutes, so the slope is per-minute
        return float(np.polyfit(times, vals, 1)[0])

    def median(self, sensor: str, minutes: float):
        pts = self.series(sensor, minutes)
        if not pts:
            return None
        return float(np.median([v for _, v in pts]))

    def maximum(self, sensor: str, minutes: float):
        pts = self.series(sensor, minutes)
        if not pts:
            return None
        return max(v for _, v in pts)

    def minimum(self, sensor: str, minutes: float):
        pts = self.series(sensor, minutes)
        if not pts:
            return None
        return min(v for _, v in pts)

    def was_above(self, sensor: str, threshold: float, minutes: float) -> bool:
        """Did this sensor read above `threshold` at any point in the window?

        This is the memory the old Critical alarm lacked: after a chiller outage trips the
        compressor the oil cools back below its threshold within minutes, but it *was* hot,
        and that fact is what matters.
        """
        peak = self.maximum(sensor, minutes)
        return peak is not None and peak > threshold

    def was_below(self, sensor: str, threshold: float, minutes: float) -> bool:
        trough = self.minimum(sensor, minutes)
        return trough is not None and trough < threshold

    def rose_by(self, sensor: str, delta: float, minutes: float):
        """How far the sensor rose from its minimum in the window to its latest value."""
        trough = self.minimum(sensor, minutes)
        current = self.latest(sensor)
        if trough is None or current is None:
            return False
        return (current - trough) >= delta

    # -- freshness -----------------------------------------------------------

    def data_age(self, sensors: list = None):
        """Seconds since the freshest of the named sensors reported. None if none ever have.

        Freshest rather than oldest on purpose: a single disconnected thermometer should not
        read as "this fridge has stopped reporting".
        """
        sensors = sensors if sensors is not None else list(self._latest.keys()) + list(self._window.keys())
        ages = [self.age(s) for s in sensors]
        ages = [a for a in ages if a is not None]
        if not ages:
            return None
        return min(ages)

    def is_stale(self, seconds: float, sensors: list = None) -> bool:
        """True if the fridge has not reported recently -- or has never reported at all."""
        if self.error is not None:
            return True
        age = self.data_age(sensors)
        return age is None or age > seconds
