import os
from waitress import serve
import schedule
import time
from multiprocessing import Process
from thermometry.flaskr import create_app
from thermometry.alarm.Watchtower import Watchtower

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
    watch = Watchtower(config.TEAMS_WEBHOOK, config.SERVER_URL)
    watch.load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"))

    schedule.every(30).seconds.do(watch.lookout)
    schedule.every(10).seconds.do(watch.apply_changes)
    schedule.every(10).seconds.do(watch.log_status)

    while True:
        schedule.run_pending()
        time.sleep(1)


def run_all():
    """Run both the FQT website and alert subsystem"""
    a = Process(target=run_alerts, daemon=True)
    a.start()
    run_website()








