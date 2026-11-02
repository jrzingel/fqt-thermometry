# -*- coding: utf-8 -*-
"""
The fridge has stopped being cooled.

This is the early warning to people: the pulse tubes have stopped and nothing is bringing them
back. It fires as soon as the loss is confirmed, typically half an hour or more before the
mixing chamber is anywhere near 1 K, so there is time to restart the compressor before the
fridge is lost.

It does not gate the experimental interlock -- see Critical for that.

@author: james
"""

from .. import cooling
from .Alert import Alert


class CoolingLost(Alert):
    sensors = cooling.SENSORS
    window_minutes = 120
    arm_on_boot = True
    defaults = dict(cooling.DEFAULTS)

    def _verdict(self, obs):
        verdict = cooling.evaluate(obs, self.options)

        # Hold the latch across the oil cooling back down, and require a sustained recovery
        # before letting it go. A chiller blip the compressor rides out clears in minutes.
        if verdict.lost:
            self.detail.pop("recovering_since", None)
            self.latch("cooling_lost", True, reasons=verdict.reasons)
        elif verdict.recovering:
            held = self.latch("recovering", True)
            if held is not None and held >= self.opt("recover_min") * 60:
                self.latch("cooling_lost", False)
                self.latch("recovering", False)
        else:
            self.latch("recovering", False)

        self.detail["evidence"] = verdict.evidence
        return verdict

    def is_in_alarm(self, obs) -> bool:
        self._verdict(obs)
        held = self.latched_for("cooling_lost")
        if held is None or held < self.opt("confirm_min") * 60:
            return False
        if not cooling.was_cold_recently(obs, self.options):
            return False
        if cooling.is_fully_warm(obs, self.options):
            return False

        planned = cooling.looks_planned(obs, self.options)
        self.detail["planned_warmup"] = planned.planned
        self.detail["warmup_reasons"] = planned.reasons
        return not planned.planned

    def should_enable(self, obs) -> bool:
        return self.latched_for("cooling_lost") is None and cooling.was_cold_recently(obs, self.options)

    def should_disable(self, obs) -> bool:
        return cooling.is_fully_warm(obs, self.options)

    def alarm_reason(self, obs) -> str:
        return "; ".join(self.detail.get("cooling_lost_reasons", [])) or "cooling power lost"

    @property
    def title(self) -> str:
        return "Fridge has lost cooling power"

    @property
    def description(self) -> str:
        reasons = self.detail.get("cooling_lost_reasons", [])
        detail = ("<br>".join(f"- {r}" for r in reasons)) if reasons else "No detail recorded."
        return (f"{self.fridge.capitalize()} is no longer being cooled and this does not look "
                f"deliberate. The fridge will warm from here unless the compressor is restarted. "
                f"Evidence:<br>{detail}")

    @property
    def now_text(self) -> str:
        obs = self.obs
        bits = []
        running = obs.latest("pulse_on")
        if running is not None:
            bits.append(f"Compressor {'ON' if running else 'OFF'}")
        four_k = obs.latest("4K")
        if four_k is not None:
            bits.append(f"4K = {four_k:.2f} K")
        slope = obs.slope("4K", self.opt("trend_window_min"))
        if slope is not None:
            bits.append(f"d4K/dt = {slope * 1000:+.0f} mK/min")
        held = self.latched_for("cooling_lost")
        if held is not None:
            bits.append(f"lost for {held / 60:.0f} min")
        return ", ".join(bits) if bits else "?"

    @property
    def condition_text(self) -> str:
        return (f"Alarm if cooling is lost for {self.opt('confirm_min')} min and the warm-up "
                f"does not look planned")
