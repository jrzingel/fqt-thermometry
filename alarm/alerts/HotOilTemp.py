# -*- coding: utf-8 -*-
"""
Created on Sat Apr 19 23:29 2025

Check if the compressor oil temperature is above a critical threshold
Usually this is a precursor to the compressor shutting down, the pulse tubes failing, and then the fridge heating up

@author: james
"""

from typing import override
from .Alert import Alert


# NORMAL < 35 < WARNING < 40 < ALARM

class HotOilTemp(Alert):
    @override
    def is_in_alarm(self) -> bool:
        measurement = self._get_latest("oil_temp")
        # We have the reading, check if it is > 1K
        if "reading" in measurement.keys() and measurement["reading"] < 40.0:
            return False
        self.activate()
        return True  # Default to alarm state (also if no data exists)

    @override
    def try_enable(self):
        self.enable_if_below_threshold("oil_temp", 35.0)

    @override
    @property
    def description(self) -> str:
        return "Compressor oil temperature is above 40C. The compressor will fail soon and action must be taken now. Alarm disabled until oil temperature is below 35 degrees."

    @override
    @property
    def title(self) -> str:
        return "Compressor oil temperature exceeds 40C"
