# -*- coding: utf-8 -*-
"""
Created on Sat Apr 19 23:29 2025

Check if the compressor oil temperature is above a critical threshold
Usually this is a precursor to the compressor shutting down, the pulse tubes failing, and then the fridge heating up

@author: james
"""

from .Alert import Alert


# NORMAL < 35 < WARNING < 38 < ALARM

class HotOilTemp(Alert):
    def update_data(self):
        return {
            "oil_temp": self._get_latest("oil_temp")
        }

    def is_in_alarm(self) -> bool:
        # We have the reading, check if it is > 38C
        if "reading" in self.data["oil_temp"].keys():
            return self.data["oil_temp"]["reading"] > 38.0
        return True  # Default to alarm state (also if no data exists)

    def should_enable(self):
        return self.enable_if_below_threshold("oil_temp", 35.0)

    @property
    def description(self) -> str:
        return "Compressor oil temperature is above 38C. The compressor will likely fail soon (at 50C) and action must be taken now. The compressor will then re-enable at 40C. Alarm disabled until oil temperature is below 35C."

    @property
    def describe_condition(self) -> str:
        if "reading" in self.data["oil_temp"].keys():
            return f"Oil temp = {self.data['oil_temp']['reading']:.1f} C | Alarm > 38C, 35C > Enabled"
        return ""

    @property
    def title(self) -> str:
        return "Compressor oil temperature exceeds 38C"
