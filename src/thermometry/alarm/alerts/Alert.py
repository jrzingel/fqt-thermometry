# Base class for an alert
from datetime import datetime, timedelta, timezone
from enum import Enum


class State(Enum):
    """Current state of the alert"""
    DISABLED = 0
    ENABLED = 1
    ALARM = 2
    MANUALLY_DISABLED = 3
    UNKNOWN = 4  # Data is missing or stale, so the alert cannot say whether things are safe


#: States a human can put an alert into from the website
ACTIONABLE_STATES = {State.DISABLED.name, State.MANUALLY_DISABLED.name, "ACKNOWLEDGE"}


class Alert(object):
    """One alert, watching one fridge.

    The state machine is unchanged in spirit -- DISABLED is "armed but waiting for the condition
    to clear", ENABLED is "watching", ALARM has fired -- with two corrections:

    * Missing or stale data moves the alert to UNKNOWN instead of DISABLED. The old code treated
      every read failure as a reason to quietly stop alarming, which is the wrong direction for
      anything protecting hardware.
    * MANUALLY_DISABLED is never left except by an explicit action, and state is persisted, so a
      restart no longer silently re-arms alerts somebody deliberately switched off.
    """

    #: Sensors this alert needs. The Watchtower unions these per fridge into a single query.
    sensors = ()

    #: How much history to fetch, in minutes.
    window_minutes = 60

    #: A latching alert stays in ALARM until a person acknowledges it, however the fridge behaves
    #: afterwards. Used for the alerts that gate the experimental interlock.
    latching = False

    #: Seconds without data before the alert gives up and reports UNKNOWN.
    stale_after = 10 * 60

    #: Whether the alert may fire on its very first evaluation.
    #:
    #: DISABLED is normally the boot state as well as the post-alarm cool-off, which means an
    #: alert starting up while the condition is already bad waits for it to clear before it will
    #: ever arm. That is right for the nuisance alerts -- restarting the service during a planned
    #: warm-up should not fire MxcAbove1K -- but wrong for anything protecting hardware: if the
    #: service restarts mid-incident, nobody has been told yet.
    arm_on_boot = False

    #: Default tunables, overridable per fridge from config.yaml.
    defaults = {}

    def __init__(self, fridge: str, options: dict = None):
        self.fridge = fridge
        self.options = dict(self.defaults)
        self.options.update(options or {})

        self.state = State.DISABLED
        self.since = datetime.now(timezone.utc)
        self.last_triggered = None
        self.detail = {}          # persisted scratch space: latches, evidence, timers
        self.obs = None           # most recent Observation
        self.reason = ""          # why the last transition happened

    def now(self):
        """Current time, taken from the observation being evaluated.

        In production that is wall clock. During a replay it is the simulated time, which is
        what lets latch durations and hysteresis timers behave identically offline and online.
        """
        if self.obs is not None:
            return datetime.fromtimestamp(self.obs.now, tz=timezone.utc)
        return datetime.now(timezone.utc)

    @property
    def type_name(self) -> str:
        return self.__class__.__name__

    @property
    def key(self) -> tuple:
        return (self.type_name, self.fridge)

    def opt(self, name):
        return self.options[name]

    # -- persistence ---------------------------------------------------------

    def restore(self, record: dict):
        """Adopt a state previously written to the database."""
        try:
            self.state = State[record["state"]]
        except KeyError:
            self.state = State.DISABLED
        self.since = record.get("since") or datetime.now(timezone.utc)
        self.last_triggered = record.get("last_triggered")
        self.detail = dict(record.get("detail") or {})

    def apply_action(self, action: str) -> bool:
        """Apply a state change requested from the website. Returns True if anything changed."""
        if action == "MANUALLY_DISABLED":
            if self.state is State.MANUALLY_DISABLED:
                return False
            self._transition(State.MANUALLY_DISABLED, "manually disabled from the website")
            return True
        if action in ("DISABLED", "ACKNOWLEDGE"):
            if self.state is State.DISABLED:
                return False
            # Acknowledging clears every latch, which is the only way out of a latching ALARM
            self.clear_latches()
            self._transition(State.DISABLED, "acknowledged from the website")
            return True
        return False

    # -- state machine -------------------------------------------------------

    def _transition(self, new_state: State, reason: str):
        self.previous_state = self.state
        self.state = new_state
        self.since = self.now()
        self.reason = reason

    def update(self, obs) -> dict:
        """Advance the state machine by one tick.

        Returns a transition dict when the state changed, else None. `notify` marks the
        transitions that deserve a Teams message.
        """
        self.obs = obs
        previous = self.state

        # Somebody deliberately switched this off. Nothing observed changes that.
        if self.state is State.MANUALLY_DISABLED:
            return None

        # Fail safe, not silent: if we cannot see the fridge we say so rather than
        # reporting that everything is fine.
        if self.is_unavailable(obs):
            if self.state is not State.UNKNOWN:
                self._transition(State.UNKNOWN, self.unavailable_reason(obs))
                return self._transition_record(previous, notify=self.notify_on_unknown)
            return None

        in_alarm = self.is_in_alarm(obs)

        match self.state:
            case State.ALARM:
                if self.latching:
                    pass  # Only an acknowledgement leaves a latched alarm
                elif not in_alarm:
                    if self.should_enable(obs):
                        self._transition(State.ENABLED, "alarm condition cleared")
                    else:
                        self._transition(State.DISABLED, "alarm condition cleared")
                elif self.should_disable(obs):
                    self._transition(State.DISABLED, "deactivated while in alarm")
            case State.UNKNOWN:
                # Data is back. Re-enter the normal cycle from a safe place.
                if in_alarm:
                    self._trigger("data returned and the alarm condition is present")
                elif self.should_enable(obs):
                    self._transition(State.ENABLED, "data returned")
                else:
                    self._transition(State.DISABLED, "data returned")
            case State.DISABLED:
                if self.should_enable(obs):
                    self.detail["armed_once"] = True
                    self._transition(State.ENABLED, "conditions nominal, alert armed")
                elif self.arm_on_boot and in_alarm and not self.detail.get("armed_once"):
                    # First evaluation and the condition is already bad: nobody has been told
                    self._trigger(self.alarm_reason(obs))
            case State.ENABLED:
                if in_alarm:
                    self._trigger(self.alarm_reason(obs))
                elif self.should_disable(obs):
                    self._transition(State.DISABLED, "deactivated")

        if self.state is previous:
            return None
        return self._transition_record(previous, notify=(self.state is State.ALARM))

    def _trigger(self, reason: str):
        self.last_triggered = self.now()
        self._transition(State.ALARM, reason)

    def _transition_record(self, previous: State, notify: bool) -> dict:
        return {
            "alert": self,
            "type": self.type_name,
            "fridge": self.fridge,
            "from_state": previous.name,
            "to_state": self.state.name,
            "reason": self.reason,
            "notify": notify,
        }

    # -- availability --------------------------------------------------------

    #: Whether going UNKNOWN should send a Teams message. Off by default so a brief listener
    #: outage does not spam the channel; UnresponsiveFridge is the alert that reports that.
    notify_on_unknown = False

    def is_unavailable(self, obs) -> bool:
        """True when this alert cannot form an opinion because the data is missing or stale."""
        if obs.error is not None:
            return True
        return obs.is_stale(self.stale_after, list(self.sensors) if self.sensors else None)

    def unavailable_reason(self, obs) -> str:
        if obs.error is not None:
            return f"could not read the database: {obs.error}"
        age = obs.data_age(list(self.sensors) if self.sensors else None)
        if age is None:
            return "no data has ever been recorded for the sensors this alert needs"
        return f"no new data for {age / 60:.0f} minutes"

    # -- helpers for subclasses ---------------------------------------------

    def if_after_delay(self, cooldown=1) -> bool:
        """Re-enable the alarm if it has not been triggered for `cooldown` hours"""
        if self.last_triggered is None:
            return True
        return self.now() > (self.last_triggered + timedelta(hours=cooldown))

    def latch(self, name: str, on: bool, reasons=None):
        """Set or clear a named latch, remembering when it was set. Persisted across restarts.

        Returns how long the latch has been held, in seconds, or None when it is clear.
        """
        key = f"{name}_since"
        if on:
            if self.detail.get(key) is None:
                self.detail[key] = self.now().isoformat()
            if reasons is not None:
                self.detail[f"{name}_reasons"] = reasons
        else:
            self.detail.pop(key, None)
            self.detail.pop(f"{name}_reasons", None)
        return self.latched_for(name)

    def clear_latches(self):
        """Drop every latch this alert is holding."""
        for key in [k for k in self.detail if k.endswith(("_since", "_reasons"))]:
            self.detail.pop(key, None)

    def latched_for(self, name: str):
        """Seconds the named latch has been held, or None if it is not set."""
        stamp = self.detail.get(f"{name}_since")
        if not stamp:
            return None
        try:
            since = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            return None
        return (self.now() - since).total_seconds()

    # -- interface subclasses implement -------------------------------------

    def is_in_alarm(self, obs) -> bool:
        """Return whether the alarm condition holds. Only called with usable data."""
        raise NotImplementedError

    def should_enable(self, obs) -> bool:
        """Return whether the alert should arm. Keep a hysteresis gap below the alarm point."""
        return not self.is_in_alarm(obs)

    def should_disable(self, obs) -> bool:
        """Return whether the alert should stop watching (nothing left to protect)."""
        return False

    def alarm_reason(self, obs) -> str:
        """A one-line explanation of why the alarm fired, for the audit trail."""
        return self.now_text

    @property
    def title(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    @property
    def now_text(self) -> str:
        """Current readings, human-readable. Shown in the 'Now' column."""
        return "?"

    @property
    def condition_text(self) -> str:
        """The rule, human-readable. Shown in the 'Condition' column."""
        return ""

    # -- display -------------------------------------------------------------

    def display(self) -> dict:
        """The fields the website and its consumers see."""
        if self.state is State.UNKNOWN:
            now = self.unavailable_reason(self.obs) if self.obs is not None else "no data"
        else:
            try:
                now = self.now_text
            except Exception as e:  # a broken formatter must never take the alarm system down
                now = f"(could not format reading: {e})"
        return {
            "title": self.title,
            "type": self.type_name,
            "fridge": self.fridge,
            "state": self.state.name,
            "description": self.description,
            "now": now,
            "condition": self.condition_text,
        }
