# -*- coding: utf-8 -*-
"""
The fridge is warming, whatever the reason.

CoolingLost and Critical both reason about a specific mechanism -- the compressor stopped. This
one does not care why. It watches the mixing chamber and the 4K plate climb away from base and
says so, which is the net that catches the warm-ups nobody enumerated: a vacuum leak, lost
mixture, a heater left on, a blocked impedance.

Notification only; it never gates the interlock.

@author: james
"""

from .. import cooling
from .Alert import Alert


class FridgeWarming(Alert):
    sensors = ("4K", "50K", "mxc", "P1", "P5", "pulse_on", "flow", "oil_temp", "water_in", "comp_error")
    window_minutes = 120

    defaults = {
        "trend_window_min": 20,
        "slope_mxc": 0.002,     # K/min sustained rise of the mixing chamber
        "slope_4k": 0.01,       # K/min sustained rise of the 4K plate
        "base_mxc": 0.1,        # K -- only meaningful once the fridge was actually at base
        "rise_mxc": 0.05,       # K -- how far above its recent floor the MXC must have climbed
        "arm_lookback_min": 120,
        "arm_mxc": 0.2,
        "cold_4k": 5.0,
        "disarm_50k": 150.0,
        "warmup_lookback_min": 120,
        "p5_rise_mbar": 100.0,
        "water_hot": 20.0,
        "oil_hot": 38.0,
    }

    def is_in_alarm(self, obs) -> bool:
        if not cooling.was_cold_recently(obs, self.options):
            return False
        if cooling.is_fully_warm(obs, self.options):
            return False

        window = self.opt("trend_window_min")
        slope_mxc = obs.slope("mxc", window)
        slope_4k = obs.slope("4K", window)

        rising = (
            (slope_mxc is not None and slope_mxc > self.opt("slope_mxc")
             and obs.rose_by("mxc", self.opt("rise_mxc"), window))
            or (slope_4k is not None and slope_4k > self.opt("slope_4k"))
        )
        if not rising:
            return False

        planned = cooling.looks_planned(obs, self.options)
        self.detail["planned_warmup"] = planned.planned
        return not planned.planned

    def should_enable(self, obs) -> bool:
        mxc = obs.latest("mxc")
        return mxc is not None and mxc < self.opt("base_mxc")

    def should_disable(self, obs) -> bool:
        return cooling.is_fully_warm(obs, self.options)

    @property
    def title(self) -> str:
        return "Fridge is warming"

    @property
    def description(self) -> str:
        return (f"{self.fridge.capitalize()} is warming away from base and it does not look "
                f"deliberate. This alert does not assume a cause -- check the compressor, the "
                f"vacuum, the mixture and any heaters. Alarm re-arms once the mixing chamber is "
                f"back below {self.opt('base_mxc') * 1000:.0f} mK.")

    @property
    def now_text(self) -> str:
        obs = self.obs
        bits = []
        mxc = obs.latest("mxc")
        if mxc is not None:
            bits.append(f"MXC = {mxc * 1000:.1f} mK")
        slope = obs.slope("mxc", self.opt("trend_window_min"))
        if slope is not None:
            bits.append(f"dMXC/dt = {slope * 1000:+.1f} mK/min")
        four_k = obs.latest("4K")
        if four_k is not None:
            bits.append(f"4K = {four_k:.2f} K")
        return ", ".join(bits) if bits else "?"

    @property
    def condition_text(self) -> str:
        return (f"Alarm if MXC rises faster than {self.opt('slope_mxc') * 1000:.0f} mK/min "
                f"over {self.opt('trend_window_min')} min")
