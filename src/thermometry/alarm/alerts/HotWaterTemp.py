# -*- coding: utf-8 -*-
"""
Created on Sat Apr 19 23:29 2025

Check if the compressor input water temperature is above a critical threshold
Usually this is a precursor to the compressor shutting down, the pulse tubes failing, and then the fridge heating up
If it does it isn't out fault :|

@author: james
"""

from .Alert import Alert


# Enabled < 19,  20 < ALARM

class HotWaterTemp(Alert):
    def update_data(self):
        return {
            "water_temp": self._get_latest("water_in")
        }

    def is_in_alarm(self) -> bool:
        # We have the reading, check if it is > 38C
        if "reading" in self.data["water_temp"].keys():
            return self.data["water_temp"]["reading"] > 20.0
        return True  # Default to alarm state (also if no data exists)

    def should_enable(self):
        return self.if_below_threshold("water_temp", 19.0)

    def should_disable(self) -> bool:
        return False  # Never disable if active

    @property
    def description(self) -> str:
        return "Compressor input water temperature is above 20C. The roof chiller has likely failed and so the compressor will too if it is on. Alarm disabled until input water temperature is below 19C."

    @property
    def describe_condition(self) -> str:
        if "reading" in self.data["water_temp"].keys():
            return f"Input water temp = {self.data['water_temp']['reading']:.1f} C | Alarm > 20C, 19C > Enabled"
        return ""

    @property
    def title(self) -> str:
        return "Input compressor water temperature exceeds 20C"
