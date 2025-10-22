# Check and see if the website is running.
# If not send an alert in teams

import requests
from datetime import datetime
import time
import schedule
from thermometry import config

VERSION = "1.0"
LOG_FILE = "watchdog.log"


def check_alive():
    """Ping the server and check that it is alive"""
    url = f"{config.WATCHDOG_WEBSITE_URL}/api/v1/ping"
    try:
        response = requests.get(url, timeout=30.0)
    except requests.exceptions.RequestException as e:
        return False
    if response.status_code != 200:
        return False
    return True


def log(message: str):
    """Log the message to a file"""
    msg = f"[{datetime.now().isoformat()}] {message}"
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


def send_teams_alert():
    """The server is done. Message me."""
    time = datetime.now().strftime("%a %d.%m.%Y, %H:%M:%S")
    message = f"<blockquote>[{time}]</blockquote> <h1><strong>FQT Website Down</strong>🔔</h1>\n \nThermometry website is unreachable... this should be addressed ASAP. Contact James."
    headers = {"Content-Type": "application/json"}
    r = requests.post(
        config.WATCHDOG_TEAMS_WEBHOOK,
        json={"text": message},
        headers=headers,
        timeout=30)
    if r.status_code < 300:
        log("Successfully sent message")
    else:
        log(f"Failed to send message {r.status_code}")


def watch():
    """Check if the server is alive, and kill it if not"""
    global sent_alert
    if check_alive():
        sent_alert = False
        log("Server is alive")
    else:
        log("Server is down. Time to panic")
        if not sent_alert:
            send_teams_alert()
            sent_alert = True


if __name__ == "__main__":
    log(f"Version: {VERSION}")
    log("Watchdog starting...")

    sent_alert = False
    schedule.every(1).minute.do(watch)

    while True:
        schedule.run_pending()
        time.sleep(1)


