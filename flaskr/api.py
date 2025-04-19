# Thermometry API methods
import sqlite3

# Either GET from Javascript or Charizard (for data acquisition)
# Or POST from listener.py (for data collection)

# All API requests should be done using JSON

from flask import g, request, current_app
from apiflask import APIBlueprint, Schema, abort
from apiflask.fields import Integer, String, Float, DateTime, Boolean, List, Dict
import pandas as pd
import numpy as np
from functools import reduce
from datetime import datetime, timezone
import hmac
import hashlib


from flaskr.db import get_db, fetch_readings


bp = APIBlueprint("api", __name__, url_prefix="/api")


# Authorization
def is_valid_signature(fridge: str, payload: dict, signature: str) -> bool:
    """Check if the HMAC signature of the message is valid"""
    secret = current_app.config["FRIDGE_KEYS"].get(fridge)
    if not secret:
        return False
    expected_sig = hmac.new(secret, str(payload).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


@bp.get("/v1/ping")
@bp.doc(summary="Ping that the API server is active")
def ping():
    return {"response": "pong"}


# Latest reading
class LatestReadingSchema(Schema):
    """Schema for returning the latest reading"""
    fridge = String(required=True)
    sensor = String(required=True)


class SingleReadingSchema(Schema):
    """Schema for returning a single reading"""
    time = DateTime(required=True)
    fridge = String(required=True)
    sensor = String(required=True)
    reading = Float(required=True)


@bp.get("/v1/latest")
@bp.input(LatestReadingSchema, location="query")
@bp.output(SingleReadingSchema)
@bp.doc(summary="Get the latest reading for a particular sensor. This is the only endpoint that can be used to fetch non-historical readings.")
def getLatestReading(query_data: dict):
    """Get the latest reading of a given sensor."""
    db = get_db()
    # First, identify which table to use
    result = db.execute(
        """
        SELECT s.id AS sensor_id, s.latest
        FROM sensor s
        JOIN fridge f ON f.id = s.fridge_id
        WHERE s.name = ? AND f.name = ?;""",
        (query_data["sensor"], query_data["fridge"])
    ).fetchone()

    if not result:
        abort(404, f"No sensor {query_data['sensor']} found")
    sensor_id, latest_only = result

    # Switch based on what table to use
    if latest_only:
        result = db.execute("""
        SELECT lr.time, lr.reading
        FROM latest_reading lr
        WHERE lr.sensor_id = ?
        """, (sensor_id,)).fetchone()
    else:
        result = db.execute("""
        SELECT m.time, m.reading
        FROM measurement m
        WHERE m.sensor_id = ?
        ORDER BY m.time
        """, (sensor_id,)).fetchone()
    if result:
        time, reading = result
        return {
            "time": datetime.fromtimestamp(time, timezone.utc),
            "fridge": query_data["fridge"],
            "sensor": query_data["sensor"],
            "reading": reading,
        }
    abort(404, f"No data for {query_data['fridge']}.{query_data['sensor']} found")


class RangedReadingSchema(Schema):
    """Schema for specifying a range of readings to return"""
    fridge = String(required=True)
    sensors = List(String(), required=True)
    earliest_timestamp = DateTime(required=True)
    latest_timestamp = DateTime(required=True)

class RangedResponseSchema(Schema):
    times = List(Integer(), required=True)
    fridge = String(required=True)
    readings = Dict(keys=String(), values=List(Float()), required=True)


@bp.post("/v1/range")
@bp.input(RangedReadingSchema)
@bp.output(RangedResponseSchema)
@bp.doc(summary="Get all readings for some sensors between two timestamps on one fridge")
def getRangeOfReadings(json_data: dict):
    """Get a range of readings between two timestamps for some given sensors."""
    # Sanity checks of the input
    if json_data["earliest_timestamp"] > json_data["latest_timestamp"]:
        return abort(400, "Earliest timestamp must be before latest timestamp")

    earliest = int(json_data["earliest_timestamp"].timestamp())
    latest = int(json_data["latest_timestamp"].timestamp())

    df = fetch_readings([(json_data["fridge"], s) for s in json_data["sensors"]], earliest, latest)

    # Convert NaN to null
    df = df.replace({np.nan: None})

    return {
        "fridge": json_data["fridge"],
        "times": df.index.values.tolist(),
        "readings": {sensor: series.tolist() for (fridge, sensor), series in df.items()},
    }


class MultipleFridgeReadingSchema(Schema):
    """Schema for specifying a sensor from multiple fridges to return"""
    query = List(List(String()), required=True)  # [[fridge, sensor], ...]
    earliest_timestamp = DateTime(required=False)
    latest_timestamp = DateTime(required=False)


class MultipleFridgeResponseSchema(Schema):
    timestamps = List(Integer(), required=True)
    readings = Dict(keys=String(), values=List(Float()), required=True)  # {fridge.sensor: [readings]}


@bp.post("/v1/fridges")
@bp.input(MultipleFridgeReadingSchema)
@bp.output(MultipleFridgeResponseSchema)
@bp.doc(summary="Get all readings from multiple fridges for some given sensors between two timestamps")
def getMultipleFridgeReadings(json_data: dict):
    """Get a range of readings between two timestamps for a given sensor on each fridge. Truncate the seconds."""
    db = get_db()

    # Sanity checks of the input
    if json_data["earliest_timestamp"] > json_data["latest_timestamp"]:
        return abort(400, "Earliest timestamp must be before latest timestamp")

    earliest = int(json_data["earliest_timestamp"].timestamp())
    latest = int(json_data["latest_timestamp"].timestamp())

    df = fetch_readings([(q[0], q[1]) for q in json_data["query"]], earliest, latest)

    # Convert NaN to null
    df = df.replace({np.nan: None})

    return {
        "timestamps": df.index.values.tolist(),
        "readings": {fridge + "." + sensor: series.tolist() for (fridge, sensor), series in df.items()}
    }

class NewReadingSchema(Schema):
    """Schema for a single reading to upload"""
    timestamp = DateTime(required=True)
    temp = Float(required=True)
    fridge = String(required=True)
    sensor = String(required=True)


@bp.post("/v1/new")
@bp.input(NewReadingSchema)
@bp.doc(summary="Add a new reading for a given sensor")
def addReading(json_data: dict):
    """Upload temperature data for a given time from listener.py. Not publicly accessible."""
    #print(json_data)
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

