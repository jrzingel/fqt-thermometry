# Base class for an alert
from datetime import datetime, timedelta
import json
from json import JSONDecodeError
from enum import Enum
from unittest import case

import urllib3.exceptions


class State(Enum):
    """Current state of the alert"""
    DISABLED = 0
    ENABLED = 1
    ALARM = 2
    MANUALLY_DISABLED = 3


class Alert(object):
    def __init__(self, http, api_url: str, fridge: str):
        self.http = http
        self.api_url = api_url
        self.fridge = fridge

        self.state = State.DISABLED
        self.data = {}  # Contains all the queried data from the API. Should use this between functions to stop querying the server multiple times
        #self.active = False  # Default to not being enabled (must be not in alarm state to enable, assume fridges nominal)
        self.last_triggered = None

    def _get_latest(self, sensor) -> {}:
        """Common code to fetch the latest reading from the server"""
        try:
            r = self.http.request(
                'GET',
                self.api_url + f"/api/v1/latest?fridge={self.fridge}&sensor={sensor}",
                headers={"Content-Type": "application/json"},
                timeout=10
            )
        except urllib3.exceptions.MaxRetryError as e:
            # Server is down
            print(f"ERROR API server is unreachable: {e}")
            return {}
        if r.status < 300:
            try:
                measurement = json.loads(r.data.decode('utf-8'))
            except JSONDecodeError as e:
                print(f"ERROR Failed to parse json {e}")
                return {}
            if ("reading" in measurement.keys()) and ("time" in measurement.keys()):
                return measurement
            else:
                print(f"ERROR Unknown keys {measurement.keys()}")
                return {}
        else:
            #print(f"ERROR Server error {r.status}")
            return {}

    def if_after_delay(self, cooldown=1) -> bool:
        """Re-enable the alarm if it has not been triggered for an hour"""
        if self.last_triggered is None:
            return True
        elif datetime.now() > (self.last_triggered + timedelta(hours=cooldown)):
            return True
        return False

    def if_cold(self) -> bool:
        """Re-enable the alarm if it is no longer in a state of alarm"""
        return not self.is_in_alarm()

    def if_after_delay_and_cold(self, cooldown=1) -> bool:
        """Re-enable the alarm if it is both cold and a delay has passed"""
        if self.last_triggered is None:
            return self.if_cold()
        elif datetime.now() > (self.last_triggered + timedelta(hours=cooldown)):
            return self.if_cold()
        return False

    def if_below_threshold(self, sensor: str, threshold: float) -> bool:
        """Re-enable the alarm if a particular sensor is below a threshold. This threshold should be sufficiently below the alarm point"""
        if "reading" in self.data[sensor].keys() and self.data[sensor]["reading"] <= threshold:
            return True
        return False

    def if_above_threshold(self, sensor: str, threshold: float) -> bool:
        """Re-enable the alarm if a particular sensor is above a threshold. This threshold should be sufficiently below the alarm point"""
        if "reading" in self.data[sensor].keys() and self.data[sensor]["reading"] >= threshold:
            return True
        return False

    def update(self) -> bool:
        """Update the alert control logic. Returns true if the alert changed to alarm."""
        self.data = self.update_data()
        # TODO: self.check_for_manual_disable() from the website
        match self.state:
            case State.ALARM:
                if not self.is_in_alarm():
                    print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} alarm ended for instance '{self.fridge}'.")
                    if self.should_enable():  # No longer in alarm, enable if appropriate
                        self.state = State.ENABLED
                    else:
                        self.state = State.DISABLED
                elif self.should_disable():
                    print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} deactivating for instance '{self.fridge}'.")
                    self.state = State.DISABLED  # Or disable it otherwise
            case State.DISABLED:
                if self.should_enable():
                    print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} enabling alert for instance '{self.fridge}'.")
                    self.state = State.ENABLED
            case State.ENABLED:
                if self.is_in_alarm():  # Here we go
                    print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} is in alarm for instance '{self.fridge}'. Sending teams message.")
                    self.last_triggered = datetime.now()
                    self.state = State.ALARM
                    return True
                elif self.should_disable():
                    print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} deactivating for instance '{self.fridge}'.")
                    self.state = State.DISABLED  # Or disable it otherwise
            case State.MANUALLY_DISABLED:
                # TODO: Add logic to check if the alert should be re-enabled
                pass
            case _:
                print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} unknown state of '{self.state.name}'.")
                pass
        return False

    def update_data(self) -> dict:
        """Query the API to get the latest data available"""
        raise NotImplementedError

    def should_enable(self) -> bool:
        """Return if the alert should be enabled. Make sure that alarm spam doesn't exist"""
        # return self.if_cold()
        raise NotImplementedError

    def should_disable(self) -> bool:
        """Return if the alert should be disabled. Make sure that alarm spam doesn't exist'"""
        raise NotImplementedError

    def is_in_alarm(self) -> bool:
        """Return if the alert is in alarm (true) or not (false). Assume the alert is enabled"""
        raise NotImplementedError

    def describe_condition(self) -> str:
        """Return the current alert condition in a human-readable format"""
        raise NotImplementedError

    def description(self) -> str:
        """Return the description of the alert (for when triggered)"""
        raise NotImplementedError

    def title(self) -> str:
        """Return the title of the alert (for when triggered)"""
        raise NotImplementedError
