# Check if the pulse tubes are currently running
from typing import override
from .Alert import Alert
from datetime import datetime


class PulseTubeOff(Alert):
    @override
    def is_in_alarm(self) -> bool:
        measurement = self._get_latest("pulse_on")
        # We have the reading, check if it is running
        if "reading" in measurement.keys() and measurement["reading"] == 1.0:
            return False
        self.activate()
        return True  # Default to alarm state (also if no data exists)

    @override
    def should_enable(self):
        self.enable_if_cold()

    @override
    @property
    def description(self) -> str:
        return "Pulse tube has been turned off. This may not be intended."

    @override
    @property
    def title(self) -> str:
        return "Pulse Tube Off"
