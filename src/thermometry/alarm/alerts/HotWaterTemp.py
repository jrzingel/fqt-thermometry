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
    sensors = ("water_in",)

    defaults = {"alarm": 20.0, "enable": 19.0}

    def is_in_alarm(self, obs) -> bool:
        water = obs.latest("water_in")
        return water is not None and water > self.opt("alarm")

    def should_enable(self, obs) -> bool:
        water = obs.latest("water_in")
        return water is not None and water <= self.opt("enable")

    @property
    def title(self) -> str:
        return f"Input compressor water temperature exceeds {self.opt('alarm'):.0f}C"

    @property
    def description(self) -> str:
        return (f"Compressor input water temperature is above {self.opt('alarm'):.0f}C. The roof "
                f"chiller has likely failed and so the compressor will too if it is on. Alarm "
                f"disabled until input water temperature is below {self.opt('enable'):.0f}C.")

    @property
    def now_text(self) -> str:
        water = self.obs.latest("water_in")
        return f"Input water temp = {water:.1f} C" if water is not None else "?"

    @property
    def condition_text(self) -> str:
        return f"Alarm > {self.opt('alarm'):.0f}C, {self.opt('enable'):.0f}C > Enabled"
