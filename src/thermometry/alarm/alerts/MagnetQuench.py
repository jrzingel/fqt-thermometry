# -*- coding: utf-8 -*-
"""
Created on Sun Apr 20 13:45 2025

Alert for when the magnet is quenched.
This is when the temperature of the magnet rapidly rises from under 10K by 5K within 1 minute.

The previous version of this file could not run at all: it called self.active/activate()/
deactivate(), which were left over from an API that predated the State enum, and never
implemented update_data so it raised at construction. It is rebuilt here on the slope helper.

@author: james
"""

from .Alert import Alert


class MagnetQuench(Alert):
    sensors = ("magnet",)

    defaults = {
        "window_min": 2,     # the "within 2 minutes" of the original rule
        "rise": 5.0,         # K rise over that window that counts as a quench
        "enable": 10.0,      # K -- re-arm once the magnet is cold again
        "disable": 20.0,     # K -- above this it has already quenched or is being warmed
    }

    def is_in_alarm(self, obs) -> bool:
        window = self.opt("window_min")
        slope = obs.slope("magnet", window, min_points=3)
        if slope is None:
            return False
        # Expressed as a rate so an irregular logging interval cannot hide or fake a quench
        return slope * window > self.opt("rise")

    def should_enable(self, obs) -> bool:
        magnet = obs.latest("magnet")
        return magnet is not None and magnet <= self.opt("enable")

    def should_disable(self, obs) -> bool:
        magnet = obs.latest("magnet")
        return magnet is not None and magnet >= self.opt("disable")

    @property
    def title(self) -> str:
        return "Magnet Quenched"

    @property
    def description(self) -> str:
        return (f"Magnet temperature has risen far too quickly (Over {self.opt('rise'):.0f}K in "
                f"under {self.opt('window_min')} min). The magnet has most likely quenched. Alarm "
                f"disabled until magnet temperature is below {self.opt('enable'):.0f}K.")

    @property
    def now_text(self) -> str:
        magnet = self.obs.latest("magnet")
        if magnet is None:
            return "?"
        slope = self.obs.slope("magnet", self.opt("window_min"), min_points=3)
        if slope is None:
            return f"Magnet = {magnet:.2f} K"
        return f"Magnet = {magnet:.2f} K, rising {slope:+.2f} K/min"

    @property
    def condition_text(self) -> str:
        return f"Alarm if it rises over {self.opt('rise'):.0f}K in {self.opt('window_min')} min"
