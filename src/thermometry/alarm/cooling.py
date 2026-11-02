# -*- coding: utf-8 -*-
"""
Deciding whether a fridge has lost its cooling power, and whether that was on purpose.

The alarm this replaces asked whether the compressor oil was hot *and* the mixing chamber was
warm at the same instant. Those two things are never true together in the failure we actually
see: the chiller drops out, the oil spikes and trips the compressor, the oil then *cools*
because no work is being done, and the mixing chamber does not reach 1 K until half an hour
later. By then the oil is nowhere near 38 C and the conjunction can never be satisfied.

What matters is not a coincidence of two thresholds but a sequence: cooling power went away and
did not come back, and the fridge is warming as a result. That is a latch plus a trend, which is
what this module computes.

Everything here is a pure function of an Observation so it can be replayed offline against
historical data -- see `uv run backtest`.
"""

from collections import namedtuple


Verdict = namedtuple("Verdict", ["lost", "recovering", "reasons", "evidence"])
Warmup = namedtuple("Warmup", ["planned", "reasons"])


#: Tunables. Every one of these is a starting point to be checked against recorded incidents
#: with the backtest harness, not a measured constant.
DEFAULTS = {
    # What "cold" means
    "cold_4k": 5.0,             # K -- a healthy cold fridge sits at 3-4 K and never reaches this
    "recovered_4k": 4.5,        # K -- must fall back below this to count as recovered
    "arm_mxc": 0.2,             # K -- fridge counts as "was at base" below this
    "arm_lookback_min": 120,    # minutes to look back for evidence the fridge was cold
    "disarm_50k": 150.0,        # K -- above this the fridge is simply warm; nothing left to protect

    # Trends
    "trend_window_min": 15,     # minutes over which slopes are fitted
    "slope_4k": 0.01,           # K/min rise on the 4K plate
    "slope_50k": 0.2,           # K/min rise on the 50K plate

    # Compressor behaviour
    "oil_water_running": 12.0,  # K -- a working compressor holds oil this far above its water inlet
    "oil_water_stopped": 4.0,   # K -- once it stops, oil decays towards the water temperature
    "oil_water_lookback_min": 45,
    "oil_hot": 38.0,            # C -- the over-temperature threshold the compressor trips on
    "comp_current_running": 1.0,   # A -- motor current while compressing
    "comp_fault_states": [],    # cpastate values meaning "faulted". Left empty until the
                                # values are confirmed on a real fridge -- guessing an enum
                                # would produce confident nonsense.

    # Timers
    "confirm_min": 3,           # minutes the latch must hold before the interlock fires
    "recover_min": 10,          # minutes of good behaviour before the latch clears

    # Planned warm-up inference
    "warmup_lookback_min": 120,
    "p5_rise_mbar": 100.0,      # mixture tank rise that indicates the mixture was recovered
    "water_hot": 20.0,          # C -- above this the chiller is in trouble
}

#: Every sensor the cooling logic can consult.
SENSORS = (
    "4K", "50K", "mxc", "still", "P1", "P5",
    "pulse_on", "oil_temp", "water_in", "water_out",
    "comp_error", "comp_warn", "comp_state", "comp_current", "comp_dp", "comp_lp", "comp_hp",
    "flow", "turbo_speed", "turbo_on",
)


def _opt(options, name):
    return options.get(name, DEFAULTS[name])


# -- arming ------------------------------------------------------------------

def was_cold_recently(obs, options) -> bool:
    """Has this fridge been at base within the arming window?

    Without this an unused fridge sitting at room temperature would latch "cooling lost"
    forever, which is exactly what the old `should_disable` hack was groping towards.
    """
    lookback = _opt(options, "arm_lookback_min")
    if obs.was_below("4K", _opt(options, "cold_4k"), lookback):
        return True
    return obs.was_below("mxc", _opt(options, "arm_mxc"), lookback)


def is_fully_warm(obs, options) -> bool:
    """Is the fridge already warm enough that there is nothing left to protect?"""
    fifty = obs.latest("50K")
    return fifty is not None and fifty > _opt(options, "disarm_50k")


# -- the latch ---------------------------------------------------------------

def evaluate(obs, options) -> Verdict:
    """Decide whether cooling power is currently absent.

    A single decisive signal is enough; otherwise two independent corroborating signals are
    required, so no one noisy sensor can fire the interlock on its own.
    """
    decisive = []
    corroborating = []
    evidence = {}

    armed = was_cold_recently(obs, options)

    # -- decisive ------------------------------------------------------------

    # The compressor's own error word. This is the best signal available for this failure,
    # because it latches in the hardware: it is still set long after the oil has cooled.
    error = obs.latest("comp_error")
    if error is not None:
        evidence["comp_error"] = error
        if error != 0:
            decisive.append(f"compressor error word set ({error:.0f})")

    state = obs.latest("comp_state")
    if state is not None:
        evidence["comp_state"] = state
        fault_states = _opt(options, "comp_fault_states")
        if fault_states and state in fault_states:
            decisive.append(f"compressor in fault state ({state:.0f})")

    running = obs.latest("pulse_on")
    if running is not None:
        evidence["pulse_on"] = running
        if running == 0.0:
            decisive.append("compressor reports it is not running")

    four_k = obs.latest("4K")
    if four_k is not None:
        evidence["4K"] = four_k
        if armed and four_k > _opt(options, "cold_4k"):
            decisive.append(f"4K plate at {four_k:.2f} K")

    # -- corroborating -------------------------------------------------------

    window = _opt(options, "trend_window_min")

    slope_4k = obs.slope("4K", window)
    if slope_4k is not None:
        evidence["slope_4K"] = slope_4k
        if armed and slope_4k > _opt(options, "slope_4k"):
            corroborating.append(f"4K plate rising at {slope_4k * 1000:.0f} mK/min")

    slope_50k = obs.slope("50K", window)
    if slope_50k is not None:
        evidence["slope_50K"] = slope_50k
        if armed and slope_50k > _opt(options, "slope_50k"):
            corroborating.append(f"50K plate rising at {slope_50k:.2f} K/min")

    # A running compressor dumps its work into the cooling water and sits well above the inlet
    # temperature. Once it stops, that gap collapses -- and unlike the absolute oil temperature,
    # the collapse persists. This is the signal that survives step 3 of the incident.
    oil, water = obs.latest("oil_temp"), obs.latest("water_in")
    if oil is not None and water is not None:
        delta = oil - water
        evidence["oil_minus_water"] = delta
        was_working = obs.was_above("oil_temp", water + _opt(options, "oil_water_running"),
                                    _opt(options, "oil_water_lookback_min"))
        if delta < _opt(options, "oil_water_stopped") and was_working:
            corroborating.append(
                f"compressor oil has fallen to {delta:.1f} K above its water inlet after running warm")

    current = obs.latest("comp_current")
    if current is not None:
        evidence["comp_current"] = current
        if current < _opt(options, "comp_current_running") and obs.was_above(
                "comp_current", _opt(options, "comp_current_running"),
                _opt(options, "oil_water_lookback_min")):
            corroborating.append(f"compressor motor current dropped to {current:.1f} A")

    turbo_on = obs.latest("turbo_on")
    turbo_speed = obs.latest("turbo_speed")
    if turbo_on is not None and turbo_on == 0.0:
        evidence["turbo_on"] = turbo_on
        corroborating.append("turbo pump stopped")
    elif turbo_speed is not None and turbo_speed == 0.0:
        evidence["turbo_speed"] = turbo_speed
        corroborating.append("turbo pump at zero speed")

    flow = obs.latest("flow")
    if flow is not None:
        evidence["flow"] = flow
        if flow <= 0.0 and obs.was_above("flow", 0.0, _opt(options, "oil_water_lookback_min")):
            corroborating.append("mixture circulation stopped")

    reasons = decisive + corroborating
    lost = bool(decisive) or len(corroborating) >= 2

    # -- recovery ------------------------------------------------------------
    # Deliberately strict and one-sided: a brief chiller blip that the compressor rides out
    # clears this within minutes, while a trip that never restarts never does.
    recovering = (
        (running is None or running == 1.0)
        and (error is None or error == 0)
        and four_k is not None and four_k < _opt(options, "recovered_4k")
        and (slope_4k is None or slope_4k <= 0)
    )

    return Verdict(lost=lost, recovering=recovering, reasons=reasons, evidence=evidence)


# -- planned warm-up inference ----------------------------------------------

def _last_time_above(obs, sensor, threshold, minutes):
    """When the sensor was last seen above `threshold`, as a unix timestamp, or None."""
    latest = None
    for t, v in obs.series(sensor, minutes):
        if v > threshold:
            latest = t
    return latest


def looks_planned(obs, options) -> Warmup:
    """Was this warm-up deliberate?

    Answered only from positive evidence of an orderly shutdown. Absence of evidence means the
    warm-up is treated as accidental, because a missed accidental warm-up costs devices while a
    spurious alarm costs a measurement.
    """
    lookback = _opt(options, "warmup_lookback_min")
    reasons = []

    # 1. Was the mixture deliberately recovered? A planned warm-up pumps it back into the tank,
    #    which shows up as a large, sustained rise in P5. An accidental warm-up leaves the
    #    mixture in the circuit.
    if not obs.rose_by("P5", _opt(options, "p5_rise_mbar"), lookback):
        return Warmup(False, ["mixture tank pressure (P5) has not risen -- mixture is still in the circuit"])
    reasons.append("mixture tank pressure (P5) rose, so the mixture was recovered")

    # 2. Any sign of a fault means this was not planned, whatever else happened.
    if obs.was_above("water_in", _opt(options, "water_hot"), lookback):
        return Warmup(False, ["compressor cooling water went above its limit -- chiller fault"])
    if obs.was_above("oil_temp", _opt(options, "oil_hot"), lookback):
        return Warmup(False, ["compressor oil went over temperature"])
    if obs.was_above("comp_error", 0, lookback):
        return Warmup(False, ["compressor reported an error"])
    reasons.append("no compressor or chiller fault in the lead-up")

    # 3. Was the sequence orderly? Shutting a fridge down by hand stops circulation and the
    #    turbo before the compressor. A fault stops the compressor first, or everything at once.
    compressor_stopped = _last_time_above(obs, "pulse_on", 0.0, lookback)
    circulation_stopped = _last_time_above(obs, "flow", 0.0, lookback)
    if compressor_stopped is not None and circulation_stopped is not None:
        if circulation_stopped > compressor_stopped + 60:
            return Warmup(False, ["circulation was still running when the compressor stopped"])
        reasons.append("circulation stopped before the compressor, as in a manual shutdown")

    return Warmup(True, reasons)
