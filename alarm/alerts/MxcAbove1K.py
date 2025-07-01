# Check if we are above 1K

from .Alert import Alert


class MxcAbove1K(Alert):
    def update_data(self) -> dict:
        return {
            "mxc": self._get_latest("mxc")
        }

    def is_in_alarm(self) -> bool:
        # We have the reading, check if it is > 1K
        if "reading" in self.data["mxc"].keys() and self.data["mxc"]["reading"] < 1.0:
            return False
        return True  # Default to alarm state (also if no data exists)

    def should_enable(self) -> bool:
        return self.if_below_threshold("mxc", 0.9)

    def should_disable(self) -> bool:
        return self.if_above_threshold("mxc", 100)

    @property
    def description(self) -> str:
        return "Mixing chamber temperature has risen above 1K. Alarm disabled until temperature is below 900 mK."

    @property
    def describe_condition(self):
        if "reading" in self.data["mxc"].keys():
            return f"MXC = {self.data['mxc']['reading']*1000:.4f} mK | Alarm > 1.0 K, 0.9 K > Enabled"
        return ""

    @property
    def title(self) -> str:
        return "MXC Temperature above 1K"
