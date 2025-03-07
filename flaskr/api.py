# Thermometry API methods
import sqlite3

# Either GET from Javascript or Charizard (for data acquisition)
# Or POST from listener.py (for data collection)

# All API requests should be done using JSON

from flask import g, request
from apiflask import APIBlueprint, Schema, abort
from apiflask.fields import Integer, String, Float, DateTime, Boolean, List
from apiflask.validators import OneOf

from flaskr.db import get_db


bp = APIBlueprint("api", __name__, url_prefix="/api")


# INPUTS

class ReadingSchema(Schema):
    """Schema for a single reading to upload"""
    timestamp = DateTime(required=True)
    temp = Float(required=True)
    fridge = String(required=True)
    sensor = String(required=True)
    #type = String(required=True, validate=OneOf(["temperature", "pressure"]))


class LatestReadingSchema(Schema):
    """Schema for returning the latest reading"""
    fridge = String(required=True)
    sensor = String(required=True)
    #type = String(required=True, validate=OneOf(["temperature", "pressure"]))


class RangedReadingSchema(LatestReadingSchema):
    """Schema for specifying a range of readings to return"""
    earliest_timestamp = DateTime(required=False)  # range of times. Ignored if latest flag is set
    latest_timestamp = DateTime(required=False)


# OUTPUTS

class DefaultResponseSchema(Schema):
    success = Boolean(required=True)


@bp.get("/v1/ping")
@bp.doc(summary="Ping that the API server is active")
def ping():
    return {"response": "pong"}


@bp.post("/v1/latest")
@bp.input(LatestReadingSchema)
@bp.output(ReadingSchema)
@bp.doc(summary="Get the latest reading for a particular sensor")
def getLatestReading(json_data: dict):
    """Get the latest reading of the given sensor."""
    db = get_db()
    temp_row = db.execute(
        'SELECT * FROM temperatures  WHERE fridge = ? AND sensor = ? ORDER BY timestamp DESC', (json_data["fridge"], json_data["sensor"])
    ).fetchone()

    if temp_row is None:
        abort(404, "No readings found")

    temp_row = dict(temp_row)
    del temp_row["id"]  # Internal use only. Don't expose to users
    return temp_row


@bp.post("/v1/range")
@bp.input(RangedReadingSchema)
#@bp.output(ManyReadingSchema)
@bp.doc(summary="Get all readings for a sensor between two timestamps")
def getRangeOfReadings(json_data: dict):
    """Get a range of readings between two timestamps for a given sensor."""
    db = get_db()

    # Sanity checks of the input
    if json_data["earliest_timestamp"] > json_data["latest_timestamp"]:
        return abort(400, "Earliest timestamp must be before latest timestamp")

    reading_rows = db.execute(
        'SELECT * from temperatures WHERE fridge = ? AND sensor = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp',
        (json_data["fridge"], json_data["sensor"], json_data["earliest_timestamp"], json_data["latest_timestamp"])
    ).fetchall()

    if reading_rows is None:
        return abort(404, "No readings found")

    rows = []
    for row in reading_rows:
        r = dict(row)
        del r["id"]
        rows.append(r)
    return {"readings": rows}



@bp.post("/v1/new")
@bp.input(ReadingSchema)
@bp.output(DefaultResponseSchema)
@bp.doc(summary="Add a new reading for a given sensor")
def addReading(json_data: dict):
    """Upload temperature data for a given time from listener.py. Not publicly accessible."""
    print(json_data)
    db = get_db()
    fridge = json_data["fridge"]
    sensor = json_data["sensor"]
    temp = json_data["temp"]
    timestamp = json_data["timestamp"]

    # TODO: Add validation that this is a known fridge and sensor

    try:
        db.execute(
            "INSERT INTO temperatures (timestamp, fridge, sensor, temp) VALUES (?, ?, ?, ?)",
            (timestamp, fridge, sensor, temp),
        )
        db.commit()
    except db.IntegrityError:
        return abort(500, "Duplicate data entry")
    return {"success": True}




