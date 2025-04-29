# -*- coding: utf-8 -*-
"""
Created on Sun Apr 20 13:44 2025

Alert for when the vacuum can pressure is lost

@author: james
"""

from typing import override
from .Alert import Alert

# From running this script it appears that sometimes there is a small pressure fluctuation
# so you really need it to be greater than threshold for two consecutive measurements

class LosingVacuum(Alert):
    def __init__(self, http, api_url, fridge):
        super().__init__(http, api_url, fridge)
        self.pre_alarm = False  # Used if the last state was alarm too

    @override
    def is_in_alarm(self) -> bool:
        measurement = self._get_latest("P1")
        # We have the reading, check if it is > 1e-5
        if "reading" in measurement.keys() and measurement["reading"] < 1.0e-5:
            self.pre_alarm = False
            return False

        if self.pre_alarm:  # Meaning that the last check was triggered too
            self.activate()
            return True  # Default to alarm state (also if no data exists)
        else:
            self.pre_alarm = True
            return False

    @override
    def try_enable(self):
        self.enable_if_below_threshold("P1", 8.0e-6)

    @override
    @property
    def description(self) -> str:
        return "Vacuum can pressure (P1) has increased over 1e-5 mBar. Fridge will begin to (or is already) warm soon. Alarm disabled until pressure P1 drops below 8e-6 mBar."

    @override
    @property
    def title(self) -> str:
        return "P1 (Vacuum can) pressure above 1e-5 mBar"
