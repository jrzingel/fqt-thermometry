# Base class for an alert
from datetime import datetime, timedelta
import json
from json import JSONDecodeError

import urllib3.exceptions


class Alert(object):
    def __init__(self, http, api_url: str, fridge: str):
        self.http = http
        self.api_url = api_url
        self.fridge = fridge

        self.active = False  # Default to not being enabled (must be not in alarm state to enable, assume fridges nominal)
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

    def enable_after_delay(self, cooldown=1):
        """Re-enable the alarm if it has not been triggered for an hour"""
        if self.active is False:
            if self.last_triggered is None:
                self.active = True
                print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) re-enabling.")
            elif datetime.now() > (self.last_triggered + timedelta(hours=cooldown)):
                self.active = True
                print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) re-enabling.")

    def enable_if_cold(self):
        """Re-enable the alarm if it is no longer in a state of alarm"""
        if not self.active:
            if not self.is_in_alarm():
                self.active = True
                print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) re-enabling.")

    def enable_after_delay_and_cold(self, cooldown=1):
        """Re-enable the alarm if it is both cold and a delay has passed"""
        if not self.active:
            if self.last_triggered is None:
                self.enable_if_cold()
            elif datetime.now() > (self.last_triggered + timedelta(hours=cooldown)):
                self.enable_if_cold()

    def enable_if_below_threshold(self, sensor: str, threshold: float):
        """Re-enable the alarm if a particular sensor is below a threshold. This threshold should be sufficiently below the alarm point"""
        if not self.active:
            measurement = self._get_latest(sensor)
            if "reading" in measurement.keys() and measurement["reading"] <= threshold:
                self.active = True
                print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) re-enabling.")

    def activate(self):
        """Activate the alarm"""
        if self.active:
            print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} is in alarm for instance '{self.fridge}'. Sending teams message.")
            self.active = False
            self.last_triggered = datetime.now()

    def deactivate(self):
        """Alert is in a state that is no longer sensitive"""
        if self.active:
            print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} deactivating for instance '{self.fridge}'.")
            self.active = False

    def try_enable(self):
        """Try to re-enable the alarm. Make sure that alarm spam doesn't exist"""
        # self.enable_after_delay()
        # self.enable_if_cold()
        pass

    def is_in_alarm(self) -> bool:
        """Return if the alert is in alarm (true) or not (false)"""
        return False

    def description(self) -> str:
        """Return the description of the alert (for when triggered)"""
        return ""

    def title(self) -> str:
        """Return the title of the alert (for when triggered)"""
        return ""
