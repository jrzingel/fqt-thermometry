# Script to run on the fridge PC that uploads the logs to the server

import os
import requests
from datetime import datetime
import yaml
import time
from requests.exceptions import HTTPError


# TODO: Will need to adjust this on the actual machine
LOG_DIR = os.path.join(os.getcwd(), "demo_logs")
SERVER_LOCATION = "127.0.0.1:5000"
CONFIG_FILE = os.path.join(os.getcwd(), "fridge.yaml")


def check_alive():
    """Ping the server and check that it is alive"""
    url = f"http://{SERVER_LOCATION}/api/v1/ping"
    try:
        response = requests.get(url)
    except HTTPError as e:
        print(f"Error occurred when connecting to the server: {e}")
        return False
    if response.status_code != 200:
        print("Failed to connect to the server")
        return False
    return True


def upload_reading(timestamp: datetime, fridge: str, sensor: str, reading: float):
    """Given a temperature reading, upload it to the API"""
    req = requests.post(
        f"http://{SERVER_LOCATION}/api/v1/new",
        json={
            "timestamp": timestamp.isoformat(),
            "fridge": fridge,
            "sensor": sensor,
            "temp": reading,
        },
        timeout=10
    )

    if req.status_code != 200:
        print(f"Error {req.status_code} occurred when uploading to the server: {req.json()}")
    else:
        print(f"Successfully uploaded {req.json()}")


def watch_X_file(path: str, last_position: int = 0):
    """Return the next line if available"""
    while not os.path.exists(path):
        print(f"Waiting for {path} to become available...")
        time.sleep(10.0)

    with open(path, "r") as f:
        f.seek(last_position)
        line = f.readline()
        if line:
            # Something new
            return line.strip(), f.tell()
        else:
            return None, f.tell()


def get_file_position(positions: dict, sensor_name: str):
    """Lookup the file position to not repeat readings"""
    if sensor_name not in positions.keys():
        positions[sensor_name] = 0
    return positions, positions[sensor_name]


def listen():
    """Listen for new readings by watching the log files"""
    with open(CONFIG_FILE, "r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Failed to load configuration file: {e}")
            return

    fridge = config["fridge"]

    # Only upload from the current date to the server
    last_day = datetime.now().strftime("%y-%m-%d")
    file_positions = {}

    while True:  # Main loop
        today = datetime.now().strftime("%y-%m-%d")

        # Check if the day changed. If so we must move to new file positions
        if today != last_day:
            file_positions = {}
            last_day = today
            time.sleep(60.0)  # just wait to make sure the log files exist

        # Check temperatures and upload
        for (temp_sensor, params) in config["temperatures"].items():
            file_positions, pos = get_file_position(file_positions, temp_sensor)  # position to file.seek() to
            file_path = os.path.join(LOG_DIR, today, params["log"].replace("DATE", today))
            line, new_pos = watch_X_file(file_path, pos)
            file_positions[temp_sensor] = new_pos  # save new position (if changed)

            if line: # Something new. Upload it!
                # Must parse the string
                splits = line.strip().split(",")
                timestamp = datetime.strptime(','.join(splits[0:2]), "%d-%m-%y,%H:%M:%S")
                reading = float(splits[2])
                print(temp_sensor, timestamp.isoformat(), reading)
                upload_reading(timestamp, fridge, params["sensor"], reading)

        time.sleep(1.0)  # Logs only update every minute


if __name__ == "__main__":
    alive = check_alive()
    if not alive:
        raise Exception("Server seems dead.")
    print("Server ONLINE.")

    listen()




