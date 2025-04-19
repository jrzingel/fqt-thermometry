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
        ORDER BY m.time DESC 
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
    times = List(Integer(), required=True)
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
        "times": df.index.values.tolist(),
        "readings": {fridge + "." + sensor: series.tolist() for (fridge, sensor), series in df.items()}
    }


class NewReadingSchema(Schema):
    """Schema for a single reading to upload"""
    time = DateTime(required=True)
    reading = Float(required=True)
    fridge = String(required=True)
    sensor = String(required=True)
    signature = String(required=True)  # HMAC signature of the message


# Authorization
def generate_signature(fridge: str, sensor: str, time: int, reading: float) -> str:
    """Generate the HMAC signature for a given reading"""
    secret = current_app.config["FRIDGE_KEYS"].get(fridge).encode()
    if not secret:
        return ""
    payload = f"{fridge}.{sensor}.{time}.{float(reading)}"
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


@bp.post("/v1/new")
@bp.input(NewReadingSchema)
@bp.doc(summary="Add a new reading for a given sensor. Cryptographically secure.")
def addReading(json_data: dict):
    """Upload temperature data for a given time from listener.py. Not publicly accessible."""
    db = get_db()
    time = int(json_data["time"].timestamp())
    print(time)

    # First, identify if the request is genuine
    signature = generate_signature(json_data["fridge"], json_data["sensor"], time, json_data["reading"])
    if not hmac.compare_digest(signature, json_data["signature"]):
        return abort(401, "Invalid signature. You are not authorized to upload data.")

    # Second, identify which table to use
    result = db.execute(
        """
        SELECT s.id AS sensor_id, s.latest
        FROM sensor s
        JOIN fridge f ON f.id = s.fridge_id
        WHERE s.name = ? AND f.name = ?;""",
        (json_data["sensor"], json_data["fridge"])
    ).fetchone()

    if not result:
        abort(404, f"No sensor '{json_data['sensor']}' found for fridge '{json_data['fridge']}'")
    sensor_id, latest_only = result

    if latest_only:
        # Add to the latest table
        try:
            db.execute("""
            INSERT INTO latest_reading (sensor_id, time, reading)
            VALUES (?, ?, ?)
            ON CONFLICT(sensor_id) DO UPDATE SET
                time = excluded.time,
                reading = excluded.reading;
            """, (sensor_id, time, json_data["reading"]))
            db.commit()
        except db.IntegrityError:
            return abort(500, "Duplicated data entry")
    else:
        # Add to historic readings table
        try:
            db.execute("""
            INSERT INTO measurement (time, sensor_id, reading) 
            VALUES (?, ?, ?)
            """, (time, sensor_id, json_data["reading"]))
            db.commit()
        except db.IntegrityError:
            return abort(500, "Duplicate data entry")
    return {"success": True}

