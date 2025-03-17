# Root flask function

import os
from flask import url_for, redirect
from apiflask import APIFlask
from . import db
from . import api
from . import dashboard


def create_app():
    """Application factory for creating the flask app"""
    app = APIFlask(__name__, instance_relative_config=True, title="FQT Lab Thermometry", version='1.0')

    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE=os.path.join(app.instance_path, "flaskr.sqlite"),
    )

    # Load config
    #app.config.from_pyfile("config.py", silent=False)

    # Check folders exist
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Load database
    db.init_app(app)

    # Load blueprints
    app.register_blueprint(api.bp)
    app.register_blueprint(dashboard.bp)

    @app.route("/")
    def hello():
        return redirect(url_for("dashboard.dashboard"))

    return app

