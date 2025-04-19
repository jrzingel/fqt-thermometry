# Check if we are above 1K

from typing import override
from .Alert import Alert


class MxcAbove1K(Alert):
    @override
    def is_in_alarm(self) -> bool:
        measurement = self._get_latest("mxc")
        # We have the reading, check if it is > 1K
        if "reading" in measurement.keys() and measurement["reading"] < 1.0:
            return False
        self.activate()
        return True  # Default to alarm state (also if no data exists)

    @override
    def try_enable(self):
        self.enable_if_below_threshold("mxc", 0.9)

    @override
    @property
    def description(self) -> str:
        return "Mixing chamber temperature has risen above 1K. Alarm disabled until temperature is below 900 mK."

    @override
    @property
    def title(self) -> str:
        return "MXC Temperature above 1K"
