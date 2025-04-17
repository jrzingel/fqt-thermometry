# HTML/CSS template renderer methods

from flask import Blueprint, render_template, request

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


