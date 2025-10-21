# -*- coding: utf-8 -*-
"""
Created on Mon Apr 21 13:29 2025

Script to migrate the SQLite database from old to new formats

@author: james
"""

import sqlite3
from datetime import datetime


old_db_path = "instance/flaskr_old.sqlite"
new_db_path = "instance/flaskr.sqlite"


old_db = sqlite3.connect(old_db_path, detect_types=sqlite3.PARSE_DECLTYPES)
old_db.row_factory = sqlite3.Row

new_db = sqlite3.connect(new_db_path, detect_types=sqlite3.PARSE_DECLTYPES)
new_db.row_factory = sqlite3.Row

sqlite3.register_converter(
    'timestamp', lambda v: datetime.fromisoformat(v.decode())
)

def get_old_reading(fridge: str, sensor: str):
    readings = old_db.execute("""
    SELECT *
    FROM temperatures
    WHERE fridge = ? AND sensor = ?""", (fridge, sensor)).fetchall()
    return readings


def add_new_reading(sensor_id: int, latest_only: bool, time: int, reading: float):
    #  Copied from /new
    if latest_only:
        # Add to the latest table
        new_db.execute("""
        INSERT INTO latest_reading (sensor_id, time, reading)
        VALUES (?, ?, ?)
        ON CONFLICT(sensor_id) DO UPDATE SET
            time = excluded.time,
            reading = excluded.reading;
        """, (sensor_id, time, reading))
    else:
        # Add to historic readings table
        try:
            new_db.execute("""
            INSERT INTO measurement (time, sensor_id, reading) 
            VALUES (?, ?, ?)
            """, (time, sensor_id, reading))
        except new_db.IntegrityError:
            #print(f"Duplicate data entry: {time}, {sensor_id}, {reading}")
            # This is usually from daylight savings... which I don't care about
            return


FRIDGES = ["queenie", "scarlett", "venus", "tallulah", "winona"]
SENSORS = ["P1", "P2", "P3", "P4", "P5", "P6", "50K", "4K", "magnet", "still", "mxc"]

for fridge in FRIDGES:
    for sensor in SENSORS:
        print(f"Migrating {fridge} on {sensor}", end="")
        results = get_old_reading(fridge, sensor)
        readings = [dict(r) for r in results]
        divs = len(readings) // 10
        i = 0

        # Determine the type of sensor
        result = new_db.execute(
            """
            SELECT s.id AS sensor_id, s.latest
            FROM sensor s
            JOIN fridge f ON f.id = s.fridge_id
            WHERE s.name = ? AND f.name = ?;""",
            (sensor, fridge)
        ).fetchone()

        if not result:
            print("Unknown sensor or fridge")
            continue

        sensor_id, latest_only = result
        for reading in readings:
            if reading != 0.0:
                time = reading["timestamp"].timestamp()
                add_new_reading(sensor_id, latest_only, time, reading["temp"])
            i += 1
            if i > divs:
                print(".", end="")
                i = 0
        
        new_db.commit()
        
        print()
