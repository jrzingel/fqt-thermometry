# Rapid demo to watch Venus and alert if the pulse tube stops.
# This was coded in an hour


import sqlite3
import urllib3
import json
import time
import schedule
import os


DATABASE = os.path.join(os.path.dirname(os.getcwd()), "instance", "flaskr.sqlite")   # database path
TEST_FILE = "testfile.txt"
HOOKURL = "https://prod-07.australiasoutheast.logic.azure.com:443/workflows/b5d694e856d64fc69cd9ae8e73e8eec2/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=9-Hit9weCVmOG6T0HQuGn1_412lr1ZT8uOrcqX5bvyc"

http = urllib3.PoolManager()


def get_pulse_status(db):
    # Return if Venus pulse tube is on
    temp_row = db.execute(
    'SELECT * FROM temperatures WHERE fridge = ? AND SENSOR = ? ORDER BY timestamp DESC LIMIT 1',
        ("venus", "pulse_on")
    ).fetchone()

    if temp_row is None:
        print("No reading found")
        return False, None

    temp_row = dict(temp_row)
    if temp_row["temp"] == 0.0:
        return False, None
    else:
        return True, temp_row["temp"]


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
    db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
    status, row = get_pulse_status(db)
    if status is False:
        print("ALERT: SENDING ALARM")
        send_alarm(generate_payload(row))
    else:
        print(f"{time.time()} all ok")


def test_alert():
    # IF a file exists, send the alert
    if os.path.isfile(TEST_FILE):
        send_alarm(generate_payload("TEST MESSAGE ONLY."))


schedule.every(20).seconds.do(check_and_alert)
schedule.every(20).seconds.do(test_alert)

while True:
    schedule.run_pending()
    time.sleep(1)