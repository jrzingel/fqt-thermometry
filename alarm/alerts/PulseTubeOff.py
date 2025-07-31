# Check if the pulse tubes are currently running
from .Alert import Alert
from datetime import datetime


class PulseTubeOff(Alert):
    def update_data(self) -> dict:
        return {
            "pulse_on": self._get_latest("pulse_on")
        }

    def is_in_alarm(self) -> bool:
        # We have the reading, check if it is running
        if "reading" in self.data["pulse_on"].keys():
            return self.data["pulse_on"]["reading"] == 0.0
        return True  # Default to alarm state (also if no data exists)

    def should_enable(self):
        return self.if_cold()

    def should_disable(self):
        return False  # Never disable once the pulse tube is running

    @property
    def description(self) -> str:
        return "Pulse tube has been turned off. This may not be intended."

    @property
    def describe_condition(self):
        if "reading" in self.data["pulse_on"].keys():
            return f"Pulse tube is {'OFF' if self.data['pulse_on']['reading'] == 0.0 else 'ON'} | Alarm = OFF"
        return ""

    @property
    def title(self) -> str:
        return "Pulse Tube Off"
