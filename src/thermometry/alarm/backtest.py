# -*- coding: utf-8 -*-
"""
Replay alarm logic over recorded or synthetic data.

The thresholds in `cooling.py` are physics reasoning, not measurements. This harness is how
they get checked: feed a detector a window of real history from TimescaleDB and see when it
would have fired, or run the built-in synthetic incidents to check the logic end to end without
touching a database.

    uv run backtest --scenarios                                  # synthetic incidents
    uv run backtest --fridge queenie --from 2026-03-01 --to 2026-03-02
    uv run backtest --fridge queenie --from ... --to ... --alert CoolingLost

Each run reports every state transition, and for the critical alert it also reports whether the
*old* rule (oil > 38 C AND mxc > 1 K simultaneously) would have caught the same event. That
comparison is the point of the exercise.
"""

import argparse
import math
from datetime import datetime, timedelta, timezone

from thermometry.alarm.alerts import REGISTRY
from thermometry.alarm.observation import Observation


# -- replay ------------------------------------------------------------------

def observation_at(fridge: str, history: dict, at: float, window_minutes: float) -> Observation:
    """Build the Observation the alarm system would have seen at time `at`."""
    cutoff = at - window_minutes * 60
    window = {}
    latest = {}
    for sensor, points in history.items():
        kept = [(t, v) for t, v in points if cutoff <= t <= at]
        window[sensor] = kept
        recent = [(t, v) for t, v in points if t <= at]
        if recent:
            latest[sensor] = recent[-1]
    return Observation(fridge, window, latest, now=at)


def replay(fridge: str, history: dict, alert_type: str, options: dict = None,
           step: float = 30, start: float = None, end: float = None) -> list:
    """Step an alert through a trace, returning every transition as (unix_time, transition)."""
    cls = REGISTRY[alert_type]
    alert = cls(fridge, options or {})

    times = sorted({t for points in history.values() for t, _ in points})
    if not times:
        return []
    start = start if start is not None else times[0]
    end = end if end is not None else times[-1]

    events = []
    at = start
    while at <= end:
        obs = observation_at(fridge, history, at, alert.window_minutes)
        transition = alert.update(obs)
        if transition:
            events.append((at, transition))
        at += step
    return events


def old_critical_first_fire(history: dict, step: float = 30):
    """When the original rule would first have fired: oil > 38 C AND mxc > 1 K at the same instant."""
    times = sorted({t for points in history.values() for t, _ in points})
    if not times:
        return None
    at = times[0]
    while at <= times[-1]:
        obs = observation_at("x", history, at, 5)
        oil, mxc = obs.latest("oil_temp"), obs.latest("mxc")
        if oil is not None and mxc is not None and oil > 38 and mxc > 1.0:
            return at
        at += step
    return None


# -- synthetic incidents -----------------------------------------------------

def _ramp(value_from, value_to, fraction):
    return value_from + (value_to - value_from) * max(0.0, min(1.0, fraction))


def _decay(value_from, value_to, minutes, tau):
    return value_to + (value_from - value_to) * math.exp(-minutes / tau)


def chiller_outage(duration_min=180, trip_min=68, sample_s=60) -> dict:
    """The incident this rebuild exists for.

    A chiller outage drives the compressor oil over temperature; the compressor trips; the oil
    then *cools* because it stopped, falling back under 38 C within about seven minutes. The
    pulse tubes are off from that moment and the fridge warms, but the mixing chamber does not
    reach 1 K for roughly another fifty minutes -- long after the oil is cold again.
    """
    base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    history = {s: [] for s in (
        "4K", "50K", "mxc", "still", "P1", "P5", "pulse_on", "oil_temp",
        "water_in", "water_out", "comp_error", "comp_current", "flow", "turbo_speed", "turbo_on")}

    for i in range(0, duration_min * 60 // sample_s):
        m = i * sample_s / 60.0
        t = base + i * sample_s
        after_trip = m - trip_min

        if m < 60:                       # nominal
            water = 15.0
            oil = 30.0
        elif m < trip_min:               # chiller out, compressor cooking
            water = _ramp(15.0, 28.0, (m - 60) / 5.0)
            oil = _ramp(30.0, 52.0, (m - 60) / 8.0)
        else:                            # tripped: oil falls back towards the water temperature
            water = _decay(28.0, 19.0, after_trip, 25.0)
            oil = _decay(52.0, 21.0, after_trip, 9.0)

        running = 1.0 if m < trip_min else 0.0
        error = 0.0 if m < trip_min else 3.0
        current = 8.0 if m < trip_min else 0.0

        if m < trip_min:
            four_k, fifty_k, mxc = 3.5, 45.0, 0.020
            flow = 0.50
        else:
            four_k = 3.5 + 0.16 * after_trip
            fifty_k = 45.0 + 1.4 * after_trip
            # The mixing chamber lags badly -- it is the last thing to notice. Crosses 1 K
            # roughly 50 minutes after the trip, by which point the oil is long cold.
            mxc = 0.020 + 0.0004 * after_trip ** 2
            flow = max(0.0, 0.50 - 0.25 * after_trip)

        history["water_in"].append((t, water))
        history["water_out"].append((t, water + 3.0))
        history["oil_temp"].append((t, oil))
        history["pulse_on"].append((t, running))
        history["comp_error"].append((t, error))
        history["comp_current"].append((t, current))
        history["4K"].append((t, four_k))
        history["50K"].append((t, fifty_k))
        history["mxc"].append((t, min(mxc, 300.0)))
        history["still"].append((t, 0.8 if m < trip_min else 0.8 + 0.05 * after_trip))
        history["P1"].append((t, 2.0e-6))
        history["P5"].append((t, 10.0))
        history["flow"].append((t, flow))
        history["turbo_speed"].append((t, 820.0))
        history["turbo_on"].append((t, 1.0))

    return history


def brief_blip(duration_min=180, sample_s=60) -> dict:
    """A chiller drop-out the compressor rides out. Must NOT fire the interlock."""
    base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    history = {s: [] for s in (
        "4K", "50K", "mxc", "P1", "P5", "pulse_on", "oil_temp",
        "water_in", "comp_error", "comp_current", "flow", "turbo_on")}

    for i in range(0, duration_min * 60 // sample_s):
        m = i * sample_s / 60.0
        t = base + i * sample_s
        # Water warms for two minutes and recovers; the compressor never stops
        water = 15.0 + (6.0 if 60 <= m < 62 else 0.0)
        oil = 30.0 + (5.0 if 60 <= m < 64 else 0.0)
        history["water_in"].append((t, water))
        history["oil_temp"].append((t, oil))
        history["pulse_on"].append((t, 1.0))
        history["comp_error"].append((t, 0.0))
        history["comp_current"].append((t, 8.0))
        history["4K"].append((t, 3.5 + (0.05 if 61 <= m < 66 else 0.0)))
        history["50K"].append((t, 45.0))
        history["mxc"].append((t, 0.020))
        history["P1"].append((t, 2.0e-6))
        history["P5"].append((t, 10.0))
        history["flow"].append((t, 0.50))
        history["turbo_on"].append((t, 1.0))
    return history


def planned_warmup(duration_min=240, stop_min=70, sample_s=60) -> dict:
    """A deliberate warm-up: mixture recovered into the tank, then everything stopped in order."""
    base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    history = {s: [] for s in (
        "4K", "50K", "mxc", "P1", "P5", "pulse_on", "oil_temp",
        "water_in", "comp_error", "comp_current", "flow", "turbo_speed", "turbo_on")}

    for i in range(0, duration_min * 60 // sample_s):
        m = i * sample_s / 60.0
        t = base + i * sample_s
        after = m - stop_min

        # Mixture is pumped back into the tank over the ten minutes before the compressor stops
        p5 = 10.0 if m < stop_min - 10 else _ramp(10.0, 900.0, (m - (stop_min - 10)) / 10.0)
        # Circulation and the turbo are stopped first, by hand
        flow = 0.50 if m < stop_min - 8 else 0.0
        turbo = 1.0 if m < stop_min - 4 else 0.0
        running = 1.0 if m < stop_min else 0.0

        if m < stop_min:
            four_k, fifty_k, mxc = 3.5, 45.0, 0.020
        else:
            four_k = 3.5 + 0.16 * after
            fifty_k = 45.0 + 1.4 * after
            mxc = 0.020 + 0.0004 * after ** 2

        history["water_in"].append((t, 15.0))      # chiller fine throughout
        history["oil_temp"].append((t, 30.0 if m < stop_min else _decay(30.0, 20.0, after, 9.0)))
        history["pulse_on"].append((t, running))
        history["comp_error"].append((t, 0.0))     # no fault, ever
        history["comp_current"].append((t, 8.0 if m < stop_min else 0.0))
        history["4K"].append((t, four_k))
        history["50K"].append((t, fifty_k))
        history["mxc"].append((t, min(mxc, 300.0)))
        history["P1"].append((t, 2.0e-6))
        history["P5"].append((t, p5))
        history["flow"].append((t, flow))
        history["turbo_speed"].append((t, 820.0 * turbo))
        history["turbo_on"].append((t, turbo))
    return history


def chiller_outage_legacy(**kwargs) -> dict:
    """The same incident, seen only through the sensors that existed before the listener update.

    Matters during rollout: until the extended status whitelist reaches every fridge PC there is
    no comp_error, no comp_current and no turbo_on, and the promoted signals have no history
    behind them yet. The detector must still catch the incident on pulse_on and the 4K plate
    alone, which is why neither is merely corroborating.
    """
    history = chiller_outage(**kwargs)
    for sensor in ("comp_error", "comp_current", "turbo_on", "water_out"):
        history.pop(sensor, None)
    return history


def chiller_outage_no_compressor_bit(**kwargs) -> dict:
    """The incident on a fridge whose software never reports cparun either -- plate temperatures only."""
    history = chiller_outage_legacy(**kwargs)
    history.pop("pulse_on", None)
    return history


SCENARIOS = {
    "chiller_outage": (chiller_outage, True, "accidental warm-up after a chiller outage"),
    "chiller_outage_legacy": (chiller_outage_legacy, True, "same incident, pre-listener-update sensors only"),
    "chiller_outage_plates_only": (chiller_outage_no_compressor_bit, True, "same incident, plate temperatures only"),
    "brief_blip": (brief_blip, False, "short chiller drop-out the compressor rides out"),
    "planned_warmup": (planned_warmup, False, "deliberate warm-up with the mixture recovered"),
}


def _fmt(t, base):
    return f"t+{(t - base) / 60:6.1f} min"


def mxc_crosses_1k(history: dict):
    """When the mixing chamber passes 1 K -- the trigger the old alarm waited for."""
    for t, v in history.get("mxc", []):
        if v > 1.0:
            return t
    return None


def run_scenarios(alert_type="Critical") -> bool:
    """Run every synthetic incident. Returns True if all behaved as they should."""
    ok = True
    for name, (factory, should_fire, blurb) in SCENARIOS.items():
        history = factory()
        base = min(t for points in history.values() for t, _ in points)
        events = replay("synthetic", history, alert_type)
        fired = [(t, e) for t, e in events if e["to_state"] == "ALARM"]

        print(f"\n=== {name} -- {blurb} ===")
        for t, e in events:
            print(f"  {_fmt(t, base)}  {e['from_state']} -> {e['to_state']}: {e['reason']}")
        if not events:
            print("  (no transitions)")

        if alert_type == "Critical":
            old = old_critical_first_fire(history)
            crossed = mxc_crosses_1k(history)
            print(f"  MXC passes 1 K: " + (_fmt(crossed, base) if crossed else "never in this trace"))
            print(f"  old rule (oil>38 AND mxc>1): "
                  + (f"would fire at {_fmt(old, base)}" if old else "would NEVER fire"))
            if fired and crossed:
                lead = (crossed - fired[0][0]) / 60
                print(f"  lead time over the 1 K threshold: {lead:.0f} min")

        verdict = bool(fired) == should_fire
        ok = ok and verdict
        expected = "should fire" if should_fire else "should stay quiet"
        result = f"fired at {_fmt(fired[0][0], base)}" if fired else "did not fire"
        print(f"  {'PASS' if verdict else 'FAIL'}: {expected}, {result}")
    return ok


# -- replay against recorded data -------------------------------------------

def load_history(fridge: str, sensors, start: datetime, end: datetime) -> dict:
    """Pull a real trace out of TimescaleDB."""
    from thermometry import store
    conn = store.connect()
    cur = conn.cursor()
    placeholders = ", ".join(["%s"] * len(sensors))
    cur.execute(f"""
    SELECT s.name, m.time, m.reading
    FROM measurement m
    JOIN sensor s ON m.sensor_id = s.id
    JOIN fridge f ON s.fridge_id = f.id
    WHERE f.name = %s AND s.name IN ({placeholders}) AND m.time BETWEEN %s AND %s
    ORDER BY m.time
    """, [fridge] + list(sensors) + [start, end])
    history = {s: [] for s in sensors}
    for name, t, reading in cur.fetchall():
        if reading is not None:
            history[name].append((t.timestamp(), float(reading)))
    cur.close()
    conn.close()
    return history


def main():
    parser = argparse.ArgumentParser(description="Replay alarm logic over recorded or synthetic data")
    parser.add_argument("--scenarios", action="store_true", help="run the built-in synthetic incidents")
    parser.add_argument("--fridge", help="fridge to replay")
    parser.add_argument("--from", dest="start", help="start time, ISO format")
    parser.add_argument("--to", dest="end", help="end time, ISO format")
    parser.add_argument("--alert", default="Critical", help="alert type to replay")
    parser.add_argument("--step", type=float, default=30, help="tick interval in seconds")
    args = parser.parse_args()

    if args.alert not in REGISTRY:
        parser.error(f"unknown alert '{args.alert}'. Known: {', '.join(sorted(REGISTRY))}")

    if args.scenarios or not args.fridge:
        ok = run_scenarios(args.alert)
        print("\nAll scenarios behaved as expected." if ok else "\nSome scenarios did NOT behave as expected.")
        raise SystemExit(0 if ok else 1)

    if not (args.start and args.end):
        parser.error("--from and --to are required when replaying a real fridge")

    start = datetime.fromisoformat(args.start).astimezone(timezone.utc)
    end = datetime.fromisoformat(args.end).astimezone(timezone.utc)
    sensors = REGISTRY[args.alert].sensors

    print(f"Replaying {args.alert} @ {args.fridge} from {start} to {end}")
    history = load_history(args.fridge, sensors, start - timedelta(hours=2), end)
    present = {s: len(p) for s, p in history.items() if p}
    print(f"Loaded: {present}")
    missing = sorted(s for s in sensors if not history.get(s))
    if missing:
        print(f"No data for: {', '.join(missing)}"
              f"  (expected for signals only recorded since the listener update)")

    events = replay(args.fridge, history, args.alert, step=args.step, start=start.timestamp())
    base = start.timestamp()
    for t, e in events:
        stamp = datetime.fromtimestamp(t, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        print(f"  {stamp} ({_fmt(t, base)})  {e['from_state']} -> {e['to_state']}: {e['reason']}")
    if not events:
        print("  (no transitions in this window)")

    if args.alert == "Critical":
        old = old_critical_first_fire(history)
        if old:
            stamp = datetime.fromtimestamp(old, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
            print(f"  old rule would have fired at {stamp}")
        else:
            print("  old rule (oil>38 AND mxc>1) would NEVER have fired in this window")


if __name__ == "__main__":
    main()
