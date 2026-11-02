# Check if we are above 1K

from .Alert import Alert


class MxcAbove1K(Alert):
    sensors = ("mxc",)

    defaults = {"alarm": 1.0, "enable": 0.9, "disable": 100.0}

    def is_in_alarm(self, obs) -> bool:
        mxc = obs.latest("mxc")
        return mxc is not None and mxc >= self.opt("alarm")

    def should_enable(self, obs) -> bool:
        mxc = obs.latest("mxc")
        return mxc is not None and mxc <= self.opt("enable")

    def should_disable(self, obs) -> bool:
        mxc = obs.latest("mxc")
        return mxc is not None and mxc >= self.opt("disable")

    @property
    def title(self) -> str:
        return "MXC Temperature above 1K"

    @property
    def description(self) -> str:
        return (f"Mixing chamber temperature has risen above {self.opt('alarm')}K. "
                f"Alarm disabled until temperature is below {self.opt('enable') * 1000:.0f} mK.")

    @property
    def now_text(self) -> str:
        mxc = self.obs.latest("mxc")
        return f"MXC = {mxc * 1000:.4f} mK" if mxc is not None else "?"

    @property
    def condition_text(self) -> str:
        return f"Alarm > {self.opt('alarm')} K, {self.opt('enable')} K > Enabled"
