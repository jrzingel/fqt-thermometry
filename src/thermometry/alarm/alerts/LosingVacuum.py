# -*- coding: utf-8 -*-
"""
Created on Sun Apr 20 13:44 2025

Alert for when the vacuum can pressure is lost

@author: james
"""

from .Alert import Alert
import numpy as np

# From running this script it appears that sometimes there is a small pressure fluctuation
# so you really need it to be greater than threshold for n consecutive measurements (on average)

class LosingVacuum(Alert):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = 8  # Number of points to average over. This is run every 30 seconds
        self.history = [np.nan] * self.n

    def update_data(self) -> dict:
        return {
            "P1": self._get_latest("P1")
        }

    def is_in_alarm(self) -> bool:
        # check if it is > 1e-5
        if "reading" in self.data["P1"].keys():
            # Add reading to array and shift them over
            self.history.pop(0)
            self.history.append(self.data["P1"]["reading"])

            avg = np.median(self.history)  # So high values are ignored

            if np.isnan(avg):
                # It hasn't been n minutes yet
                return False
            return avg > 7.0e-6
        return False

    def should_enable(self) -> bool:
        if self.if_below_threshold("P1", 6.5e-6):
            return True
        return False

    def should_disable(self) -> bool:
        return self.if_above_threshold("P1", 100.0e-6)

    @property
    def description(self) -> str:
        return "Vacuum can pressure (P1) average has increased over 7e-6 mBar over the last 4 minutes. Fridge will begin to (or is already) warm soon. Alarm disabled until pressure P1 drops below 6.5e-6 mBar."

    @property
    def describe_condition(self):
        if "reading" in self.data["P1"].keys():
            return f"P1 = {self.data['P1']['reading']} mBar | Alarm > 7e-6 mBar, Enabled < 6.5e-6 mBar"
        return ""

    @property
    def title(self) -> str:
        return "P1 (Vacuum can) pressure above 7e-6 mBar"
