# HTML/CSS template renderer methods

import os
from flask import Blueprint, render_template, request, current_app, jsonify, abort
import time
import json

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
def dashboard():
    fridge = request.args.get('fridge', type=str)
    data_type = request.args.get('type', type=str)
    showPressures = data_type == "pressures"

    if fridge is None:
        # Render all the fridges at once
        return render_template("combined_dashboard.html", title="Fridge Status", url=request.url_root)
    else:
        # Render just one fridge
        return render_template("dashboard.html", fridge=fridge, title=f"{fridge.title()} Fridge Status", url=request.url_root, showPressures=showPressures)


@bp.post("/alerts/action")
def action_alert():
    # Apply the action of enabling or disabling the alert
    action = request.get_json()

    splits = action["value"].split(".")
    if len(splits) != 2:
        return "Unknown action type", 500

    alertType = splits[0]
    fridge = splits[1]
    state = "MANUALLY_DISABLED" if action["checked"] else "DISABLED"

    # Write the update to the log file for the alert code to read and process it
    if os.path.getsize(current_app.config["ALERT_CHANGE_PATH"]) > 0:
        with open(current_app.config["ALERT_CHANGE_PATH"], "r") as f:
            current_changes = json.load(f)  # Get current changes requested
    else:
        current_changes = []

    with open(current_app.config["ALERT_CHANGE_PATH"], "w") as f:
        f.write(json.dumps(current_changes + [{  # Add our change
            "type": alertType,
            "fridge": fridge,
            "action": state
        }]))
    time.sleep(2)  # Wait for dramatic effect
    return '', 204


@bp.route("/alerts")
def view_alerts():
    # Display the alert view
    # Load JSON from disk
    with open(current_app.config["ALERT_PATH"], 'r') as f:
        status = json.load(f)

    return render_template("alerts.html", alerts=status["alerts"], last_updated=status["last_updated"])


@bp.route("/alerts/<string:alert_type>.json")
def view_alert(alert_type: str):
    # Load JSON from disk
    with open(current_app.config["ALERT_PATH"], 'r') as f:
        status = json.load(f)

    if "alerts" not in status.keys() or "last_updated" not in status.keys():
        return "Alerts are not available", 500

    alerts = []
    for alert in status["alerts"]:
        if alert["type"] == alert_type or alert_type == "all":
            alerts.append(alert)
    return jsonify({
        "alerts": alerts,
        "last_updated": status["last_updated"]
    })
