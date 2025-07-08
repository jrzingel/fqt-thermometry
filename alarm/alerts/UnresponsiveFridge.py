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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_data_uploaded = None

    def update_data(self) -> dict:
        return {}

    def is_in_alarm(self) -> bool:
        sensors = ["P1", "P3", "50K", "4K"]
        for sensor in sensors:
            measurement = self._get_latest(sensor)
            if "time" in measurement.keys():
                reading_time = datetime.fromisoformat(measurement["time"])
                if reading_time + timedelta(minutes=5) > datetime.now(timezone.utc):
                    # Reading is fresh (no need to keep checking)
                    self.last_data_uploaded = reading_time
                    return False
        return True

    def should_enable(self):
        return self.if_cold()

    def should_disable(self):
        return False  # Never disable

    @property
    def description(self) -> str:
        return "There has been no new data uploaded in the past 5 minutes. Check that the thermometry software is running. Alarm disabled until issue resolved."

    @property
    def describe_condition(self):
        if self.last_data_uploaded is not None:
            return f"Last updated = {self.last_data_uploaded.astimezone().isoformat()} | Alarm if not in the last 5 minutes"
        return "Last updated = ? | Alarm if not in the last 5 minutes"

    @property
    def title(self) -> str:
        return "No new thermometry data for the past 5 minutes"
