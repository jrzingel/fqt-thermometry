# HTML/CSS template renderer methods

import os
from apiflask import APIBlueprint, Schema, fields
from flask import render_template, request, current_app, jsonify, abort
import time
import json
from thermometry import config

bp = APIBlueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
@bp.doc(summary="Get HTML page of the dashboard with javascript charts")
def dashboard():
    fridge = request.args.get('fridge', type=str)
    data_type = request.args.get('type', type=str)
    showPressures = data_type == "pressures"

    if fridge is None:
        # Render all the fridges at once
        return render_template("combined_dashboard.html", fridges=config.SIDEBAR_FRIDGES, menu="all", title="Fridge Status", url=config.EXTERNAL_WEBSITE_URL)
    else:
        # Render just one fridge
        return render_template("dashboard.html", fridges=config.SIDEBAR_FRIDGES, menu=fridge, title=f"{fridge.title()} Fridge Status", url=config.EXTERNAL_WEBSITE_URL, showPressures=showPressures)


class DisabledSchema(Schema):
    """Schema for requesting an alert to be disabled or not"""
    name = fields.String(required=False)
    value = fields.String(required=True)
    checked = fields.Boolean(required=False)


@bp.post("/alerts/action")
@bp.input(DisabledSchema)
@bp.doc(summary="Process an alert status change to be manually disabled or not. This is submitted by the HTML form")
def action_alert(json_data):
    # Apply the action of enabling or disabling the alert
    splits = json_data["value"].split(".")
    if len(splits) != 2:
        return "Unknown action type", 500

    alertType = splits[0]
    fridge = splits[1]
    state = "MANUALLY_DISABLED" if json_data["checked"] else "DISABLED"

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
@bp.doc(summary="Get a HTML page of all the alerts")
def view_alerts():
    # Display the alert view
    # Load JSON from disk
    with open(current_app.config["ALERT_PATH"], 'r') as f:
        status = json.load(f)

    return render_template("alerts.html", fridges=config.SIDEBAR_FRIDGES, menu="alerts", alerts=status["alerts"], last_updated=status["last_updated"])


@bp.get("/alerts/<string:alert_type>.json")
@bp.doc(summary="Get JSON status for a specific type of alert. Use 'all' to get all alerts")
def view_alert(alert_type: str):
    # Load JSON from disk
    with open(current_app.config["ALERT_PATH"], 'r') as f:
        try:
            status = json.load(f)
        except json.decoder.JSONDecodeError:
            print("Failed to decode JSON. Waiting a second")
            time.sleep(1.0)
            status = json.load(f)  # Give it half a second for file writes, then try again

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


@bp.route("/gauges")
@bp.doc(summary="Get HTML page of fridge gauges")
def gauges():
        return render_template("gauges.html", fridges=config.SIDEBAR_FRIDGES, menu="gauges", title="Gauges", url=config.EXTERNAL_WEBSITE_URL)
