# -*- coding: utf-8 -*-
"""
Created on Wed Jul 9 15:20 2025

Check if the fridge has encountered a critical alert meaning that the measurement should stop immediately and the device be grounded

Charizard watches for this alert and will halt any running programs if it is executed

@author: james
"""

from .Alert import Alert

# Alarm if BOTH MXC > 1K and OIL TEMP > 38deg


class Critical(Alert):
    def update_data(self) -> dict:
        return {
            "mxc": self._get_latest("mxc"),
            "oil_temp": self._get_latest("oil_temp")
        }

    def is_in_alarm(self) -> bool:
        if "reading" in self.data["oil_temp"].keys() and "reading" in self.data["mxc"].keys():
            # Check if these values are within range
            if self.data["oil_temp"]["reading"] > 38 and self.data["mxc"]["reading"] > 1.0:
                # Oil is hot and we are warm.
                # Time to panic
                return True
            else:
                # We are ok
                return False
        return True  # If there is an error default to being in alarm

    def should_enable(self) -> bool:
        return self.if_below_threshold("oil_temp", 35.0) and self.if_below_threshold("mxc", 0.9)

    def should_disable(self) -> bool:
        return self.if_above_threshold("mxc", 100)  # It is warm enough now

    @property
    def description(self):
        return f"{self.fridge.capitalize()} has encountered a critical alert with both a hot mixing chamber (>1.0K) and oil temperature (>38deg). Charizard will halt any experiments and ground the device if the notebook is running. Urgent action must be taken now to prevent a complete warm up."

    @property
    def describe_condition(self) -> str:
        if "reading" in self.data["oil_temp"].keys() and "reading" in self.data["mxc"].keys():
            return f" MXC = {self.data['mxc']['reading']} K, OIL TEMP = {self.data['oil_temp']['reading']} C | Alarm if MXC > 1.0 and Oil Temp > 38"
        return " | Alarm if MXC > 1.0 and Oil Temp > 38"

    @property
    def title(self):
        return "Fridge in critical condition"
