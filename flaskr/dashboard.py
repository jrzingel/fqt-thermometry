# HTML/CSS template renderer methods

from flask import Blueprint, render_template, request, current_app
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


@bp.route("/alerts")
def view_alerts():
    # Load JSON from disk
    with open(current_app.config["ALERT_PATH"], 'r') as f:
        status = json.load(f)

    return render_template("alerts.html", alerts=status["alerts"], last_updated=status["last_updated"])