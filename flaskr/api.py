# Thermometry API methods


# Either GET from Javascript or Charizard (for data acquisition)
# Or POST from listener.py (for data collection)

# All API requests should be done using JSON

from flask import g, request
from apiflask import APIBlueprint, Schema, abort
from apiflask.fields import Integer, String, Float, DateTime, Boolean

from flaskr.db import get_db


bp = APIBlueprint("api", __name__, url_prefix="/api")


class TemperatureReadingSchema(Schema):
    """Schema for a single temperature reading"""
    timestamp = DateTime(required=True)
    temp = Float(required=True)
    fridge = String(required=True)
    sensor = String(required=True)


class TemperatureRequestSchema(Schema):
    """Schema for a temperature reading request"""
    fridge = String(required=True)
    sensor = String(required=True)
    earliest_timestamp = DateTime(required=False)
    latest_timestamp = DateTime(required=False)
    latest = Boolean(required=False, default=True)
    single = Boolean(required=False, default=True)


class DefaultResponseSchema(Schema):
    timestamp = DateTime(required=True)
    success = Boolean(required=True)


@bp.post("/v1/temp/latest")
@bp.input(TemperatureRequestSchema)
@bp.output(TemperatureReadingSchema)
def getTemperature(json_data: dict):
    """Get the temperature of the given fridge device for the specified times."""
    db = get_db()
    if json_data["single"]:  # Just get the last reading
        temp_row = db.execute(
            'SELECT * FROM temperatures WHERE fridge = ? AND sensor = ?', (json_data["fridge"], json_data["sensor"])
        ).fetchone()

        if temp_row is None:
            abort(404, "No temperatures found")

        temp_row = dict(temp_row)
        del temp_row["id"]  # Internal only
        reading = TemperatureReadingSchema(**temp_row)
        print(reading)
        return reading
    else:
        abort(501, "Not implemented")



@bp.post("/v1/temp/post")
@bp.input(TemperatureReadingSchema)
def setTemperature(json_data: dict):
    """Upload temperature data for a given time from listener.py. Not publicly accessible."""
    print(json_data)
    db = get_db()
    fridge = json_data["fridge"]
    sensor = json_data["sensor"]
    temp = json_data["temp"]
    timestamp = json_data["timestamp"]

    try:
        db.execute(
            "INSERT INTO temperatures (time, fridge, sensor, temp) VALUES (?, ?, ?, ?)",
            (timestamp, fridge, sensor, temp),
        )
        db.commit()
    except db.IntegrityError:
        error = "Duplicate entry"
    else:
        error = "success"
    return {"success": True, "error": error}




