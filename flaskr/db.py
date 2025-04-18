# Methods for controlling the SQLite DB

import sqlite3
from datetime import datetime, timedelta, UTC
import click
import numpy as np

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


def create_dummy_data():
    """Create some dummy data to test the API with"""
    import random
    from datetime import datetime

    db = get_db()
    # db.executemany(
    #     'INSERT INTO fridges (name) VALUES (?)', [("fridge1",), ("fridge2",)]
    # )
    # db.executemany(
    #     'INSERT INTO sensors (fridge, name) VALUES (?, ?) ', [("fridge1", "s1"), ("fridge1", "s2"), ("fridge1", "s3")]
    # )
    for fridge in ["queenie", "scarlett", "tallulah", "ursula", "venus"]:
        for sensor in ["50K", "4K", "magnet", "still", "mxc"]:
            n = 100
            # Gaussian noise data
            random_values = []
            i = 1.0
            for _ in range(n):
                i += random.gauss(0, 0.1)
                i = max(0.01, i)
                random_values.append(i)
            random_timestamps = [datetime.now(UTC) - timedelta(hours=random.randint(0, 12), minutes=random.randint(0, 59), seconds=random.randint(0, 59)) for _ in range(n)]
            random_timestamps.sort()
            tuples = [(t, fridge, sensor, te) for t, te in zip(random_timestamps, random_values)]
            db.executemany(
                'INSERT INTO temperatures (timestamp, fridge, sensor, temp) VALUES (?, ?, ?, ?)', tuples
            )
        for sensor in ["P1", "P2", "P3", "P4", "P5"]:
            offset = datetime.now(UTC).timestamp()
            x = np.linspace(offset - 7*24*60*60, offset, n)
            timestamps = [datetime.fromtimestamp(i) for i in x]
            n = 100
            # Gaussian noise data
            random_values = []
            i = 500.0
            for _ in range(n):
                i += random.gauss(0, 10)
                i = max(0.01, i)
                random_values.append(i)
            tuples = [(t, fridge, sensor, te) for t, te in zip(random_timestamps, random_values)]
            db.executemany(
                'INSERT INTO temperatures (timestamp, fridge, sensor, temp) VALUES (?, ?, ?, ?)', tuples
            )
    db.commit()


@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Initialized the database.')


@click.command('create-dummy-data')
def create_dummy_data_command():
    init_db()
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
    app.cli.add_command(create_dummy_data_command)
    app.cli.add_command(add_fridge_command)
    app.cli.add_command(add_sensor_command)
