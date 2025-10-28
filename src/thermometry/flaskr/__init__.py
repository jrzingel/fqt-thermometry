# Root flask function

import logging
logging.getLogger('werkzeug').setLevel(logging.CRITICAL)  # disable werkzeug logging

import os
from flask import url_for, redirect, request
import time
from apiflask import APIFlask
import mimetypes
from thermometry.flaskr import db, api, dashboard
from thermometry import config


def create_app():
    """Application factory for creating the flask app"""
    logger = logging.getLogger("thermometry")
    logger.setLevel(logging.INFO)

    mimetypes.add_type("image/webp", ".webp")

    app = APIFlask(__name__, instance_relative_config=True, title="FQT Lab Thermometry", version='1.0')

    app.config.from_object(config)

    # Load database
    db.init_app(app)

    # Load blueprints
    app.register_blueprint(api.bp)
    app.register_blueprint(dashboard.bp)

    @app.route("/")
    @app.doc(hide=True)
    def root():
        return redirect(url_for("dashboard.dashboard"))

    @app.after_request
    def after_request(response):
        timestamp = time.strftime('[%Y-%b-%d %H:%M]')

        # Determine origin IP
        if request.headers.getlist("X-Forwarded-For"):
            # If behind a reverse proxy (nginx)
            ip = request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
        elif request.headers.get("X-Real-IP"):
            ip = request.headers.get("X-Real-IP")
        else:
            # fallback — direct client connection
            ip = request.remote_addr or "unknown"

        logger.info('%s %s "%s %s %s" %s', timestamp, ip, request.method, request.full_path, request.scheme.upper(), response.status)
        return response

    return app

