# -*- coding: utf-8 -*-
"""
Created on Sat Apr 19 22:34 2025

Alert for if there has been no new data from a fridge
(meaning the loggers or something is broken)

@author: james
"""

from datetime import datetime, timezone, timedelta
from .Alert import Alert


class UnresponsiveFridge(Alert):
    def __init__(self, http, api_url, fridge):
        super().__init__(http, api_url, fridge)
        self.time_last_seen = datetime.now(timezone.utc)

    def is_in_alarm(self) -> bool:
        sensors = ["P1", "P3", "50K", "4K"]
        for sensor in sensors:
            measurement = self._get_latest(sensor)
            if "time" in measurement.keys():
                reading_time = datetime.fromisoformat(measurement["time"])
                if reading_time + timedelta(minutes=5) > self.time_last_seen:
                    # Reading is fresh (no need to keep checking)
                    return False
        self.activate()
        return True

    def try_enable(self):
        self.enable_if_cold()

    @property
    def description(self) -> str:
        return "There has been no new data uploaded in the past 5 minutes. Check that the thermometry software is running. Alarm disabled until issue resolved."

    @property
    def title(self) -> str:
        return "No new thermometry data for the past 5 minutes"
