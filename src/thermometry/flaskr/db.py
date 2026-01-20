# Methods for controlling the SQLite DB

import click
import numpy as np
import pandas as pd
import psycopg2
from flask import current_app, g


def get_db():
    """Return the current database connection"""
    if 'db' not in g:
        g.db = psycopg2.connect(**current_app.config["DATABASE"])
    return g.db


def close_db(e=None):
    """Close the current database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialise the database with the appropriate schema. THIS RESETS ALL DATA STORED."""
    db = get_db()
    cur = db.cursor()
    with current_app.open_resource('schema.sql', mode='r') as f:
        cur.execute(f.read())
    db.commit()
    cur.close()



def add_fridge(name: str) -> int:
    """Add a new fridge to the database"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO fridge (name)
        VALUES (%s)
        RETURNING id
        """, (name,))
    f_id = cursor.fetchone()[0]
    db.commit()
    cursor.close()
    return f_id


def add_sensor(name: str, fridge_id: int, latest=0) -> int:
    """Add a new sensor to the database"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO sensor (name, fridge_id, latest)
        VALUES (%s, %s, %s)
        RETURNING id
        """, (name, fridge_id, latest))
    s_id = cursor.fetchone()[0]
    db.commit()
    cursor.close()
    return s_id


def create_default_fridges():
    """Create the default fridges and associated sensors"""
    fridges = ["queenie", "scarlett", "tallulah", "ursula", "venus", "winona"]
    sensors = ["50K", "4K", "magnet", "still", "mxc", "P1", "P2", "P3", "P4", "P5", "P6"]
    latest_sensors = ["pulse_on", "oil_temp", "water_in", "water_out", "flow", "turbo_speed"]
    for fridge in fridges:
        f_id = add_fridge(fridge)
        print(fridge, f_id)
        for sensor in sensors:
            add_sensor(sensor, f_id, False)
        for sensor in latest_sensors:
            add_sensor(sensor, f_id, True)
            
    winona2_id = add_fridge("winona2")
    for sensor in ["pulse_on", "oil_temp", "water_temp"]:  # We only need the compressor settings
        add_sensor(sensor, winona2_id, True)


def create_dummy_data():
    """Create some dummy data to test the API with"""
    import random
    from datetime import datetime, timezone

    db = get_db()
    cur = db.cursor()
    now = int(datetime.now(timezone.utc).timestamp())

    # Do historic data
    n = 201
    cur.execute("SELECT id FROM sensor WHERE latest=false;")
    sensors = cur.fetchall()
    times = np.linspace(now - 3 * 24 * 60 * 60, now, n)
    times = [datetime.fromtimestamp(t) for t in times]  # Convert to datetime object
    for _id in sensors:
        scale = 1e-4
        id = _id[0]
        i = 500.0 * scale
        vals = []
        for _ in range(n):
            i += random.gauss(0, 10) * scale
            i = max(scale / 20, i)
            vals.append(i)
        # Randomly set some values to null to test graphing later
        inx = np.random.randint(0, n, size=(n // 4))
        vals = np.delete(vals, inx)
        times_ = np.delete(times.copy(), inx)
        tuples = [(t, id, r) for t, r in zip(times_, vals.astype(float).tolist())]
        cur.executemany(
            'INSERT INTO measurement (time, sensor_id, reading) VALUES (%s, %s, %s);', tuples
        )

    # Do latest data
    cur.execute("SELECT id FROM sensor WHERE latest=true;")
    sensors = cur.fetchall()
    for _id in sensors:
        id = _id[0]
        val = random.gauss(0, 10)
        cur.execute(
            'INSERT INTO latest_reading (time, sensor_id, reading) VALUES (%s, %s, %s)', (datetime.fromtimestamp(now), id, val)
        )

    db.commit()
    cur.close()


def fetch_readings(query: list[tuple], earliest_stamp: int, latest_stamp: int, bin: int =1) -> pd.DataFrame:
    """Fetch all sensor readings between timestamps for the given  fridge/sensor querys. Combine times into multiples of bin"""
    # query should be of the form: [("fridge", "sensor"), ("fridge", "sensor"), ... ]
    db = get_db()
    cur = db.cursor()

    # Build dynamic WHERE clause
    WHERE_clause = " OR ".join([f"(f.name = %s AND s.name = %s)" for _ in query])
    cur.execute(f"""
    SELECT f.name AS fridge, s.name AS sensor, m.time, m.reading
    FROM measurement m
    JOIN sensor s ON m.sensor_id = s.id
    JOIN fridge f ON s.fridge_id = f.id
    WHERE ({WHERE_clause})
    AND m.time BETWEEN %s AND %s
    ORDER BY m.time
    """, [v for pair in query for v in pair] + [earliest_stamp, latest_stamp])
    result = cur.fetchall()
    cur.close()

    # Pivot records together so that they share the same time axis
    df = pd.DataFrame.from_records(result, columns=['fridge', 'sensor', 'time', 'reading'])
    df['time'] = pd.to_datetime(df['time'], utc=True)  # Force datetime object for daylight savings
    df['time'] = df['time'].astype('int64') // 10**9  # Convert datetime objects to unix timestamp
    df['time'] = (df['time'] // bin) * bin

    grouped = df.groupby(['time', 'fridge', 'sensor'])['reading'].first().unstack(['fridge', 'sensor'])

    # Ensure all requested columns are present
    grouped = grouped.reindex(columns=pd.MultiIndex.from_tuples(query), fill_value=None)
    return grouped


def fetch_latest_readings(query: list[tuple]) -> pd.DataFrame:
    """Fetch the latest sensor readings for the given fridge/sensor querys"""
    # query should be of the form: [("fridge", "sensor"), ("fridge", "sensor"), ... ]
    db = get_db()
    cur = db.cursor()

    # Build dynamic WHERE clause
    WHERE_clause = " OR ".join([f"(f.name = %s AND s.name = %s)" for _ in query])
    cur.execute(f"""
    SELECT f.name AS fridge, s.name AS sensor, lr.time, lr.reading
    FROM latest_reading lr
    JOIN sensor s ON lr.sensor_id = s.id
    JOIN fridge f ON s.fridge_id = f.id
    WHERE ({WHERE_clause})
    """, [v for pair in query for v in pair])
    result = cur.fetchall()
    cur.close()

    # Pivot records together so that they share the same time axis
    df = pd.DataFrame.from_records(result, columns=['fridge', 'sensor', 'time', 'reading'])
    df['time'] = pd.to_datetime(df['time'], utc=True)  # Force datetime object for daylight savings
    return df


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

