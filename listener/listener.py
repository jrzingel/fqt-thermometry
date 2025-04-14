# Script to run on the fridge PC that uploads the logs to the server
# Copied and pasted onto the fridge PCs.
# For an up-to-date version, check the repository on GitHub : https://github.com/jrzingel/fqt-thermometry

__VERSION__ = 1.3

import os
import requests
from datetime import datetime
from dateutil import tz
import yaml
import time


SERVER_LOCATION = "129.94.115.104"
#SERVER_LOCATION = "localhost:5000"
CONFIG_FILE = os.path.join(os.getcwd(), "fridge.yaml")


def check_alive():
    """Ping the server and check that it is alive"""
    url = f"http://{SERVER_LOCATION}/api/v1/ping"
    try:
        response = requests.get(url, timeout=10.0)
    except requests.exceptions.RequestException as e:
        return False
    if response.status_code != 200:
        return False
    return True


def wait_for_server():
    """Wait until the server is alive. Could be indefinitely if something is ill configured"""
    print("Waiting for the server to come online", end="")
    while not check_alive():
        print(".", end="")
        time.sleep(5.0)
    print(" ONLINE")



def upload_reading(timestamp: datetime, fridge: str, sensor: str, reading: float):
    """Given a temperature reading, upload it to the API"""
    print(f"{timestamp.isoformat()}: {sensor} == {reading}", end=" ")
    data = {
        "timestamp": timestamp.isoformat(),
        "fridge": fridge,
        "sensor": sensor,
        "temp": reading,
    }
    try:
        req = requests.post(
            f"http://{SERVER_LOCATION}/api/v1/new",
            json=data, timeout=10
        )
    except requests.exceptions.RequestException as e:
        print(f"\nServer not responding {e.request}")
        wait_for_server()
        req = requests.post(
            f"http://{SERVER_LOCATION}/api/v1/new",
            json=data, timeout=10
        )

    if req.status_code != 200:
        print(f"\nError {req.status_code} occurred when uploading to the server: {req.json()}")
    else:
        print(f" | Upload {req.json()}")
    time.sleep(0.1)  # Don't spam the server


def watch_X_file(path: str, last_position: int = 0):
    """Return the next line if available"""
    if not os.path.exists(path):
        print(f"File {path} does not exist. Skipping...")
        return None, last_position

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


def format_time(times: list):
    """Format the time strings as a datetime object in UTC time"""
    local_time = datetime.strptime(','.join(times), "%d-%m-%y,%H:%M:%S").astimezone(tz=tz.gettz("Australia/Sydney"))  # in local time
    return local_time.astimezone(tz.UTC)


def listen():
    """Listen for new readings by watching the log files"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Config file '{CONFIG_FILE}' does not exist. Make sure that this file exists, and then try again.")
        return

    with open(CONFIG_FILE, "r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Failed to load configuration file: {e}")
            return

    fridge = config["fridge"]
    logdir = config["logdir"]
    print(f"Watching {fridge} at {logdir}")

    # Only upload from the current date to the server
    last_day = datetime.now().strftime("%y-%m-%d")
    file_positions = {}

    while True:  # Main loop
        today = datetime.now().strftime("%y-%m-%d")

        # Check if the day changed. If so we must move to new file positions
        if today != last_day:
            print("New day. Resetting file positions")
            file_positions = {}
            last_day = today
            time.sleep(60.0)  # just wait to make sure the log files exist

        # Check temperatures and upload
        for (temp_sensor, params) in config["temperatures"].items():
            file_positions, pos = get_file_position(file_positions, temp_sensor)  # position to file.seek() to
            file_path = os.path.join(logdir, today, params["log"].replace("DATE", today))
            line, new_pos = watch_X_file(file_path, pos)
            file_positions[temp_sensor] = new_pos  # save new position (if changed)

            if line: # Something new. Upload it!
                # Must parse the string
                splits = line.strip().split(",")
                reading = float(splits[2])
                if reading != 0.0:  # Temperatures can never be 0K (means the sensor is disabled)
                    upload_reading(format_time(splits[0:2]), fridge, params["sensor"], reading)  # Only upload the UTC time

        # Upload maxigauge pressures
        file_positions, pos = get_file_position(file_positions, "maxigauge")
        file_path = os.path.join(logdir, today, config["maxigauge"].replace("DATE", today))
        line, new_pos = watch_X_file(file_path, pos)
        file_positions["maxigauge"] = new_pos
        if line:
            # Parse the string and only upload ACTIVE pressure sensor readings
            splits = line.strip().split(",")
            if len(splits) == 39:  # 2 timestamps + 6 sensors * 6 values + 1 end
                for i in range(6):
                    if int(splits[2 + 6*i + 2]) == 1:  # Only upload active sensors
                        upload_reading(format_time(splits[0:2]), fridge, f"P{i+1}", float(splits[2 + 6*i + 3]))
            else:
                print("Maxigauge log file has an unexpected number of columns. Skipping...")

        if "status" in config.keys():
            # Check if the compressor (pulse tube) is running
            file_positions, pos = get_file_position(file_positions, "status")
            file_path = os.path.join(logdir, today, config["status"].replace("DATE", today))
            line, new_pos = watch_X_file(file_path, pos)
            file_positions["status"] = new_pos
            if line:
                # Parse the string and only upload ACTIVE pressure sensor readings
                splits = line.strip().split(",")
                if len(splits) == 74:
                    upload_reading(format_time(splits[0:2]), fridge, "pulse_on", float(splits[21]))
                else:
                    print("Status log file has an unexpected number of columns. Skipping...")


        time.sleep(1.0)  # Logs only update every minute so no need to check more often



if __name__ == "__main__":
    print(f"Version: {__VERSION__}")

    wait_for_server()

    listen()

    # If we get here, something went wrong
    time.sleep(10.0)  # enough time to read the error
    print("Exiting...")


