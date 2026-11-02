import os
import time
from multiprocessing import Process

import schedule
from waitress import serve

from thermometry.alarm.Watchtower import Watchtower
from thermometry.flaskr import create_app

try:
    from thermometry import config
except ImportError:
    raise RuntimeError("Missing config.py - copy config.example.py to config.py and edit it")


def run_website():
    """Run the FQT website using waitress"""
    print("Starting the website")
    app = create_app()
    serve(app, host='0.0.0.0', port=config.WEBSITE["port"], threads=config.WEBSITE["threads"])


def run_alerts():
    """Run the alert subsystem"""
    print("Starting the alerts")
    watch = Watchtower(config.TEAMS_WEBHOOK, getattr(config, "EXTERNAL_WEBSITE_URL", None))
    watch.load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))

    watch.lookout()  # Evaluate once at startup rather than waiting out the first interval
    schedule.every(30).seconds.do(watch.lookout)
    schedule.every(5).seconds.do(watch.apply_changes)

    while True:
        schedule.run_pending()
        time.sleep(1)


def _supervise_alerts():
    """Keep the alert subsystem running.

    It used to be spawned as a bare daemon process: if it died -- an unhandled exception from a
    single alert was enough -- nothing noticed and nothing restarted it, while the website carried
    on serving the last alert states it had written. Since those states gate the experimental
    interlock, a silent death was the worst possible failure. Now it comes back.
    """
    while True:
        try:
            run_alerts()
        except Exception as e:
            print(f"Alert subsystem crashed: {e!r}. Restarting in 30 seconds.", flush=True)
        else:
            print("Alert subsystem exited unexpectedly. Restarting in 30 seconds.", flush=True)
        schedule.clear()
        time.sleep(30)


def run_all():
    """Run both the FQT website and alert subsystem"""
    a = Process(target=_supervise_alerts, daemon=True)
    a.start()
    run_website()
