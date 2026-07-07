# Application to run on the fridge PC that uploads the BlueFors logs to the server.
# Copied and pasted onto the fridge PCs.
# For an up-to-date version, check the repository on GitHub : https://github.com/jrzingel/fqt-thermometry

__VERSION__ = "2.1"

import os
import sys
import queue
import threading
import requests
from datetime import datetime
from dateutil import tz
import yaml
import hmac
import hashlib
import traceback
import time
import math
import colorsys

import tkinter as tk
from tkinter import scrolledtext, messagebox


def app_dir():
    """Directory the executable (or this script) lives in. fridge.yaml sits alongside it."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(app_dir(), "fridge.yaml")
ERROR_LOG = os.path.join(app_dir(), "error.log")

REQUIRED_KEYS = ("fridge", "secret", "logdir", "maxigauge", "status", "flow", "api_url", "temperatures")

DEFAULT_CONFIG = """\
# Configure the datafiles that the fridge outputs.
# In general this shouldn't change between fridges

# DATE will be replaced with the current date

fridge: "fridge-name"
secret: "fridge-key"  # used to sign messages
logdir: "C:\\\\Users\\\\LabUser\\\\Logs"
maxigauge: "maxigauge DATE.log"
status: "status DATE.log"
flow: "Flowmeter DATE.log"
api_url: "status.example.com"
#day_override: "1/8/2025"  # Upload old readings from this date

temperatures:
  T1:
    sensor: "50K"
    log: "CH1 T DATE.log"
  T2:
    sensor: "4K"
    log: "CH2 T DATE.log"
  T3:
    sensor: "magnet"
    log: "CH3 T DATE.log"
  T5:
    sensor: "still"
    log: "CH5 T DATE.log"
  T6:
    sensor: "mxc"
    log: "CH6 T DATE.log"
"""


class ServerError(Exception):
    """The server responded but not in a way we can continue from"""
    pass


def generate_signature(secret: str, fridge: str, sensor: str, unixtime: int, reading: float) -> str:
    """Generate the HMAC signature for a given reading"""
    payload = "{}.{}.{}.{}".format(fridge, sensor, unixtime, float(reading))
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def format_time(times: list):
    """Format the time strings as a datetime object in UTC time"""
    local_time = datetime.strptime(','.join(times), "%d-%m-%y,%H:%M:%S").astimezone(tz=tz.gettz("Australia/Sydney"))  # in local time
    return local_time.astimezone(tz.UTC)


def celsius_or_kelvin_to_celsius(temp: float):
    """Convert a temperature reading guessing the range"""
    if temp > 150:  # nothing should be this hot in celsius... so it must be kelvin
        return temp - 273.15
    return temp


def format_temp(kelvin: float) -> str:
    """Pretty-print a temperature in K, using mK below 1K"""
    if kelvin < 0.95:
        return "{:.1f} mK".format(kelvin * 1000)
    if kelvin < 100:
        return "{:.2f} K".format(kelvin)
    return "{:.0f} K".format(kelvin)


def temp_to_colour(kelvin: float) -> str:
    """Colour for a temperature: deep blue at mK, through green, to red at room temperature (log scale)"""
    kelvin = min(max(kelvin, 0.005), 400.0)
    frac = (math.log10(kelvin) + 2.3) / (math.log10(400.0) + 2.3)
    frac = min(max(frac, 0.0), 1.0)
    r, g, b = colorsys.hsv_to_rgb((240.0 - 240.0 * frac) / 360.0, 0.55, 0.95)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def format_duration(seconds: float) -> str:
    """Compact duration for the stats footer"""
    if seconds < 60:
        return "{:.0f} s".format(seconds)
    if seconds < 3600:
        return "{:.0f} min".format(seconds / 60)
    if seconds < 86400:
        return "{:.1f} h".format(seconds / 3600)
    return "{:.0f} d {:.0f} h".format(seconds // 86400, (seconds % 86400) / 3600)


def watch_X_file(path: str, last_position: int = 0):
    """Return the next complete line if available"""
    if not os.path.exists(path):
        return None, last_position

    with open(path, "r") as f:
        f.seek(last_position)
        line = f.readline()
        if line.endswith("\n"):
            # Something new (a line without a newline is still being written by BlueFors)
            return line.strip(), f.tell()
        else:
            return None, last_position


def describe_response(req) -> str:
    """Body of a response for logging. The server normally replies with JSON, but proxies
    and gateway errors can return HTML or an empty body instead"""
    try:
        return str(req.json())
    except ValueError:
        text = req.text.strip()
        return text[:200] if text else "<empty response>"


def log_error_to_file(error: str):
    try:
        with open(ERROR_LOG, "a") as f:
            f.write("Error at {}\n".format(datetime.now().isoformat()))
            f.write(error)
            f.write("\n")
    except OSError:
        pass  # Never die because the error log is unwritable


def validate_config(config) -> str:
    """Return an error message if the config is unusable, otherwise an empty string"""
    if not isinstance(config, dict):
        return "Configuration must be a YAML mapping of keys to values"
    missing = [key for key in REQUIRED_KEYS if key not in config]
    if missing:
        return "Configuration is missing required keys: {}".format(", ".join(missing))
    if not isinstance(config["temperatures"], dict):
        return "'temperatures' must be a mapping of channels to sensor/log names"
    for (channel, params) in config["temperatures"].items():
        if not isinstance(params, dict) or "sensor" not in params or "log" not in params:
            return "Temperature channel '{}' must define both 'sensor' and 'log'".format(channel)
    return ""


def load_config():
    """Load and validate fridge.yaml. Returns (config, error_message)"""
    if not os.path.exists(CONFIG_FILE):
        return None, "Config file '{}' does not exist.".format(CONFIG_FILE)
    with open(CONFIG_FILE, "r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return None, "Failed to load the configuration file: {}".format(e)
    error = validate_config(config)
    if error:
        return None, error
    return config, ""


class ListenerWorker(threading.Thread):
    """Background thread that watches the log files and uploads new readings.
    Never touches tkinter directly; reports back through the log/set_status callbacks."""

    def __init__(self, config: dict, log, set_status, on_reading=None, on_upload_failure=None):
        super().__init__(daemon=True)
        self.config = config
        self.log = log                                # callable(str), thread-safe
        self.set_status = set_status                  # callable(str), thread-safe
        self.on_reading = on_reading                  # callable(sensor, reading), thread-safe
        self.on_upload_failure = on_upload_failure    # callable(sensor), thread-safe
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.session = requests.Session()

    # -- control -----------------------------------------------------------

    def stop(self):
        self.stop_event.set()

    def _sleep(self, seconds: float):
        """Sleep that returns early when the worker is asked to stop"""
        self.stop_event.wait(seconds)

    def _wait_if_paused(self):
        if self.pause_event.is_set() and not self.stop_event.is_set():
            self.set_status("Paused")
            self.log("Uploading paused")
            while self.pause_event.is_set() and not self.stop_event.is_set():
                self.stop_event.wait(0.2)
            if not self.stop_event.is_set():
                self.log("Uploading resumed")
                self.set_status("Running")

    # -- server communication ------------------------------------------------

    @property
    def server(self) -> str:
        return self.config["api_url"]

    def check_alive(self) -> bool:
        """Ping the server and check that it is alive"""
        try:
            response = self.session.get("http://{}/api/v1/ping".format(self.server), timeout=10)
        except requests.exceptions.RequestException:
            return False
        return response.status_code == 200

    def wait_for_server(self):
        """Wait until the server is alive. Could be indefinitely if something is ill configured"""
        if self.check_alive():
            return
        self.set_status("Waiting for server")
        self.log("Waiting for the server at {} to come online...".format(self.server))
        while not self.stop_event.is_set():
            self._sleep(5)
            if self.check_alive():
                self.log("Server is online")
                self.set_status("Running")
                return

    def upload_reading(self, timestamp: datetime, sensor: str, reading: float, fridge: str = None):
        """Given a reading, upload it to the API. Retries until the server accepts or
        definitively rejects it, so a flaky connection never kills the listener."""
        fridge = fridge if fridge is not None else self.config["fridge"]
        signature = generate_signature(self.config["secret"], fridge, sensor, int(timestamp.timestamp()), reading)
        data = {
            "time": timestamp.isoformat(),
            "fridge": fridge,
            "sensor": sensor,
            "reading": reading,
            "signature": signature
        }

        server_errors = 0
        while not self.stop_event.is_set():
            try:
                req = self.session.post(
                    "http://{}/api/v1/new".format(self.server),
                    json=data, timeout=10
                )
            except requests.exceptions.RequestException as e:
                self.log("Server not responding ({}) while uploading {}".format(type(e).__name__, sensor))
                if self.on_upload_failure:
                    self.on_upload_failure(sensor)
                self.wait_for_server()
                continue

            if req.status_code >= 500 and server_errors < 3:
                # Usually the reverse proxy answering while the server restarts. Worth retrying
                server_errors += 1
                self.log("Server error {} while uploading {} (retry {}/3): {}".format(
                    req.status_code, sensor, server_errors, describe_response(req)))
                if self.on_upload_failure:
                    self.on_upload_failure(sensor)
                self._sleep(5)
                continue

            if req.status_code != 200:
                self.log("Error {} occurred when uploading {}: {}".format(req.status_code, sensor, describe_response(req)))
                if self.on_upload_failure:
                    self.on_upload_failure(sensor)
            else:
                self.log("{}: {} == {} | Upload {}".format(timestamp.isoformat(), sensor, reading, describe_response(req)))
                if self.on_reading:
                    self.on_reading(sensor, reading)
            break
        self._sleep(0.01)  # Don't spam the server

    def get_latest_time(self, sensor: str):
        """Get the time of the latest reading the server has for a sensor"""
        while True:
            if self.stop_event.is_set():
                raise ServerError("Stopped while syncing with the server")
            try:
                req = self.session.get(
                    "http://{}/api/v1/latest".format(self.server),
                    params={"fridge": self.config["fridge"], "sensor": sensor},
                    timeout=10
                )
            except requests.exceptions.RequestException as e:
                self.log("Server not responding ({}) while syncing {}".format(type(e).__name__, sensor))
                self.wait_for_server()
                continue
            break

        self._sleep(0.1)  # Don't spam the server

        if req.status_code == 404:
            return None  # No data uploaded yet

        if req.status_code != 200:
            raise ServerError("Error {} occurred when requesting the latest {} reading: {}".format(
                req.status_code, sensor, describe_response(req)))

        try:
            json_data = req.json()
        except ValueError:
            raise ServerError("Server returned a non-JSON response for the latest {} reading".format(sensor))

        if "time" not in json_data:
            self.log("No previous {} time recorded. Will upload all values".format(sensor))
            return None
        return datetime.fromisoformat(json_data["time"])

    # -- log file watching ---------------------------------------------------

    def log_path(self, day: str, fname: str) -> str:
        return os.path.join(self.config["logdir"], day, fname.replace("DATE", day))

    def find_sync_position(self, file_path: str, last_time, name: str) -> int:
        """Find the position in a log file of the first reading newer than last_time"""
        if last_time is None or not os.path.exists(file_path):
            return 0

        last_seek = 0
        size = os.path.getsize(file_path)
        with open(file_path, "r") as f:
            while f.tell() < size:
                line = f.readline()
                try:
                    line_time = format_time(line.strip().split(",")[0:2])
                except (ValueError, IndexError):
                    last_seek = f.tell()  # Unparseable (possibly torn) line, skip it
                    continue
                if line_time > last_time:
                    self.log("{} synced with the server from {} UTC at position {}".format(name, line_time, last_seek))
                    return last_seek
                last_seek = f.tell()
        return last_seek  # Everything in the file is already on the server

    def sync_position_with_server(self) -> dict:
        """Work out where in today's log files to resume from, based on what the server already has"""
        config = self.config
        today = datetime.now().strftime("%y-%m-%d")
        file_positions = {}

        if config.get("day_override"):
            self.log("Day override set. Uploading from the start of that day's logs")
            return file_positions  # get_new_line starts unknown files at position 0

        # Check each temperature sensor
        for (temp_sensor, params) in config["temperatures"].items():
            last_time = self.get_latest_time(params["sensor"])
            file_positions[temp_sensor] = self.find_sync_position(
                self.log_path(today, params["log"]), last_time, params["sensor"])

        # P5 is always active if the maxigauge is connected
        file_positions["maxigauge"] = self.find_sync_position(
            self.log_path(today, config["maxigauge"]), self.get_latest_time("P5"), "maxigauge")

        # oil_temp is always logged if the status file exists
        file_positions["status"] = self.find_sync_position(
            self.log_path(today, config["status"]), self.get_latest_time("oil_temp"), "status")

        # Flow is only recorded as a latest measurement, so just skip to the end of the file
        flow_path = self.log_path(today, config["flow"])
        file_positions["flow"] = os.path.getsize(flow_path) if os.path.exists(flow_path) else 0

        self.log("Starting file positions: {}".format(file_positions))
        return file_positions

    def get_new_line(self, file_positions: dict, today: str, fname: str, name: str):
        """Get the next line from a file if available. Store the updated file position if we read a line"""
        if name not in file_positions:
            file_positions[name] = 0  # It is a new day, so start from the top
        file_path = self.log_path(today, fname)
        line, new_pos = watch_X_file(file_path, file_positions[name])
        file_positions[name] = new_pos
        return file_positions, line

    # -- main loop -------------------------------------------------------------

    def upload_status_records(self, read_time: datetime, records: dict):
        """Upload the interesting readings from a parsed status log line"""
        fridge = self.config["fridge"]
        if "cptempo" in records:  # compressor temperature oil
            self.upload_reading(read_time, "oil_temp", celsius_or_kelvin_to_celsius(records["cptempo"]))  # KELVIN
        if "cpatempo" in records:  # compressor temperature oil (newer format)
            self.upload_reading(read_time, "oil_temp", celsius_or_kelvin_to_celsius(records["cpatempo"]))  # CELSIUS
        if "cparun" in records:  # compressor running (newer, meaning pulse tube is on)
            self.upload_reading(read_time, "pulse_on", records["cparun"])
        if "cptempwi" in records:  # compressor water input (older)
            self.upload_reading(read_time, "water_in", celsius_or_kelvin_to_celsius(records["cptempwi"]))  # KELVIN
        if "cpatempwi" in records:  # compressor water input (newer)
            self.upload_reading(read_time, "water_in", celsius_or_kelvin_to_celsius(records["cpatempwi"]))  # CELSIUS
        if "cptempwo" in records:  # compressor water output (older)
            self.upload_reading(read_time, "water_out", celsius_or_kelvin_to_celsius(records["cptempwo"]))  # KELVIN
        if "cpatempwo" in records:  # compressor water output (newer)
            self.upload_reading(read_time, "water_out", celsius_or_kelvin_to_celsius(records["cpatempwo"]))  # CELSIUS
        if "tc400actualspd" in records:  # turbo speed (tc400) (note there are two in parallel but we only log one)
            self.upload_reading(read_time, "turbo_speed", records["tc400actualspd"])  # Hertz

        # Optionally check the second compressor status if it exists (for XLD systems)
        if "cparun_2" in records:
            self.upload_reading(read_time, "pulse_on", records["cparun_2"], fridge=fridge + "2")
        if "cpatempo_2" in records:
            self.upload_reading(read_time, "oil_temp", celsius_or_kelvin_to_celsius(records["cpatempo_2"]), fridge=fridge + "2")  # CELSIUS
        if "cpatempwi_2" in records:
            self.upload_reading(read_time, "water_temp", celsius_or_kelvin_to_celsius(records["cpatempwi_2"]), fridge=fridge + "2")  # CELSIUS

    def listen(self):
        """Listen for new readings by watching the log files"""
        config = self.config
        self.log("Watching {} at {}".format(config["fridge"], config["logdir"]))

        self.set_status("Syncing")
        last_day = datetime.now().strftime("%y-%m-%d")
        file_positions = self.sync_position_with_server()

        # Add a day override feature for uploading old data
        day_override = config.get("day_override")
        self.set_status("Running")

        while not self.stop_event.is_set():  # Main loop
            self._wait_if_paused()
            if self.stop_event.is_set():
                break

            today = datetime.now().strftime("%y-%m-%d") if day_override is None else day_override

            # Check if the day changed. If so we must move to new file positions
            if today != last_day and day_override is None:
                self.log("New day. Resetting file positions")
                file_positions = {}
                last_day = today
                self._sleep(60)  # just wait to make sure the log files exist

            # Check temperatures and upload
            for (temp_sensor, params) in config["temperatures"].items():
                file_positions, line = self.get_new_line(file_positions, today, params["log"], temp_sensor)
                if line:  # Something new. Upload it!
                    try:
                        splits = line.split(",")
                        read_time = format_time(splits[0:2])
                        reading = float(splits[2])
                    except (ValueError, IndexError):
                        self.log("Could not parse {} line {!r}. Skipping...".format(temp_sensor, line))
                        continue
                    if reading != 0.0:  # Temperatures can never be 0K (means the sensor is disabled)
                        self.upload_reading(read_time, params["sensor"], reading)  # Only upload the UTC time

            # Upload maxigauge pressures
            file_positions, line = self.get_new_line(file_positions, today, config["maxigauge"], "maxigauge")
            if line:
                # Parse the string and only upload ACTIVE pressure sensor readings
                splits = line.split(",")
                if len(splits) == 39:  # 2 timestamps + 6 sensors * 6 values + 1 end
                    try:
                        read_time = format_time(splits[0:2])
                        for i in range(6):
                            if int(splits[2 + 6*i + 2]) == 1:  # Only upload active sensors
                                self.upload_reading(read_time, "P{}".format(i+1), float(splits[2 + 6*i + 3]))
                    except (ValueError, IndexError):
                        self.log("Could not parse maxigauge line {!r}. Skipping...".format(line))
                else:
                    self.log("Maxigauge log file has an unexpected number of columns. Skipping...")

            # Check the compressor status.
            file_positions, line = self.get_new_line(file_positions, today, config["status"], "status")
            if line:
                splits = line.split(",")

                # Based on the BlueFors Control software used there is two different formats that this log file can take.
                # The format can also change depending on which sensor/pumps are used in the gas handling system.
                # Both are alternating name,value pairs after the two timestamp columns; see log_format.md

                if len(splits) % 2 == 0 and len(splits) >= 4:  # make sure every reading has a name paired with it
                    try:
                        read_time = format_time(splits[0:2])
                        records = {splits[i]: float(splits[i+1]) for i in range(2, len(splits), 2)}
                    except (ValueError, IndexError):
                        self.log("Could not parse status line {!r}. Skipping...".format(line))
                    else:
                        self.upload_status_records(read_time, records)
                else:
                    self.log("Status log file has an unexpected number of columns. Skipping...")

            # Check the flowmeter status.
            file_positions, line = self.get_new_line(file_positions, today, config["flow"], "flow")
            if line:
                try:
                    splits = line.split(",")
                    read_time = format_time(splits[0:2])
                    reading = float(splits[2])
                except (ValueError, IndexError):
                    self.log("Could not parse flow line {!r}. Skipping...".format(line))
                else:
                    self.upload_reading(read_time, "flow", reading)

            # TODO: On older fridges check the valve file to see if the pulse tube is on

            self._sleep(0.1)  # Logs only update every minute so no need to check more often

    def run(self):
        try:
            while not self.stop_event.is_set():
                try:
                    self.set_status("Connecting")
                    self.wait_for_server()
                    if self.stop_event.is_set():
                        break
                    self.listen()
                except Exception:
                    if self.stop_event.is_set():
                        break
                    error = traceback.format_exc()
                    log_error_to_file(error)
                    self.log("Unexpected error (written to error.log):\n{}".format(error))
                    self.set_status("Error")
                    self.log("Restarting in 30 seconds...")
                    self._sleep(30)
        finally:
            self.set_status("Stopped")
            self.log("Listener stopped")


class JourneyStrip(tk.Canvas):
    """Animated banner showing each reading's journey: fridge -> logs -> listener -> server -> you.
    Dots are launched by real upload events; a red dot bounces off the server link when an upload fails."""

    HEIGHT = 100
    FRAME_MS = 40    # ~25 fps, and only ticks while dots are in flight
    DOT_MS = 1600    # time for a dot to travel the full path
    MAX_DOTS = 8     # cap concurrent dots during backlog catch-up bursts
    ICON_Y = 36
    LABEL_Y = 68
    CAPTION_Y = 86

    def __init__(self, parent):
        super().__init__(parent, height=self.HEIGHT, bg="#eef4fa", highlightthickness=0)
        self.fridge_name = "fridge"
        self.state = "Stopped"
        self.caption = ""
        self.dots = []       # {"item": canvas id, "t": progress 0..1, "fail": bool}
        self.animating = False
        self.centres = []    # x centres of the five nodes
        self.bind("<Configure>", lambda event: self.redraw())

    def set_fridge_name(self, name: str):
        self.fridge_name = name
        self.redraw()

    def set_state(self, state: str):
        self.state = state
        self.redraw()

    def show_reading(self, caption: str):
        """A reading was uploaded successfully: run a dot along the whole path"""
        self.caption = caption
        self.launch_dot(fail=False)

    def show_failure(self, caption: str):
        """An upload failed: run a dot that bounces back off the server link"""
        self.caption = caption
        self.launch_dot(fail=True)

    def launch_dot(self, fail: bool):
        self.itemconfig("caption", text=self.caption)
        if len(self.dots) >= self.MAX_DOTS or len(self.centres) < 5:
            return
        item = self.create_oval(0, 0, 0, 0, fill="#e03131" if fail else "#2f9e44", outline="")
        self.dots.append({"item": item, "t": 0.0, "fail": fail})
        if not self.animating:
            self.animating = True
            self.after(self.FRAME_MS, self.animate)

    def animate(self):
        if not self.dots:
            self.animating = False
            return
        for dot in list(self.dots):
            dot["t"] += float(self.FRAME_MS) / self.DOT_MS
            if dot["t"] >= 1.0:
                self.delete(dot["item"])
                self.dots.remove(dot)
                continue
            x, y = self.dot_position(dot)
            self.coords(dot["item"], x - 4, y - 4, x + 4, y + 4)
        self.after(self.FRAME_MS, self.animate)

    def dot_position(self, dot):
        if dot["fail"]:
            # From the listener towards the server, bouncing back at the midpoint
            x0 = self.centres[2]
            x1 = (self.centres[2] + self.centres[3]) / 2.0
            frac = dot["t"] * 2 if dot["t"] < 0.5 else (1.0 - dot["t"]) * 2
            return x0 + (x1 - x0) * frac, self.ICON_Y
        # Piecewise-linear travel through all five nodes
        seg = dot["t"] * 4
        i = min(int(seg), 3)
        frac = seg - i
        return self.centres[i] + (self.centres[i + 1] - self.centres[i]) * frac, self.ICON_Y

    def redraw(self):
        self.delete("static")
        w = max(self.winfo_width(), 480)
        self.centres = [w * (i + 0.5) / 5.0 for i in range(5)]

        paused = self.state == "Paused"
        idle = self.state == "Stopped"
        down = self.state in ("Waiting for server", "Connecting", "Error")
        line = "#b6bec9" if paused or idle else "#7a8ba3"

        y = self.ICON_Y
        for i in range(4):
            broken = down and i == 2  # the listener -> server link
            self.create_line(self.centres[i] + 30, y, self.centres[i + 1] - 30, y,
                             fill="#e03131" if broken else line, width=2, arrow=tk.LAST,
                             dash=(4, 3) if broken else None, tags="static")

        self.draw_fridge(self.centres[0], y)
        self.draw_logfile(self.centres[1], y)
        self.draw_listener(self.centres[2], y)
        self.draw_server(self.centres[3], y)
        self.draw_user(self.centres[4], y)

        for cx, label in zip(self.centres, [self.fridge_name[:12], "logs", "listener", "server", "you"]):
            self.create_text(cx, self.LABEL_Y, text=label, fill="gray25", font=("TkDefaultFont", 9), tags="static")

        if paused:
            caption = "paused"
        elif idle:
            caption = "not running"
        elif down:
            caption = "server unreachable - readings will catch up once it is back"
        else:
            caption = self.caption or "waiting for new readings..."
        self.create_text(w / 2.0, self.CAPTION_Y, text=caption, fill="gray40",
                         font=("TkDefaultFont", 9, "italic"), tags=("static", "caption"))

    # Each node icon is drawn with plain Canvas primitives so no image assets need bundling

    def draw_fridge(self, cx, cy):
        self.create_rectangle(cx - 13, cy - 20, cx + 13, cy + 20, fill="#dceefe", outline="#4a6fa5", width=2, tags="static")
        self.create_line(cx - 13, cy - 6, cx + 13, cy - 6, fill="#4a6fa5", width=2, tags="static")
        self.create_line(cx + 8, cy - 16, cx + 8, cy - 10, fill="#4a6fa5", width=2, tags="static")  # freezer handle
        self.create_line(cx + 8, cy + 1, cx + 8, cy + 11, fill="#4a6fa5", width=2, tags="static")   # door handle
        sx, sy, r = cx - 3, cy + 7, 5  # snowflake on the door
        for dx, dy in ((r, 0), (r * 0.5, r * 0.87), (-r * 0.5, r * 0.87)):
            self.create_line(sx - dx, sy - dy, sx + dx, sy + dy, fill="#4a6fa5", tags="static")

    def draw_logfile(self, cx, cy):
        self.create_polygon(cx - 12, cy - 17, cx + 6, cy - 17, cx + 12, cy - 11, cx + 12, cy + 17, cx - 12, cy + 17,
                            fill="white", outline="gray45", tags="static")
        self.create_line(cx + 6, cy - 17, cx + 6, cy - 11, cx + 12, cy - 11, fill="gray45", tags="static")
        for i in range(4):
            self.create_line(cx - 7, cy - 6 + i * 5, cx + 7, cy - 6 + i * 5, fill="#9db2c8", tags="static")

    def draw_listener(self, cx, cy):
        self.create_rectangle(cx - 17, cy - 14, cx + 17, cy + 8, fill="#22364a", outline="gray35", tags="static")
        self.create_text(cx, cy - 3, text="v" + __VERSION__, fill="#7be08a", font=("Courier New", 8), tags="static")
        self.create_line(cx, cy + 8, cx, cy + 14, fill="gray35", width=3, tags="static")
        self.create_line(cx - 10, cy + 15, cx + 10, cy + 15, fill="gray35", width=3, tags="static")

    def draw_server(self, cx, cy):
        for x0, y0, x1, y1 in ((cx - 20, cy - 4, cx + 2, cy + 14),
                               (cx - 10, cy - 14, cx + 12, cy + 6),
                               (cx - 2, cy - 6, cx + 20, cy + 14)):
            self.create_oval(x0, y0, x1, y1, fill="#dde6f2", outline="#8fa3bd", tags="static")

    def draw_user(self, cx, cy):
        self.create_rectangle(cx - 10, cy - 18, cx + 10, cy + 18, fill="white", outline="gray35", width=2, tags="static")
        self.create_line(cx - 6, cy + 6, cx - 2, cy - 2, cx + 2, cy + 2, cx + 6, cy - 8, fill="green4", width=2, tags="static")
        self.create_oval(cx - 2, cy + 11, cx + 2, cy + 15, outline="gray35", tags="static")


class FridgeSchematic(tk.Canvas):
    """Side panel drawing the fridge stages as plates coloured by their latest temperature"""

    WIDTH = 175
    PLATE_ORDER = ["50K", "4K", "magnet", "still", "cold", "mxc"]  # canonical top-to-bottom order
    STALE_S = 900  # dim a plate if its sensor has been quiet this long

    def __init__(self, parent):
        super().__init__(parent, width=self.WIDTH, bg="#f5f8fb", highlightthickness=0)
        self.plates = []   # sensor names, top to bottom
        self.latest = {}   # sensor -> (kelvin, monotonic timestamp)
        self.bind("<Configure>", lambda event: self.redraw())
        self.tick()

    def set_sensors(self, sensors: list):
        known = [name for name in self.PLATE_ORDER if name in sensors]
        extra = [name for name in sensors if name not in self.PLATE_ORDER]
        self.plates = known + extra
        self.redraw()

    def update_reading(self, sensor: str, kelvin: float):
        if sensor in self.plates:
            self.latest[sensor] = (kelvin, time.monotonic())
            self.redraw()

    def tick(self):
        """Periodic redraw so plates dim once their sensor goes quiet"""
        self.redraw()
        self.after(30000, self.tick)

    def redraw(self):
        self.delete("all")
        w = self.winfo_width() or self.WIDTH
        h = self.winfo_height()
        if h < 120:
            return
        if not self.plates:
            self.create_text(w / 2.0, h / 2.0, text="no sensors\nconfigured", fill="gray50",
                             justify=tk.CENTER, font=("TkDefaultFont", 9, "italic"))
            return

        self.create_text(w / 2.0, 14, text="fridge stages", fill="gray40", font=("TkDefaultFont", 9, "italic"))

        # Pulse tube sitting on top of the vacuum can
        can_top, can_bottom = 52, h - 14
        self.create_rectangle(w / 2.0 - 14, can_top - 22, w / 2.0 + 14, can_top, fill="#d7dee6", outline="gray55")
        self.create_text(w / 2.0, can_top - 11, text="PT", fill="gray30", font=("TkDefaultFont", 8))

        # Vacuum can
        self.create_rectangle(16, can_top, w - 16, can_bottom, outline="gray55", width=2)

        # Plates evenly spaced inside the can, with support rods between them
        gap = (can_bottom - can_top) / float(len(self.plates))
        ph = min(9, gap * 0.38)  # plate half-height, shrinks if the window is tiny
        x0, x1 = 26, w - 26
        for (i, sensor) in enumerate(self.plates):
            y = can_top + gap * (i + 0.5)
            if i > 0:
                prev_y = can_top + gap * (i - 0.5)
                self.create_line(x0 + 12, prev_y + ph, x0 + 12, y - ph, fill="gray60")
                self.create_line(x1 - 12, prev_y + ph, x1 - 12, y - ph, fill="gray60")

            reading = self.latest.get(sensor)
            if reading is None:
                fill, text, text_colour = "#e3e8ee", "{}: -".format(sensor), "gray45"
            else:
                kelvin, seen = reading
                stale = (time.monotonic() - seen) > self.STALE_S
                fill = "#d7dee6" if stale else temp_to_colour(kelvin)
                text = "{}: {}".format(sensor, format_temp(kelvin))
                text_colour = "gray45" if stale else "gray10"
            self.create_rectangle(x0, y - ph, x1, y + ph, fill=fill, outline="gray50")
            self.create_text((x0 + x1) / 2.0, y, text=text, fill=text_colour, font=("TkDefaultFont", 9))


class ListenerApp:
    """Minimal GUI wrapping the listener worker"""

    POLL_MS = 100
    MAX_LOG_LINES = 2000
    STATUS_COLOURS = {
        "Running": "green4",
        "Paused": "dark orange",
        "Waiting for server": "dark orange",
        "Connecting": "dark orange",
        "Syncing": "dark orange",
        "Error": "red3",
        "Stopped": "gray40",
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue = queue.Queue()
        self.worker = None
        self.restart_pending = False

        # Stats shown in the footer
        self.started = time.monotonic()
        self.uploads_today = 0
        self.upload_errors = 0
        self.stats_day = datetime.now().strftime("%y-%m-%d")
        self.last_upload = None  # monotonic timestamp of the last successful upload

        root.title("FQT Thermometry Listener v{}".format(__VERSION__))
        root.geometry("940x600")
        root.minsize(680, 460)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.strip = JourneyStrip(root)
        self.strip.pack(fill=tk.X, side=tk.TOP)

        footer = tk.Frame(root, bg="#eef1f4")
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        self.footer_var = tk.StringVar(value="")
        tk.Label(footer, textvariable=self.footer_var, bg="#eef1f4", fg="gray30", anchor=tk.W).pack(fill=tk.X, padx=8, pady=2)

        main = tk.Frame(root)
        main.pack(fill=tk.BOTH, expand=True)

        self.schematic = FridgeSchematic(main)
        self.schematic.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0), pady=(8, 8))

        right = tk.Frame(main)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        top = tk.Frame(right)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))
        tk.Label(top, text="Status:").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Stopped")
        self.status_label = tk.Label(top, textvariable=self.status_var, font=("TkDefaultFont", 10, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=(4, 16))
        self.info_var = tk.StringVar(value="")
        tk.Label(top, textvariable=self.info_var, fg="gray40").pack(side=tk.LEFT)

        buttons = tk.Frame(right)
        buttons.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.pause_button = tk.Button(buttons, text="Pause", width=10, command=self.toggle_pause)
        self.pause_button.pack(side=tk.LEFT)
        tk.Button(buttons, text="Edit config", width=10, command=self.open_config_editor).pack(side=tk.LEFT, padx=6)
        tk.Button(buttons, text="Clear log", width=10, command=self.clear_log).pack(side=tk.LEFT)

        self.log_text = scrolledtext.ScrolledText(right, state=tk.DISABLED, wrap=tk.NONE, font=("Courier New", 13))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.append_log("FQT Thermometry Listener v{}".format(__VERSION__))
        self.start_worker()
        self.root.after(self.POLL_MS, self.process_queue)
        self.update_footer()

    # -- worker management (all on the tk thread) ------------------------------

    def start_worker(self):
        self.restart_pending = False
        config, error = load_config()
        if error:
            self.append_log(error)
            self.append_log("Fix the configuration with 'Edit config' to start the listener.")
            self.set_status("Stopped")
            self.info_var.set(CONFIG_FILE)
            return
        self.info_var.set("{}  ->  {}".format(config["fridge"], config["api_url"]))
        self.strip.set_fridge_name(config["fridge"])
        self.schematic.set_sensors([params["sensor"] for params in config["temperatures"].values()])
        self.worker = ListenerWorker(config, self.worker_log, self.worker_status,
                                     self.worker_reading, self.worker_fail)
        self.worker.start()
        self.pause_button.config(text="Pause")

    def restart_worker(self):
        if self.restart_pending:
            return
        if self.worker is not None and self.worker.is_alive():
            self.restart_pending = True
            self.worker.stop()
            self.check_worker_stopped()
        else:
            self.start_worker()

    def check_worker_stopped(self):
        """Poll until the old worker exits (it may be mid HTTP request), then start a new one"""
        if self.worker is not None and self.worker.is_alive():
            self.root.after(200, self.check_worker_stopped)
        else:
            self.start_worker()

    def toggle_pause(self):
        if self.worker is None or not self.worker.is_alive():
            self.append_log("The listener is not running. Fix the configuration with 'Edit config' first.")
            return
        if self.worker.pause_event.is_set():
            self.worker.pause_event.clear()
            self.pause_button.config(text="Pause")
        else:
            self.worker.pause_event.set()
            self.pause_button.config(text="Resume")

    def on_close(self):
        if self.worker is not None:
            self.worker.stop()
        self.root.destroy()

    # -- callbacks from the worker thread ---------------------------------------

    def worker_log(self, message: str):
        self.queue.put(("log", message))

    def worker_status(self, status: str):
        self.queue.put(("status", status))

    def worker_reading(self, sensor: str, reading: float):
        self.queue.put(("reading", (sensor, reading)))

    def worker_fail(self, sensor: str):
        self.queue.put(("fail", sensor))

    def process_queue(self):
        try:
            while True:
                kind, message = self.queue.get_nowait()
                if kind == "log":
                    self.append_log(message)
                elif kind == "status":
                    self.set_status(message)
                elif kind == "reading":
                    self.handle_reading(*message)
                elif kind == "fail":
                    self.handle_failure(message)
        except queue.Empty:
            pass
        self.root.after(self.POLL_MS, self.process_queue)

    def handle_reading(self, sensor: str, reading: float):
        today = datetime.now().strftime("%y-%m-%d")
        if today != self.stats_day:  # midnight rollover
            self.stats_day = today
            self.uploads_today = 0
        self.uploads_today += 1
        self.last_upload = time.monotonic()

        value = format_temp(reading) if sensor in self.schematic.plates else "{:g}".format(reading)
        self.strip.show_reading("{} == {} heading to the server...".format(sensor, value))
        self.schematic.update_reading(sensor, reading)

    def handle_failure(self, sensor: str):
        self.upload_errors += 1
        self.strip.show_failure("{} upload failed, retrying...".format(sensor))

    # -- display -----------------------------------------------------------------

    def set_status(self, status: str):
        self.status_var.set(status)
        self.status_label.config(fg=self.STATUS_COLOURS.get(status, "black"))
        self.strip.set_state(status)

    def update_footer(self):
        last = "never" if self.last_upload is None else "{} ago".format(format_duration(time.monotonic() - self.last_upload))
        self.footer_var.set("Uploads today: {}   |   Last upload: {}   |   Upload errors: {}   |   Listener uptime: {}".format(
            self.uploads_today, last, self.upload_errors, format_duration(time.monotonic() - self.started)))
        self.root.after(1000, self.update_footer)

    def append_log(self, message: str):
        at_bottom = self.log_text.yview()[1] >= 0.999  # only auto-scroll if not reading history
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, "{}  {}\n".format(datetime.now().strftime("%H:%M:%S"), message))
        overflow = int(self.log_text.index("end-1c").split(".")[0]) - self.MAX_LOG_LINES
        if overflow > 0:
            self.log_text.delete("1.0", "{}.0".format(overflow + 1))
        self.log_text.config(state=tk.DISABLED)
        if at_bottom:
            self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    # -- config editor -------------------------------------------------------------

    def open_config_editor(self):
        editor = tk.Toplevel(self.root)
        editor.title("Edit {}".format(CONFIG_FILE))
        editor.geometry("640x520")
        editor.transient(self.root)

        text = scrolledtext.ScrolledText(editor, wrap=tk.NONE, font=("Courier New", 13), undo=True)
        text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                text.insert("1.0", f.read())
        else:
            text.insert("1.0", DEFAULT_CONFIG)

        def save():
            content = text.get("1.0", "end-1c")
            try:
                config = yaml.safe_load(content)
            except yaml.YAMLError as e:
                messagebox.showerror("Invalid YAML", "Could not parse the configuration:\n\n{}".format(e), parent=editor)
                return
            error = validate_config(config)
            if error:
                messagebox.showerror("Invalid configuration", error, parent=editor)
                return
            with open(CONFIG_FILE, "w") as f:
                f.write(content)
                if not content.endswith("\n"):
                    f.write("\n")
            editor.destroy()
            self.append_log("Configuration saved. Restarting the listener...")
            self.restart_worker()

        bar = tk.Frame(editor)
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Button(bar, text="Save and restart", command=save).pack(side=tk.LEFT)
        tk.Button(bar, text="Cancel", command=editor.destroy).pack(side=tk.LEFT, padx=6)


def main():
    root = tk.Tk()
    ListenerApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Last resort: a crash in the GUI itself still leaves a trace on disk
        log_error_to_file(traceback.format_exc())
        raise