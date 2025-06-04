# Check and see if the website is running.
# If not send an alert in teams

import requests
from datetime import datetime
import time
import schedule


LOG_FILE = r"C:\Users\z5653624\OneDrive - UNSW\phd\gits\thermometry\watchdog\watchdog.log"
SERVER_LOCATION = "http://status.fqt.unsw.edu.au"
PRIVATE_TEAMS_WEBHOOK = "https://prod-38.australiasoutheast.logic.azure.com:443/workflows/4864832cab2141d395e86f5a95b4f561/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=Z0UNCfaQ_5O6DVT3yzeee2qAxgO1S0rnBmYIZuwBb1o"
TEAMS_WEBHOOK = PRIVATE_TEAMS_WEBHOOK


def check_alive():
    """Ping the server and check that it is alive"""
    url = f"{SERVER_LOCATION}/api/v1/ping"
    try:
        response = requests.get(url, timeout=10.0)
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
    message = f"<blockquote>[{time}]</blockquote> <h1><strong>FQT Website Down</strong>🔔</h1>\n \n Yeah, the website is down... you might want to fix this ASAP."
    headers = {"Content-Type": "application/json"}
    r = requests.post(
        TEAMS_WEBHOOK,
        json={"text": message},
        headers=headers,
        timeout=10)
    if r.status_code < 300:
        log("Successfully sent message")
    else:
        log(f"Failed to send message {r.status_code}")


def watch():
    """Check if the server is alive, and kill it if not"""
    global sent_alert
    if check_alive():
        sent_alert = False
    else:
        log("Server is down. Time to panic")
        if not sent_alert:
            send_teams_alert()
            sent_alert = True


if __name__ == "__main__":
    log("Watchdog starting...")

    sent_alert = False
    schedule.every(1).minute.do(watch)

    while True:
        schedule.run_pending()
        time.sleep(1)


