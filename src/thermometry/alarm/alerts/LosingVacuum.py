# -*- coding: utf-8 -*-
"""
Created on Sun Apr 20 13:44 2025

Alert for when the vacuum can pressure is lost

@author: james
"""

from .Alert import Alert

# From running this script it appears that sometimes there is a small pressure fluctuation
# so you really need it to be greater than threshold for n consecutive measurements (on average)


class LosingVacuum(Alert):
    sensors = ("P1",)

    defaults = {
        "alarm": 7.0e-6,
        "enable": 6.5e-6,
        "disable": 100.0e-6,
        "median_window_min": 4,   # the rolling median this used to keep in memory, as a query
    }

    def is_in_alarm(self, obs) -> bool:
        # Median over the window so a single pressure spike is ignored. This used to be an
        # in-memory ring buffer that reset to empty on every restart.
        median = obs.median("P1", self.opt("median_window_min"))
        return median is not None and median > self.opt("alarm")

    def should_enable(self, obs) -> bool:
        p1 = obs.latest("P1")
        return p1 is not None and p1 <= self.opt("enable")

    def should_disable(self, obs) -> bool:
        p1 = obs.latest("P1")
        return p1 is not None and p1 >= self.opt("disable")

    @property
    def title(self) -> str:
        return f"P1 (Vacuum can) pressure above {self.opt('alarm'):.0e} mBar"

    @property
    def description(self) -> str:
        return (f"Vacuum can pressure (P1) median has increased over {self.opt('alarm'):.0e} mBar "
                f"over the last {self.opt('median_window_min')} minutes. Fridge will begin to (or is "
                f"already) warm soon. Alarm disabled until pressure P1 drops below "
                f"{self.opt('enable'):.1e} mBar.")

    @property
    def now_text(self) -> str:
        p1 = self.obs.latest("P1")
        median = self.obs.median("P1", self.opt("median_window_min"))
        if p1 is None:
            return "?"
        if median is None:
            return f"P1 = {p1:.2e} mBar"
        return f"P1 = {p1:.2e} mBar (median {median:.2e})"

    @property
    def condition_text(self) -> str:
        return f"Alarm > {self.opt('alarm'):.0e} mBar, Enabled < {self.opt('enable'):.1e} mBar"
