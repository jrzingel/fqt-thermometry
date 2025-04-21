# -*- coding: utf-8 -*-
"""
Created on Sun Apr 20 13:45 2025

Alert for when the magnet is quenched.
This is when the temperature of the magnet rapidly rises from under 10K by 5K within 1 minute.

@author: james
"""

from typing import override
from .Alert import Alert


class MagnetQuench(Alert):
    def __init__(self, http, api_url, fridge):
        super().__init__(http, api_url, fridge)
        self.last_reading = None
        self.last_reading_time = None

    @override
    def is_in_alarm(self) -> bool:
        measurement = self._get_latest("magnet")

        if "reading" in measurement.keys():
            temp = measurement["reading"]
            time = measurement["time"]

            if self.last_reading_time is None:
                within_2_minutes = True
            else:
                within_2_minutes = (time - self.last_reading_time).total_seconds() < 2 * 60

            if self.last_reading is None:
                jump_by_5 = True
            else:
                jump_by_5 = (temp - self.last_reading) > 5.0

            # Save for next loop
            self.last_reading_time = time
            self.last_reading = temp

            if self.active and within_2_minutes and jump_by_5:
                self.activate()
                return True  # Warmed up too quickly (5K in 2 min)
            elif temp > 20:
                self.deactivate()
                return False
            else:
                return False  # Normal stuff
        else:
            return self.active  # Default to alarm if activated... otherwise the magnet may not be connected

    @override
    def try_enable(self):
        self.enable_if_below_threshold("magnet", 10.0)

    @override
    @property
    def description(self) -> str:
        return "Magnet temperature has risen far too quickly (Over 5K in under 2 min). The magnet has most likely quenched. Alarm disabled until magnet temperature is below 10K."

    @override
    @property
    def title(self) -> str:
        return "Magnet Quenched"
