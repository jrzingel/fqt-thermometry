# -*- coding: utf-8 -*-
"""
Created on Sat Apr 19 23:29 2025

Check if the compressor oil temperature is above a critical threshold
Usually this is a precursor to the compressor shutting down, the pulse tubes failing, and then the fridge heating up

Note this only catches the fridge on the way in to the fault. Once the compressor trips the oil
cools back down and this alert goes quiet -- CoolingLost and Critical are what stay set.

@author: james
"""

from .Alert import Alert


# NORMAL < 35 < WARNING < 38 < ALARM

class HotOilTemp(Alert):
    sensors = ("oil_temp",)

    defaults = {"alarm": 38.0, "enable": 35.0}

    def is_in_alarm(self, obs) -> bool:
        oil = obs.latest("oil_temp")
        return oil is not None and oil > self.opt("alarm")

    def should_enable(self, obs) -> bool:
        oil = obs.latest("oil_temp")
        return oil is not None and oil <= self.opt("enable")

    @property
    def title(self) -> str:
        return f"Compressor oil temperature exceeds {self.opt('alarm'):.0f}C"

    @property
    def description(self) -> str:
        return (f"Compressor oil temperature is above {self.opt('alarm'):.0f}C. The compressor will "
                f"likely fail soon (at 50C) and action must be taken now. The compressor will then "
                f"re-enable at 40C. Alarm disabled until oil temperature is below {self.opt('enable'):.0f}C.")

    @property
    def now_text(self) -> str:
        oil = self.obs.latest("oil_temp")
        return f"Oil temp = {oil:.1f} C" if oil is not None else "?"

    @property
    def condition_text(self) -> str:
        return f"Alarm > {self.opt('alarm'):.0f}C, {self.opt('enable'):.0f}C > Enabled"
