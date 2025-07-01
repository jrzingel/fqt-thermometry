# -*- coding: utf-8 -*-
"""
Created on Sun Apr 20 13:44 2025

Alert for when the vacuum can pressure is lost

@author: james
"""

from .Alert import Alert

# From running this script it appears that sometimes there is a small pressure fluctuation
# so you really need it to be greater than threshold for two consecutive measurements

class LosingVacuum(Alert):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pre_alarm = False  # Used if the last state was alarm too

    def update_data(self) -> dict:
        return {
            "P1": self._get_latest("P1")
        }

    def is_in_alarm(self) -> bool:
        # check if it is > 1e-5
        if "reading" in self.data["P1"].keys():
            if self.data["P1"]["reading"] > 10.0e-6:
                if self.pre_alarm:  # Meaning that the last check was triggered too
                    return True
                else:
                    self.pre_alarm = True
                    return False
            else:
                self.pre_alarm = False  # No longer in previous state of alarm
                return False
        return True  # Default to being in alarm

    def should_enable(self) -> bool:
        if self.if_below_threshold("P1", 8.0e-6):
            self.pre_alarm = False
            return True
        return False

    def should_disable(self) -> bool:
        return self.if_above_threshold("P1", 100.0e-6)

    @property
    def description(self) -> str:
        return "Vacuum can pressure (P1) has increased over 1e-5 mBar. Fridge will begin to (or is already) warm soon. Alarm disabled until pressure P1 drops below 8e-6 mBar."

    @property
    def describe_condition(self):
        if "reading" in self.data["P1"].keys():
            return f"P1 = {self.data['P1']['reading']} mBar | Alarm > 1e-5 mBar, Enabled < 8e-6 mBar"
        return ""

    @property
    def title(self) -> str:
        return "P1 (Vacuum can) pressure above 1e-5 mBar"
