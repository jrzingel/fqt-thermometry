# Methods for controlling the SQLite DB

import click
import numpy as np
import pandas as pd
import psycopg2
from flask import current_app, g

from thermometry import store


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
        ON CONFLICT (name) DO UPDATE
            SET name = EXCLUDED.name
        RETURNING id
        """, (name,))
    f_id = cursor.fetchone()[0]
    print(f"Added fridge {name}, assigned ID {f_id}")
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
        ON CONFLICT (name, fridge_id) DO UPDATE
            SET name = EXCLUDED.name,
                latest = EXCLUDED.latest
        RETURNING id
        """, (name, fridge_id, latest))
    s_id = cursor.fetchone()[0]
    print(f"Added sensor {name} to fridge ID {fridge_id} with latest={latest}, assigned ID {s_id}")
    db.commit()
    cursor.close()
    return s_id


DEFAULT_FRIDGES = ["queenie", "scarlett", "tallulah", "ursula", "venus", "winona"]

# Plate temperatures and gas-handling pressures.
PLATE_SENSORS = ["50K", "4K", "magnet", "still", "mxc"]
PRESSURE_SENSORS = ["P1", "P2", "P3", "P4", "P5", "P6"]

# Compressor and pump signals. These used to be latest-only, which meant no history was kept
# for them at all -- so no alarm could ask "has the compressor been off for ten minutes?" or
# "was the oil hot three quarters of an hour ago?". They are historical now; the volume is
# negligible because BlueFors only writes a log line about once a minute.
COMPRESSOR_SENSORS = [
    "pulse_on",      # cparun: compressor running
    "oil_temp",      # cpatempo / cptempo
    "water_in",      # cpatempwi / cptempwi
    "water_out",     # cpatempwo / cptempwo
    "helium_temp",   # cpatemph / cptemph: helium discharge
    "comp_state",    # cpastate: state machine value
    "comp_error",    # cpaerr: error word, latches across an over-temperature trip
    "comp_warn",     # cpawarn: warning word
    "comp_current",  # cpacurrent: motor current, ~0 when not running
    "comp_hours",    # cpahours: running hours, stops advancing when stopped
    "comp_lp",       # cpalpa / cpalp / cpavgl: low side pressure
    "comp_hp",       # cpahpa / cpahp / cpavgh: high side pressure
    "comp_dp",       # cpadp: differential, where reported directly
]
PUMP_SENSORS = [
    "flow",          # mixture circulation
    "turbo_speed",   # tc400actualspd
    "turbo_on",      # tc400pumpstatn
]

# Everything is historical now. `latest` means "keep history too" rather than "instead of":
# `latest_reading` is always upserted, so the gauges page works either way.
HISTORICAL_SENSORS = PLATE_SENSORS + PRESSURE_SENSORS + COMPRESSOR_SENSORS + PUMP_SENSORS

# The subset that existing deployments still have flagged latest-only, used by `upgrade-db`.
PROMOTED_SENSORS = ["pulse_on", "oil_temp", "water_in", "water_out", "flow", "turbo_speed"]


def create_default_fridges():
    """Create the default fridges and associated sensors"""
    for fridge in DEFAULT_FRIDGES:
        f_id = add_fridge(fridge)
        print(fridge, f_id)
        for sensor in HISTORICAL_SENSORS:
            add_sensor(sensor, f_id, False)

    # XLD systems log a second compressor, which the listener uploads as its own pseudo-fridge
    winona2_id = add_fridge("winona2")
    for sensor in COMPRESSOR_SENSORS:  # We only need the compressor settings
        add_sensor(sensor, winona2_id, False)


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

    # Mirror the most recent historical point into latest_reading for every sensor, the same
    # way addReading does in production. Sensors still flagged latest-only get a value too.
    cur.execute("""
    INSERT INTO latest_reading (sensor_id, time, reading)
    SELECT DISTINCT ON (sensor_id) sensor_id, time, reading
    FROM measurement ORDER BY sensor_id, time DESC
    ON CONFLICT (sensor_id) DO UPDATE SET time = excluded.time, reading = excluded.reading;
    """)
    cur.execute("SELECT id FROM sensor WHERE latest=true;")
    for (id,) in cur.fetchall():
        cur.execute("""
        INSERT INTO latest_reading (sensor_id, time, reading) VALUES (%s, %s, %s)
        ON CONFLICT (sensor_id) DO UPDATE SET time = excluded.time, reading = excluded.reading;
        """, (id, datetime.fromtimestamp(now), random.gauss(0, 10)))

    db.commit()
    cur.close()


def fetch_readings(query: list[tuple], earliest_stamp: int, latest_stamp: int, bin: int = 1) -> pd.DataFrame:
    """Fetch all sensor readings between timestamps for the given fridge/sensor querys. Combine times into multiples of bin"""
    return store.fetch_readings(get_db(), query, earliest_stamp, latest_stamp, bin)


def fetch_latest_readings(query: list[tuple]) -> pd.DataFrame:
    """Fetch the latest sensor readings for the given fridge/sensor querys"""
    return store.fetch_latest_readings(get_db(), query)


def upgrade_db():
    """Bring an existing database up to date without destroying data.

    `init-db` drops every table, so it cannot be used on a live deployment. This applies the
    additive changes instead: the alert subsystem tables, the new compressor/pump sensors, and
    the promotion of the compressor signals from latest-only to historical.
    """
    db = get_db()
    cur = db.cursor()

    # 1. Alert subsystem tables (idempotent -- mirrors the tail of schema.sql)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alert_state (
        alert_type TEXT NOT NULL,
        fridge TEXT NOT NULL,
        state TEXT NOT NULL,
        since TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_triggered TIMESTAMPTZ,
        updated TIMESTAMPTZ NOT NULL DEFAULT now(),
        pending_action TEXT,
        detail JSONB NOT NULL DEFAULT '{}'::jsonb,
        PRIMARY KEY (alert_type, fridge)
    );
    CREATE TABLE IF NOT EXISTS alert_event (
        id BIGSERIAL PRIMARY KEY,
        time TIMESTAMPTZ NOT NULL DEFAULT now(),
        alert_type TEXT NOT NULL,
        fridge TEXT NOT NULL,
        from_state TEXT,
        to_state TEXT NOT NULL,
        reason TEXT,
        detail JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS idx_alert_event_time ON alert_event (time DESC);
    CREATE INDEX IF NOT EXISTS idx_alert_event_lookup ON alert_event (alert_type, fridge, time DESC);
    CREATE TABLE IF NOT EXISTS evaluator_heartbeat (
        name TEXT PRIMARY KEY,
        time TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    click.echo("Alert subsystem tables ready.")

    # 2. Add the new sensors to every existing fridge.
    #    winona2-style compressor pseudo-fridges only get the compressor set.
    cur.execute("SELECT id, name FROM fridge ORDER BY name")
    fridges = cur.fetchall()
    added = 0
    for f_id, f_name in fridges:
        cur.execute("SELECT name FROM sensor WHERE fridge_id = %s", (f_id,))
        existing = {row[0] for row in cur.fetchall()}
        compressor_only = existing and not (existing & set(PLATE_SENSORS))
        wanted = COMPRESSOR_SENSORS if compressor_only else HISTORICAL_SENSORS
        for sensor in wanted:
            if sensor not in existing:
                cur.execute(
                    "INSERT INTO sensor (name, fridge_id, latest) VALUES (%s, %s, FALSE)"
                    " ON CONFLICT (name, fridge_id) DO NOTHING", (sensor, f_id))
                added += 1
    click.echo(f"Added {added} new sensor rows across {len(fridges)} fridges.")

    # 3. Promote the compressor/pump signals to historical.
    #    add_sensor's ON CONFLICT could not do this before, so it needs saying explicitly.
    cur.execute(
        "UPDATE sensor SET latest = FALSE WHERE latest = TRUE AND name = ANY(%s)",
        (PROMOTED_SENSORS + PUMP_SENSORS + COMPRESSOR_SENSORS,))
    click.echo(f"Promoted {cur.rowcount} sensors from latest-only to historical.")

    db.commit()
    cur.close()


@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Initialized the database.')


@click.command('upgrade-db')
def upgrade_db_command():
    upgrade_db()
    click.echo('Database upgraded.')


@click.command('create-default-fridges')
def create_default_fridges_command():
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
    app.cli.add_command(upgrade_db_command)
    app.cli.add_command(create_default_fridges_command)
    app.cli.add_command(create_dummy_data_command)
    app.cli.add_command(add_fridge_command)
    app.cli.add_command(add_sensor_command)

