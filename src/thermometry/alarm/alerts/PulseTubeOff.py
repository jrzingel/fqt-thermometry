# Check if the pulse tubes are currently running
from .Alert import Alert


class PulseTubeOff(Alert):
    sensors = ("pulse_on",)

    def is_in_alarm(self, obs) -> bool:
        running = obs.latest("pulse_on")
        # Missing data is handled by the UNKNOWN state, so absence is no longer read as "off"
        return running is not None and running == 0.0

    def should_enable(self, obs) -> bool:
        return not self.is_in_alarm(obs)

    @property
    def title(self) -> str:
        return "Pulse Tube Off"

    @property
    def description(self) -> str:
        return "Pulse tube has been turned off. This may not be intended."

    @property
    def now_text(self) -> str:
        running = self.obs.latest("pulse_on")
        if running is None:
            return "?"
        return f"Pulse tube is {'OFF' if running == 0.0 else 'ON'}"

    @property
    def condition_text(self) -> str:
        return "Alarm = OFF"
