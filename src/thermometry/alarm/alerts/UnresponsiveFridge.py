# -*- coding: utf-8 -*-
"""
Created on Sat Apr 19 22:34 2025

Alert for if there has been no new data from a fridge
(meaning the loggers or something is broken)

This is the one alert whose whole job is to notice missing data, so it opts out of the base
class's UNKNOWN handling and alarms on staleness directly.

@author: james
"""

from datetime import datetime, timezone, timedelta

from .Alert import Alert


class UnresponsiveFridge(Alert):
    sensors = ("P1", "P3", "50K", "4K", "mxc")

    # A fridge that is already silent when the service starts is exactly what this must report
    arm_on_boot = True

    defaults = {"stale_minutes": 5}

    def is_unavailable(self, obs) -> bool:
        return obs.error is not None  # Stale data is this alert's subject, not an obstacle to it

    def is_in_alarm(self, obs) -> bool:
        age = obs.data_age(list(self.sensors))
        self.detail["data_age_s"] = age
        return age is None or age > self.opt("stale_minutes") * 60

    def should_enable(self, obs) -> bool:
        return not self.is_in_alarm(obs)

    @property
    def title(self) -> str:
        return f"No new thermometry data for the past {self.opt('stale_minutes')} minutes"

    @property
    def description(self) -> str:
        return (f"There has been no new data uploaded in the past {self.opt('stale_minutes')} "
                f"minutes. Check that the thermometry software is running. Alarm disabled until "
                f"issue resolved.")

    @property
    def now_text(self) -> str:
        age = self.obs.data_age(list(self.sensors))
        if age is None:
            return "Last updated = never"
        seen = datetime.now(timezone.utc) - timedelta(seconds=age)
        return f"Last updated = {seen.astimezone().isoformat(timespec='seconds')}"

    @property
    def condition_text(self) -> str:
        return f"Alarm if not in the last {self.opt('stale_minutes')} minutes"
