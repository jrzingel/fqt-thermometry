# Watchtower checks that no alert has been triggered.
# If an alert is in alarm a Teams message is sent to notify the group

import os
from datetime import datetime
import urllib3
import json
import yaml
from thermometry import config
from thermometry.alarm.alerts import *


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

    def apply_changes(self):
        """Apply the changes to the alerts from the website"""
        if os.path.getsize(config.ALERT_CHANGE_PATH) == 0:  # File is empty, no changes necessary to apply
            return

        with open(config.ALERT_CHANGE_PATH, "r") as f:
            changes = json.load(f)

        for change in changes:
            for alert in self.alerts:
                if alert.__class__.__name__ == change["type"] and alert.fridge == change["fridge"]:
                    if alert.state.name != change["action"]:
                        print(f"[{datetime.now().isoformat()}] Updating status of {change['type']} @ {change['fridge']} to {change['action']}")
                        if change["action"] == "MANUALLY_DISABLED":
                            alert.state = State.MANUALLY_DISABLED
                        else:
                            alert.state = State.DISABLED
                    else:
                        print(f"[{datetime.now().isoformat()}] Received same action twice. Be patient!")
                    break
        open(config.ALERT_CHANGE_PATH, 'w').close()  # Clear the file now the changes have been processed

    def status(self, fname="status.txt"):
        """Print the current status of which alarms are active"""
        with open(fname, "w") as f:
            f.write(f"[{datetime.now().isoformat()}] Current status of configured alerts:\n")
            for alert in self.alerts:
                f.write(f"- {alert.__class__.__name__} @ {alert.fridge}: {alert.state.name} \t{alert.describe_condition}\n")

    def log_status(self):
        """Log the current alert status to a JSON file"""
        contents = []

        for alert in self.alerts:
            if alert.describe_condition != "" and "|" in alert.describe_condition:
                splits = alert.describe_condition.split("|")
                condition = {"now": splits[0].strip(), "condition": splits[1].strip()}
            else:
                condition = {"now": "?", "condition": alert.describe_condition}

            contents.append({
                "title": alert.title,
                "type": alert.__class__.__name__,
                "fridge": alert.fridge,
                "state": alert.state.name,
                "description": alert.description
            } | condition)

        with open(config.ALERT_PATH, "w") as f:
            f.write(json.dumps({
                "last_updated": datetime.now().astimezone().isoformat(sep=" ", timespec="seconds"),
                "alerts": contents
            }, indent=4))

