# Script to run on the fridge PC that uploads the logs to the server
# Copied and pasted onto the fridge PCs.
# For an up-to-date version, check the repository on GitHub : https://github.com/jrzingel/fqt-thermometry

__VERSION__ = 1.7

import os
import sys
import requests
from datetime import datetime
from dateutil import tz
import yaml
import hmac
import hashlib
import time


SERVER_LOCATION = "129.94.115.104"  # points to status.fqt.unsw.edu.au
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
    print(" OK.")


def generate_signature(secret: str, fridge: str, sensor: str, unixtime: int, reading: float) -> str:
    """Generate the HMAC signature for a given reading"""
    payload = f"{fridge}.{sensor}.{unixtime}.{float(reading)}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def upload_reading(timestamp: datetime, fridge: str, sensor: str, reading: float, secret: str):
    """Given a temperature reading, upload it to the API"""
    print(f"{timestamp.isoformat()}: {sensor} == {reading}", end=" ")

    signature = generate_signature(secret, fridge, sensor, int(timestamp.timestamp()), reading)
    data = {
        "time": timestamp.isoformat(),
        "fridge": fridge,
        "sensor": sensor,
        "reading": reading,
        "signature": signature
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
        #print(f"File {path} does not exist. Skipping...")  # This line is too verbose when the magnet is not connected
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


def celsius_or_kelvin_to_celsius(temp: float):
    """Convert a temperature reading guessing the range"""
    if temp > 150:  # nothing should be this hot in celsius... so it must be kelvin
        return temp - 273.15
    return temp


def listen():
    """Listen for new readings by watching the log files"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Config file '{CONFIG_FILE}' does not exist. Make sure that this file exists, and then try again.")
        time.sleep(60)
        return

    with open(CONFIG_FILE, "r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Failed to load configuration file: {e}")
            time.sleep(60)
            return

    fridge = config["fridge"]
    secret = config["secret"]
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
                    upload_reading(format_time(splits[0:2]), fridge, params["sensor"], reading, secret)  # Only upload the UTC time

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
                        upload_reading(format_time(splits[0:2]), fridge, f"P{i+1}", float(splits[2 + 6*i + 3]), secret)
            else:
                print("Maxigauge log file has an unexpected number of columns. Skipping...")

        if "status" in config.keys():
            # Check if the compressor status.
            file_positions, pos = get_file_position(file_positions, "status")
            file_path = os.path.join(logdir, today, config["status"].replace("DATE", today))
            line, new_pos = watch_X_file(file_path, pos)
            file_positions["status"] = new_pos
            if line:
                # Parse the string and only upload ACTIVE pressure sensor readings
                splits = line.strip().split(",")
                read_time = format_time(splits[0:2])

                # Based on the BlueFors Control software used there is two different formats that this log file can take.
                # The format can also change depending on which sensor/pumps are used in the gas handling system
                # NEWER: 23-04-25,23:59:59,nxdsf,0.000000e+00,nxdspt,2.951500e+02,nxdsct,3.021500e+02,nxdst,9.331200e+07,nxdsbs,6.436440e+07,nxdstrs,0.000000e+00,ctrl_pres_ok,1.000000e+00,ctrl_pres,1.000000e+00,cpastate,3.000000e+00,cparun,1.000000e+00,cpawarn,-0.000000e+00,cpaerr,-0.000000e+00,cpatempwi,1.679444e+01,cpatempwo,2.427111e+01,cpatempo,2.421444e+01,cpatemph,6.006001e+01,cpalp,1.151647e+02,cpalpa,1.110834e+02,cpahp,3.080892e+02,cpahpa,3.058809e+02,cpadp,1.931654e+02,cpacurrent,1.251326e+01,cpahours,3.020700e+04,cpascale,0.000000e+00,cpasn,1.076200e+04,ctr_pressure_ok,1.000000e+00,tc400actualspd,0.000000e+00,tc400ovtempelec,0.000000e+00,tc400ovtemppum,0.000000e+00,tc400heating,0.000000e+00,tc400pumpaccel,0.000000e+00,tc400pumpstatn,1.000000e+00,tc400remoteprio,1.000000e+00,tc400spdswptatt,0.000000e+00,tc400setspdatt,0.000000e+00,tc400standby,0.000000e+00
                # OLDER: 24-04-25,09:40:03,cptempwi,2.898500e+02,cptempwo,2.987500e+02,cptemph,3.370500e+02,cptempo,3.065500e+02,cpttime,2.294605e+08,cpavgl,8.190974e+00,cpavgh,2.160817e+01,ctrl_pres_ok,1.000000e+00,ctrl_pres,1.000000e+00,ctr_pressure_ok,1.000000e+00,tc400actualspd,8.200000e+02,tc400drvpower,1.630000e+02,tc400ovtempelec,0.000000e+00,tc400ovtemppum,0.000000e+00,tc400heating,0.000000e+00,tc400pumpaccel,0.000000e+00,tc400pumpstatn,1.000000e+00,tc400remoteprio,1.000000e+00,tc400spdswptatt,1.000000e+00,tc400setspdatt,1.000000e+00,tc400standby,0.000000e+00,tc400actualspd_2,8.200000e+02,tc400ovtempelec_2,0.000000e+00,tc400ovtemppum_2,0.000000e+00,tc400heating_2,0.000000e+00,tc400pumpaccel_2,0.000000e+00,tc400pumpstatn_2,1.000000e+00,tc400remoteprio_2,1.000000e+00,tc400spdswptatt_2,1.000000e+00,tc400setspdatt_2,1.000000e+00,tc400standby_2,0.000000e+00

                if len(splits) % 2 == 0:  # make sure every reading has a name paired with it
                    records = {}
                    for i in range(2, len(splits), 2):
                        records[splits[i]] = float(splits[i+1])

                    # Extract readings to upload
                    if "cptempo" in records.keys():  # compressor temperature oil
                        upload_reading(read_time, fridge, "oil_temp", celsius_or_kelvin_to_celsius(records["cptempo"]), secret)  # KELVIN
                    if "cpatempo" in records.keys():  # compressor temperature oil (newer format)
                        upload_reading(read_time, fridge, "oil_temp", celsius_or_kelvin_to_celsius(records["cpatempo"]), secret)  # CELSIUS
                    if "cparun" in records.keys():  # compressor running (newer, meaning pulse tube is on)
                        upload_reading(read_time, fridge, "pulse_on", records["cparun"], secret)
                    if "cptempwi" in records.keys():  # compressor water input (older)
                        upload_reading(read_time, fridge, "water_temp", celsius_or_kelvin_to_celsius(records["cptempwi"]), secret)  # KELVIN
                    if "cpatempwi" in records.keys():  # compressor water input (newer)
                        upload_reading(read_time, fridge, "water_temp", celsius_or_kelvin_to_celsius(records["cpatempwi"]), secret)  # CELSIUS

                    # Optionally check the second compressor status if it exists (for XLD systems)
                    if "cparun_2" in records.keys():
                        upload_reading(read_time, fridge + "2", "pulse_on", records["cparun_2"], secret)
                    if "cpatempo_2" in records.keys():
                        upload_reading(read_time, fridge + "2", "oil_temp", celsius_or_kelvin_to_celsius(records["cpatempo_2"]), secret)  # CELSIUS
                    if "cpatempwi_2" in records.keys():
                        upload_reading(read_time, fridge + "2", "water_temp", celsius_or_kelvin_to_celsius(records["cpatempwi_2"]), secret)  # CELSIUS
                else:
                    print("Status log file has an unexpected number of columns. Skipping...")

        # TODO: On older fridges check the valve file to see if the pulse tube is on

        time.sleep(1.0)  # Logs only update every minute so no need to check more often


if __name__ == "__main__":
    print(f"Version: {__VERSION__}")

    wait_for_server()
    #upload_reading(datetime.now(tz.UTC), "venus", "P1", 234234, "venus-key")

    try:
        listen()
    except KeyboardInterrupt:
        print("Shutting down")
        time.sleep(5.0)
    sys.exit(0)

