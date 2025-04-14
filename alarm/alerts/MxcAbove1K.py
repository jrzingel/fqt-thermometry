# Check if we are above 1K

from typing import override
from .Alert import Alert


class MxcAbove1K(Alert):
    @override
    def is_in_alarm(self) -> bool:
        json = self._get_latest("mxc")
        if ("timestamp" in json.keys()) and ("temp" in json.keys()):
            # We have the reading, check if it is > 1K
            if json["temp"] < 1.0:
                return False
        self.activate()
        return True  # Default to alarm state (also if no data exists)

    @override
    def try_enable(self):
        self.enable_after_delay_and_cold()

    @override
    @property
    def description(self) -> str:
        return "Mixing chamber temperature has risen above 1K. Alarm disabled until temperature is below 1K (with 1 hour cooldown)."

    @override
    @property
    def title(self) -> str:
        return "MXC Temperature above 1K"
