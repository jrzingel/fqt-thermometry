# -*- coding: utf-8 -*-
"""
Created on Wed Jul 9 15:20 2025

Check if the fridge has encountered a critical alert meaning that the measurement should stop
immediately and the device be grounded.

Charizard watches for this alert and will halt any running programs if it is executed.

The original rule was `oil temperature > 38 C AND mixing chamber > 1 K`. Those two conditions
are anti-correlated in time and so almost never hold together: a chiller outage spikes the oil,
the compressor trips on over-temperature, and the oil then cools back down *because* it stopped.
The mixing chamber does not cross 1 K until half an hour or more later, by which point the oil
is cold again. The fridge warmed; the alarm never fired.

This now asks the question that actually matters -- has cooling power gone away, and is the
fridge warming as a result -- and it asks it in a way that remembers. The latch is set when the
compressor stops and is not cleared by the oil cooling down afterwards.

@author: james
"""

from .. import cooling
from .Alert import Alert


class Critical(Alert):
    sensors = cooling.SENSORS
    window_minutes = 120

    # Once this fires it stays fired. The old code did the opposite: `should_disable` returned
    # `mxc > 100 K`, so the interlock switched itself off precisely when the fridge was worst.
    latching = True

    # Losing sight of a fridge is itself interlock-relevant, so say so out loud.
    notify_on_unknown = True

    # If the service restarts in the middle of an incident, fire rather than wait it out
    arm_on_boot = True

    defaults = dict(cooling.DEFAULTS)

    def _verdict(self, obs):
        verdict = cooling.evaluate(obs, self.options)
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

        # Only protect a fridge that has something left to protect
        if not cooling.was_cold_recently(obs, self.options):
            return False
        if cooling.is_fully_warm(obs, self.options):
            return False

        held = self.latched_for("cooling_lost")
        if held is None or held < self.opt("confirm_min") * 60:
            return False

        # Confirm the fridge really is warming, not just that a sensor twitched
        slope = obs.slope("4K", self.opt("trend_window_min"))
        warming = (slope is not None and slope > 0) or (obs.latest("4K") or 0) > self.opt("cold_4k")
        if not warming:
            return False

        planned = cooling.looks_planned(obs, self.options)
        self.detail["planned_warmup"] = planned.planned
        self.detail["warmup_reasons"] = planned.reasons
        return not planned.planned

    def should_enable(self, obs) -> bool:
        return self.latched_for("cooling_lost") is None and cooling.was_cold_recently(obs, self.options)

    def should_disable(self, obs) -> bool:
        # Deliberately never disables on temperature. A warm fridge is the reason this exists.
        return False

    def alarm_reason(self, obs) -> str:
        return "; ".join(self.detail.get("cooling_lost_reasons", [])) or "cooling lost and fridge warming"

    @property
    def title(self) -> str:
        return "Fridge in critical condition"

    @property
    def description(self) -> str:
        reasons = self.detail.get("cooling_lost_reasons", [])
        detail = ("<br>".join(f"- {r}" for r in reasons)) if reasons else "No detail recorded."
        return (f"{self.fridge.capitalize()} has lost cooling power and is warming. Charizard will "
                f"halt any experiments and ground the device if the notebook is running. Urgent "
                f"action must be taken now to prevent a complete warm up. Evidence:<br>{detail}"
                f"<br><br>This alarm latches: acknowledge it on the alerts page once the fridge is safe.")

    @property
    def now_text(self) -> str:
        obs = self.obs
        bits = []
        running = obs.latest("pulse_on")
        if running is not None:
            bits.append(f"Compressor {'ON' if running else 'OFF'}")
        for sensor, fmt in (("4K", "{:.2f} K"), ("mxc", "{:.3f} K")):
            value = obs.latest(sensor)
            if value is not None:
                bits.append(f"{sensor} = " + fmt.format(value))
        slope = obs.slope("4K", self.opt("trend_window_min"))
        if slope is not None:
            bits.append(f"d4K/dt = {slope * 1000:+.0f} mK/min")
        return ", ".join(bits) if bits else "?"

    @property
    def condition_text(self) -> str:
        return (f"Alarm if cooling is lost for {self.opt('confirm_min')} min while the fridge is "
                f"cold and warming, or if data goes stale")
