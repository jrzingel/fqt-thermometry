# Thermometry API methods
import sqlite3

# Either GET from Javascript or Charizard (for data acquisition)
# Or POST from listener.py (for data collection)

# All API requests should be done using JSON

from flask import g, request
from apiflask import APIBlueprint, Schema, abort
from apiflask.fields import Integer, String, Float, DateTime, Boolean, List, Dict
from apiflask.validators import OneOf
import random
from datetime import datetime
import math
import pandas as pd
import numpy as np
from functools import reduce


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


class RangedReadingSchema(Schema):
    """Schema for specifying a range of readings to return"""
    fridge = String(required=True)
    sensors = List(String())
    earliest_timestamp = DateTime(required=False)  # range of times. Ignored if latest flag is set
    latest_timestamp = DateTime(required=False)


# OUTPUTS

class DefaultResponseSchema(Schema):
    success = Boolean(required=True)


class RangedResponseSchema(Schema):
    timestamps = List(Integer(), required=True)
    fridge = String(required=True)
    readings = Dict(keys=String(), values=List(Float()), required=True)


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
        'SELECT * FROM temperatures WHERE fridge = ? AND sensor = ? ORDER BY timestamp DESC', (json_data["fridge"], json_data["sensor"])
    ).fetchone()

    if temp_row is None:
        abort(404, "No readings found")

    temp_row = dict(temp_row)
    del temp_row["id"]  # Internal use only. Don't expose to users
    return temp_row

# TODO: Return as {timestamps, readings} to make it easier to work with in javascript
# TODO: Add /v1/range/hour to return the latest of the past hour
@bp.post("/v1/range")
@bp.input(RangedReadingSchema)
@bp.output(RangedResponseSchema)
@bp.doc(summary="Get all readings for a sensor between two timestamps")
def getRangeOfReadings(json_data: dict):
    """Get a range of readings between two timestamps for a given sensor."""
    db = get_db()

    # Sanity checks of the input
    if json_data["earliest_timestamp"] > json_data["latest_timestamp"]:
        return abort(400, "Earliest timestamp must be before latest timestamp")

    raw_data = {}

    for sensor in json_data["sensors"]:
        reading_rows = db.execute(
            'SELECT * from temperatures WHERE fridge = ? AND sensor = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp',
            (json_data["fridge"], sensor, json_data["earliest_timestamp"], json_data["latest_timestamp"])
        ).fetchall()

        if reading_rows is None:
            reading_rows = []

        raw_data[sensor] = reading_rows

    # All results should use a common set of timestamps
    # -> Merge with Pandas
    # {timestamps: [...], readings: {sensor_name: [...], ...}

    df_list = []
    for sensor, reading_rows in raw_data.items():
        timestamps = []
        readings = []

        for row in reading_rows:
            r = dict(row)
            timestamps.append(r["timestamp"])
            readings.append(r["temp"])

        df = pd.DataFrame({
            'timestamp': timestamps, sensor: readings
        })
        df.set_index('timestamp', inplace=True)
        df_list.append(df)


    result = reduce(lambda left, right: pd.merge(left, right, left_on='timestamp', right_on='timestamp', how='outer'), df_list)

    # Convert timestamps from Nanoseconds since the epoch to standard Unix epoch (second)
    result.index = result.index.values.astype(np.int64) // 10**9

    return {
        "fridge": json_data["fridge"],
        "timestamps": result.index.values.tolist(),
        "readings": result.to_dict('list')
    }


@bp.post("/v1/random_range")
@bp.input(RangedReadingSchema)
@bp.output(RangedResponseSchema)
def getRandom(json_data: dict):
    """Return random readings"""
    n = 100
    start, end = int(json_data["earliest_timestamp"].timestamp()), int(json_data["latest_timestamp"].timestamp())
    timestamps = [random.randrange(start, end) for _ in range(n)]
    timestamps.sort()
    timestamps = [datetime.fromtimestamp(i) for i in timestamps]
    return {
        "readings": [random.random()] * n,
        "timestamps": timestamps,
        "fridge": json_data["fridge"],
        "sensor": json_data["sensor"],
    }


@bp.post("/v1/new")
@bp.input(ReadingSchema)
@bp.output(DefaultResponseSchema)
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

