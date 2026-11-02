# Watchtower checks that no alert has been triggered.
# If an alert is in alarm a Teams message is sent to notify the group

import json
import traceback
from datetime import datetime

import urllib3
import yaml

from thermometry import config, store
from thermometry.alarm.alerts import REGISTRY
from thermometry.alarm.observation import Observation


def log(message: str):
    print(f"[{datetime.now().isoformat()}] {message}", flush=True)


class Watchtower:
    """Evaluates every configured alert once per tick.

    Two things changed from the original. Data comes from Postgres directly rather than from the
    web server's own REST API, so a website hiccup can no longer disarm the alarms; and alert
    state lives in the database rather than in this process's memory, so restarts no longer lose
    active alarms or silently re-arm alerts somebody switched off.
    """

    def __init__(self, msteams_webhook: str, dashboard_url: str = None):
        self.msteams_webhook = msteams_webhook
        self.dashboard_url = (dashboard_url or getattr(config, "EXTERNAL_WEBSITE_URL", "")).rstrip("/")
        self.http = urllib3.PoolManager()
        self.alerts = []
        self.conn = None

    # -- setup ---------------------------------------------------------------

    def db(self):
        """Return a live connection, reconnecting if the last one died."""
        if self.conn is None or self.conn.closed:
            self.conn = store.connect()
        return self.conn

    def load_config(self, config_path):
        """Load the config path"""
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}

        if "alerts" not in cfg:
            log("Missing 'alerts' section in config file")
            return

        for name, target in (cfg["alerts"] or {}).items():
            cls = REGISTRY.get(name)
            if cls is None:
                log(f"Unknown alert type '{name}' in config. Known types: {', '.join(sorted(REGISTRY))}")
                continue

            # Either a plain list of fridges, or a mapping of fridge -> threshold overrides
            if isinstance(target, dict):
                entries = target.items()
            else:
                entries = [(fridge, {}) for fridge in (target or [])]

            for fridge, options in entries:
                self.alerts.append(cls(fridge, options or {}))

        log(f"Loaded {len(self.alerts)} alerts")
        self.restore()

    def restore(self):
        """Adopt the states persisted by a previous run."""
        try:
            saved = store.load_alert_states(self.db())
        except Exception as e:
            log(f"ERROR could not restore alert state: {e}")
            return
        restored = 0
        for alert in self.alerts:
            record = saved.get(alert.key)
            if record:
                alert.restore(record)
                restored += 1
        log(f"Restored {restored} alert states from the database")

    # -- notifications -------------------------------------------------------

    def _format_message(self, title: str, fridge: str, message: str) -> str:
        """Format the alert to a consistent style"""
        time = datetime.now().strftime("%a %d.%m.%Y, %H:%M:%S")
        link = f"{self.dashboard_url}/dashboard?fridge={fridge}"
        return (f"<blockquote>[{time}] @ {fridge.capitalize()}</blockquote> "
                f"<h1><strong>{title}</strong>\U0001f514</h1>\n \n \n{message}\n \n "
                f"See more <a href='{link}'>here</a>.")

    def send_message(self, message: str):
        """Send the message to teams"""
        headers = {"Content-Type": "application/json"}
        try:
            r = self.http.request(
                'POST',
                self.msteams_webhook,
                body=json.dumps({"text": message}).encode('utf-8'),
                headers=headers, timeout=10)
        except Exception as e:
            log(f"Failed to send message: {e}")
            return
        if r.status < 300:
            log("Successfully sent message")
        else:
            log(f"Failed to send message {r.status}")

    # -- the tick ------------------------------------------------------------

    def observe(self, fridge: str, sensors: set, minutes: float) -> Observation:
        """Fetch one window of history for one fridge, in a single query."""
        sensors = sorted(sensors)
        try:
            conn = self.db()
            window = store.fetch_window(conn, fridge, sensors, minutes)
            latest = store.fetch_latest_for_fridge(conn, fridge, sensors)
        except Exception as e:
            if self.conn is not None and not self.conn.closed:
                self.conn.rollback()
            else:
                self.conn = None  # force a reconnect next tick
            log(f"ERROR could not read data for {fridge}: {e}")
            return Observation.unavailable(fridge, str(e))
        return Observation(fridge, window, latest)

    def lookout(self):
        """Check if any alert is in alarm"""
        # Group by fridge so each fridge's data is fetched once, not once per alert per sensor
        by_fridge = {}
        for alert in self.alerts:
            by_fridge.setdefault(alert.fridge, []).append(alert)

        for fridge, alerts in by_fridge.items():
            sensors = set()
            minutes = 0
            for alert in alerts:
                sensors.update(alert.sensors)
                minutes = max(minutes, alert.window_minutes)
            obs = self.observe(fridge, sensors, minutes)

            for alert in alerts:
                try:
                    self.step(alert, obs)
                except Exception:
                    # One misbehaving alert must never take down the evaluator
                    log(f"ERROR while updating {alert.type_name} @ {alert.fridge}:\n{traceback.format_exc()}")

        self.beat()

    def step(self, alert, obs):
        """Advance the alert, then persist whatever happened."""
        transition = alert.update(obs)

        if transition:
            log(f"{alert.type_name} @ {alert.fridge}: "
                f"{transition['from_state']} -> {transition['to_state']} ({transition['reason']})")
            try:
                store.record_alert_event(
                    self.db(), alert.type_name, alert.fridge,
                    transition["from_state"], transition["to_state"], transition["reason"],
                    alert.detail)
            except Exception as e:
                log(f"ERROR could not record alert event: {e}")

            if transition["notify"]:
                self.send_message(self._format_message(alert.title, alert.fridge, alert.description))

        self.persist(alert)

    def persist(self, alert):
        """Write an alert's state and display fields back to the database."""
        detail = dict(alert.detail)
        detail["display"] = alert.display()
        try:
            store.save_alert_state(
                self.db(), alert.type_name, alert.fridge, alert.state.name,
                alert.since, alert.last_triggered, detail)
        except Exception as e:
            log(f"ERROR could not persist {alert.type_name} @ {alert.fridge}: {e}")

    # -- commands from the website -------------------------------------------

    def apply_changes(self):
        """Apply the changes to the alerts from the website"""
        try:
            saved = store.load_alert_states(self.db())
        except Exception as e:
            log(f"ERROR could not read pending actions: {e}")
            return

        for alert in self.alerts:
            record = saved.get(alert.key)
            action = record.get("pending_action") if record else None
            if not action:
                continue
            previous = alert.state
            if alert.apply_action(action):
                log(f"Updating status of {alert.type_name} @ {alert.fridge} to {alert.state.name}")
                try:
                    store.record_alert_event(
                        self.db(), alert.type_name, alert.fridge,
                        previous.name, alert.state.name, alert.reason, alert.detail)
                except Exception as e:
                    log(f"ERROR could not record alert event: {e}")
            else:
                log(f"Received same action twice for {alert.type_name} @ {alert.fridge}. Be patient!")
            self.persist(alert)  # clears pending_action

    # -- liveness ------------------------------------------------------------

    def beat(self):
        """Tell the web server we are alive.

        The website treats a stale heartbeat as a reason to report the critical interlock as
        being in alarm, so that a dead evaluator fails safe instead of freezing on its last
        known-good answer.
        """
        try:
            store.beat(self.db(), "watchtower")
        except Exception as e:
            log(f"ERROR could not write heartbeat: {e}")
