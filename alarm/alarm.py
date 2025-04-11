# Rapid demo to watch Venus and alert if the pulse tube stops.
# This was coded in an hour


import sqlite3
import urllib3
import json
import time
import schedule
import os


API_URL = "localhost"  # server URL
TEST_FILE = "testfile.txt"
HOOKURL = "https://prod-07.australiasoutheast.logic.azure.com:443/workflows/b5d694e856d64fc69cd9ae8e73e8eec2/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=9-Hit9weCVmOG6T0HQuGn1_412lr1ZT8uOrcqX5bvyc"

http = urllib3.PoolManager()


def get_pulse_status():
    # Return if Venus pulse tube is on
    r = http.request(
        'GET',
        API_URL + "/api/v1/latest?fridge=venus&sensor=pulse_on",
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    if r.status < 300:
        try:
            reading = json.loads(r.data.decode('utf-8'))
            return bool(reading["temp"]), reading["timestamp"]
        except Exception as e:
            print(f"failed {e}")
            return False, None
    return False, None


def send_alarm(payload):
    headers = {"Content-Type": "application/json"}
    r = http.request(
        'POST',
        HOOKURL,
        body=json.dumps(payload).encode('utf-8'),
        headers=headers, timeout=10)
    if r.status < 300:
        return True
    else:
        raise Exception(r.status)


def generate_payload(db_row):
    # Assume that the pulse tube is off (no idea why)
    # Create adaptive card to send to teams
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "body": [
                        {  # Title
                            "type": "TextBlock",
                            "size": "medium",
                            "weight": "bolder",
                            "text": "ALARM - VENUS PULSE TUBE OFF",
                            "style": "heading",
                            "wrap": True,
                        },
                        {  # Description of the alarm
                            "type": "TextBlock",
                            "text": f"In the past minute the pulse tube of venus has shut off. This probably occured on all the fridges...\n{str(db_row)}",
                            "wrap": True,
                        }
                    ]
                }
            }
        ]
    }


def check_and_alert():
    # Function to call and run!
    status, timestamp = get_pulse_status()
    if status is False:
        print(f"ALERT: SENDING ALARM ({timestamp})")
        send_alarm(generate_payload(time))
    else:
        print(f"{time.time()} all ok ({timestamp})")


schedule.every(60).seconds.do(check_and_alert)


send_alarm(generate_payload("Launching alarm script"))
while True:
    schedule.run_pending()
    #print(get_pulse_status())
    time.sleep(1)