# HTML/CSS template renderer methods

from flask import Blueprint

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

@bp.route("/")
def dashboard():
    return "Hey there this is the dashboard"
