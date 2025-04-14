# Base class for an alert
from datetime import datetime, timedelta
import json
from json import JSONDecodeError


class Alert(object):
    def __init__(self, http, api_url: str, fridge: str):
        self.http = http
        self.api_url = api_url
        self.fridge = fridge

        self.active = True  # Once triggered we do not check again for an hour
        self.last_triggered = None

    def _get_latest(self, sensor) -> {}:
        """Common code to fetch the latest reading from the server"""
        r = self.http.request(
            'GET',
            self.api_url + f"/api/v1/latest?fridge={self.fridge}&sensor={sensor}",
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if r.status < 300:
            try:
                return json.loads(r.data.decode('utf-8'))
            except JSONDecodeError as e:
                print(f"Failed to parse json {e}")
                return {}
        print(f"Server error {r.status}")
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
        if self.active is False:
            if not self.is_in_alarm():
                self.active = True
                print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) re-enabling.")

    def enable_after_delay_and_cold(self, cooldown=1):
        """Re-enable the alarm if it is both cold and a delay has passed"""
        if self.active is False:
            if self.last_triggered is None:
                if not self.is_in_alarm():
                    self.active = True
                    print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) re-enabling.")
            elif datetime.now() > (self.last_triggered + timedelta(hours=cooldown)):
                if not self.is_in_alarm():
                    self.active = True
                    print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) re-enabling.")


    def activate(self):
        """Activate the alarm"""
        if self.active:
            print(f"[{datetime.now().isoformat()}] {self.__class__.__name__} ({self.fridge}) is in alarm! Sending alert")
            self.active = False
            self.last_triggered = datetime.now()

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
