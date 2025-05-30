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
        for alert in self.alerts:
            is_in_alarm = alert.update()
            if is_in_alarm:  # Only triggers when state changes from ENABLED -> ALARM once
                # Oh, no! Trigger the alarm
                msg = self._format_message(alert.title, alert.fridge, alert.description)
                self.send_message(msg)

    def status(self, fname="status.txt"):
        """Print the current status of which alarms are active"""
        with open(fname, "w") as f:
            f.write(f"[{datetime.now().isoformat()}] Current status of configured alerts:\n")
            for alert in self.alerts:
                f.write(f"- {alert.__class__.__name__} @ {alert.fridge}: {alert.state.name} \t{alert.describe_condition}\n")

    def log_status(self, fname="status.json"):
        """Log the current alert status to a JSON file"""
        contents = [{
            "title": alert.title,
            "type": alert.__class__.__name__,
            "fridge": alert.fridge,
            "state": alert.state.name,
            "condition": alert.describe_condition,
            "description": alert.description
        } for alert in self.alerts]
        with open(fname, "w") as f:
            f.write(json.dumps(contents, indent=4))



if __name__ == "__main__":
    morello_webhook = "https://prod-58.australiasoutheast.logic.azure.com:443/workflows/b051ee511eb440c7acd48c3169746c5b/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=C57BECtucQyq-WnDmi35NKyk2-Q8MNo-kaVuFk3PSp4"
    test_webhook = "https://prod-38.australiasoutheast.logic.azure.com:443/workflows/4864832cab2141d395e86f5a95b4f561/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=Z0UNCfaQ_5O6DVT3yzeee2qAxgO1S0rnBmYIZuwBb1o"
    local_api = "http://localhost"
    server_api = "http://status.fqt.unsw.edu.au"

    #watch = Watchtower(morello_webhook, local_api)
    watch = Watchtower(test_webhook, server_api)
    watch.load_config("config.yaml")

    schedule.every(6).seconds.do(watch.lookout)
    schedule.every(6).seconds.do(watch.status)
    schedule.every(6).seconds.do(watch.log_status)

    while True:
        schedule.run_pending()
        time.sleep(1)

