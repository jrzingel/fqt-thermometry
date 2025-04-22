# Methods for controlling the SQLite DB

import sqlite3
from datetime import datetime, timedelta, UTC
import click
import numpy as np
import pandas as pd

from flask import current_app, g


def get_db():
    """Return the current database connection"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    """Close the current database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialise the database with the appropriate schema. THIS RESETS ALL DATA STORED."""
    db = get_db()
    with current_app.open_resource('schema.sql', mode='r') as f:
        db.executescript(f.read())  # Setup tables


def add_fridge(name: str) -> int:
    """Add a new fridge to the database"""
    db = get_db()
    cursor = db.cursor()
    result = cursor.execute("""
        INSERT INTO fridge (name)
        VALUES (?)
        """, (name,))
    db.commit()
    return cursor.lastrowid


def add_sensor(name: str, fridge_id: int, latest=0) -> int:
    """Add a new sensor to the database"""
    db = get_db()
    cursor = db.cursor()
    result = cursor.execute("""
        INSERT INTO sensor (name, fridge_id, latest)
        VALUES (?, ?, ?)
        """, (name, fridge_id, latest))
    db.commit()
    return cursor.lastrowid


def create_default_fridges():
    """Create the default fridges and associated sensors"""
    fridges = ["queenie", "scarlett", "tallulah", "ursula", "venus", "winona"]
    sensors = ["50K", "4K", "magnet", "still", "mxc", "P1", "P2", "P3", "P4", "P5", "P6"]
    latest_sensors = ["pulse_on", "flow", "oil_temp"]
    for fridge in fridges:
        f_id = add_fridge(fridge)
        for sensor in sensors:
            add_sensor(sensor, f_id, 0)
        for sensor in latest_sensors:
            add_sensor(sensor, f_id, 1)


def create_dummy_data():
    """Create some dummy data to test the API with"""
    import random
    from datetime import datetime, timezone

    db = get_db()
    now = int(datetime.now(timezone.utc).timestamp())

    # Do historic data
    n = 201
    sensors = db.execute("SELECT id FROM sensor WHERE latest=0").fetchall()
    times = np.linspace(now - 3 * 24 * 60 * 60, now, n)
    for _id in sensors:
        id = _id[0]
        i = 500.0
        vals = []
        for _ in range(n):
            i += random.gauss(0, 10)
            i = max(0.01, i)
            vals.append(i)
        # Randomly set some values to null to test graphing later
        inx = np.random.randint(0, n, size=(n // 4))
        vals = np.delete(vals, inx)
        times_ = np.delete(times.copy(), inx)
        tuples = [(t, id, r) for t, r in zip(times_, vals)]
        db.executemany(
            'INSERT INTO measurement (time, sensor_id, reading) VALUES (?, ?, ?)', tuples
        )

    # Do latest data
    sensors = db.execute("SELECT id FROM sensor WHERE latest=1").fetchall()
    for _id in sensors:
        id = _id[0]
        val = random.gauss(0, 10)
        db.execute(
            'INSERT INTO latest_reading (time, sensor_id, reading) VALUES (?, ?, ?)', (now, id, val)
        )

    db.commit()


def fetch_readings(query: list[tuple], earliest_stamp: int, latest_stamp: int, bin: int =1) -> pd.DataFrame:
    """Fetch all sensor readings between timestamps for the given  fridge/sensor querys. Combine times into multiples of bin"""
    # query should be of the form: [("fridge", "sensor"), ("fridge", "sensor"), ... ]
    db = get_db()

    # Build dynamic WHERE clause
    WHERE_clause = " OR ".join([f"(f.name = ? AND s.name = ?)" for _ in query])
    result = db.execute(f"""
    SELECT f.name AS fridge, s.name AS sensor, m.time, m.reading
    FROM measurement m
    JOIN sensor s ON m.sensor_id = s.id
    JOIN fridge f ON s.fridge_id = f.id
    WHERE ({WHERE_clause})
    AND m.time BETWEEN ? AND ?
    ORDER BY m.time
    """, [v for pair in query for v in pair] + [earliest_stamp, latest_stamp]).fetchall()

    df = pd.DataFrame(result, columns=['fridge', 'sensor', 'time', 'reading'])
    df['time'] = (df['time'] // bin) * bin  # bin the times

    #df["fridge_sensor"] = df["fridge"] + "_" + df["sensor"]
    pivoted = df.pivot(index='time', columns=['fridge', 'sensor'], values='reading')

    # Make sure that all the request parameters are full (even if there is no data)
    for (f, s) in query:
        col = (f, s)
        if col not in pivoted.columns:
            pivoted[col] = None
    return pivoted.sort_index(axis=1)


@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Initialized the database.')


@click.command('create-default-fridges')
def create_default_fridges_command():
    init_db()
    create_default_fridges()
    click.echo('Created default fridges.')


@click.command('create-dummy-data')
def create_dummy_data_command():
    init_db()
    create_default_fridges()
    create_dummy_data()
    click.echo('Created dummy data.')


@click.command('add-fridge')
@click.argument('fridge_name')
def add_fridge_command(fridge_name):
    id = add_fridge(fridge_name)
    click.echo(f"Generated fridge ID = {id}")


@click.command('add-sensor')
@click.argument('sensor_name')
@click.argument('fridge_id')
@click.argument('latest', default=0)
def add_sensor_command(sensor_name, fridge_id, latest):
    id = add_sensor(sensor_name, fridge_id, latest)
    click.echo(f"Generated sensor ID = {id}")


def init_app(app):
    """Initialise the app with database knowledge"""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_default_fridges_command)
    app.cli.add_command(create_dummy_data_command)
    app.cli.add_command(add_fridge_command)
    app.cli.add_command(add_sensor_command)

