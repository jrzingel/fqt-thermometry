# HTML/CSS template renderer methods

from flask import Blueprint, render_template, request

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

@bp.route("/")
def dashboard():
    fridge = request.args.get('fridge', type=str)
    pretty_fridge = "" if fridge is None else fridge.title()
    return render_template("dashboard.html", fridge=fridge, pretty_fridge=pretty_fridge)


