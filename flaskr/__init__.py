# Root flask function

import logging
logging.getLogger('werkzeug').setLevel(logging.CRITICAL)  # disable werkzeug logging

import os
import traceback
from flask import url_for, redirect, request
import time
from apiflask import APIFlask
from . import db
from . import api
from . import dashboard


def create_app():
    """Application factory for creating the flask app"""
    logger = logging.getLogger("thermometry")

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

    @app.after_request
    def after_request(response):
        timestamp = time.strftime('[%Y-%b-%d %H:%M]')
        logger.error('%s %s "%s %s %s" %s', timestamp, request.remote_addr, request.method, request.full_path, request.scheme, response.status)
        return response

    return app

