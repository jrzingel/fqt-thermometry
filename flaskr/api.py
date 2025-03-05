# Thermometry API methods


# Either GET from Javascript or Charizard (for data acquisition)
# Or POST from listener.py (for data collection)

# All API requests should be done using JSON

from flask import g
from apiflask import APIBlueprint, Schema
from apiflask.fields import Integer, String, Float, DateTime

from flaskr.db import get_db


bp = APIBlueprint("api", __name__, url_prefix="/api")


class TemperatureReadingSchema(Schema):
    timestamp = DateTime(required=True)
    temp = Float(required=True)
    fridge = String(required=True)
    sensor = String(required=True)


@bp.route("/v1/temp/get", methods=["GET"])
@bp.output(TemperatureReadingSchema)
def getTemperature():
    """Get the temperature of the given fridge device for the specified times."""
    return "GET"


@bp.route("/v1/temp/post")
@bp.input(TemperatureReadingSchema)
def setTemperature():
    """Upload temperature data for a given time from listener.py. Not publicly accessible."""
    return "POST"


