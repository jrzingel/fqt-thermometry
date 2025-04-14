# Watchtower checks that no alert has been triggered.
# If an alert is in alarm a Teams message is sent to notify the group

from datetime import datetime
import urllib3
import json
import yaml
import time
import schedule

from alerts import *


class Watchtower:
    def __init__(self, msteams_webhook: str, fridge_api: str):
        self.msteams_webhook = msteams_webhook
        self.http = urllib3.PoolManager()
        self.fridge_api = fridge_api
        self.alerts = []

    def load_config(self, config_path):
        """Load the config path"""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        if "alerts" not in config:
            print("Missing 'alerts' section in config file")
            return

        for alert, fridges in config["alerts"].items():
            for fridge in fridges:
                self.alerts.append(
                    eval(alert)(self.http, self.fridge_api, fridge)
                )
        print(f"Loaded {len(self.alerts)} alerts")

    @staticmethod
    def _format_message(title: str, fridge: str, message: str) -> str:
        """Format the alert to a consistent style"""
        time = datetime.now().strftime("%a %d.%m.%Y, %H:%M:%S")
        return f"<blockquote>[{time}] @ {fridge.capitalize()}</blockquote> <h1><strong>{title}</strong>🔔</h1>\n \n \n{message}\n \n See more <a href='http://status.fqt.unsw.edu.au/dashboard?fridge={fridge}'>here</a>."

    def send_message(self, message: str):
        """Send the message to teams"""
        headers = {"Content-Type": "application/json"}
        r = self.http.request(
            'POST',
            self.msteams_webhook,
            body=json.dumps({"text": message}).encode('utf-8'),
            headers=headers, timeout=10)
        if r.status < 300:
            print(f"[{datetime.now().isoformat()}] Successfully sent message")
        else:
            print(f"[{datetime.now().isoformat()}] Failed to send message {r.status}")

    def lookout(self):
        """Check if any alert is in alarm"""
        #print(f"\rUpdated @ [{datetime.now().isoformat()}]", end="")
        for alert in self.alerts:
            if alert.active:
                if alert.is_in_alarm():
                    # Oh, no! Trigger the alarm
                    msg = self._format_message(alert.title, alert.fridge, alert.description)
                    self.send_message(msg)
            else:
                alert.try_enable()


if __name__ == "__main__":
    test_webhook = "https://prod-58.australiasoutheast.logic.azure.com:443/workflows/b051ee511eb440c7acd48c3169746c5b/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=C57BECtucQyq-WnDmi35NKyk2-Q8MNo-kaVuFk3PSp4"
    fridge_api = "http://status.fqt.unsw.edu.au"
    #fridge_api = "http://localhost"

    watch = Watchtower(test_webhook, fridge_api)
    watch.load_config("config.yaml")

    #schedule.every(1).minute.do(watch.lookout)
    schedule.every(10).seconds.do(watch.lookout)

    while True:
        schedule.run_pending()
        time.sleep(1)

