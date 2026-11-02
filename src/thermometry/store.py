# -*- coding: utf-8 -*-
"""
Database access shared by the web server and the alarm process.

The alarm process used to reach its data by HTTP-polling the web server's own
REST API, one sensor at a time. That made every alert depend on the web server
being up -- and worse, `Alert._get_latest` treated any hiccup as a reason to
silently disable itself, so a transient 500 disarmed the safety interlock. The
alarm process talks to Postgres directly now.

Flask keeps its own connection-per-request wrapper in `flaskr/db.py`, which
delegates the SQL here so there is exactly one copy of each query.
"""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import psycopg2
from psycopg2.extras import Json

from thermometry import config


# -- connections -------------------------------------------------------------

def connect():
    """Open a new database connection. Callers outside Flask own the lifetime."""
    return psycopg2.connect(**config.DATABASE)


# -- measurement reads -------------------------------------------------------

def fetch_readings(conn, query: list[tuple], earliest_stamp, latest_stamp, bin: int = 1) -> pd.DataFrame:
    """Fetch all sensor readings between timestamps for the given fridge/sensor querys. Combine times into multiples of bin"""
    # query should be of the form: [("fridge", "sensor"), ("fridge", "sensor"), ... ]
    cur = conn.cursor()

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


def fetch_latest_readings(conn, query: list[tuple]) -> pd.DataFrame:
    """Fetch the latest sensor readings for the given fridge/sensor querys"""
    # query should be of the form: [("fridge", "sensor"), ("fridge", "sensor"), ... ]
    cur = conn.cursor()

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


def fetch_window(conn, fridge: str, sensors: list[str], minutes: float) -> dict:
    """Fetch the last `minutes` of history for several sensors on one fridge in a single query.

    Returns {sensor: [(unix_time, reading), ...]} ordered oldest-first, with sensors that have
    no data in the window mapped to an empty list. This is the alarm system's only read path --
    one query per fridge per tick, rather than one HTTP round trip per sensor per alert.
    """
    if not sensors:
        return {}

    cur = conn.cursor()
    earliest = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    placeholders = ", ".join(["%s"] * len(sensors))
    cur.execute(f"""
    SELECT s.name, m.time, m.reading
    FROM measurement m
    JOIN sensor s ON m.sensor_id = s.id
    JOIN fridge f ON s.fridge_id = f.id
    WHERE f.name = %s AND s.name IN ({placeholders}) AND m.time >= %s
    ORDER BY m.time
    """, [fridge] + list(sensors) + [earliest])
    rows = cur.fetchall()
    cur.close()

    window = {sensor: [] for sensor in sensors}
    for name, time, reading in rows:
        if reading is None:
            continue
        window[name].append((time.timestamp(), float(reading)))
    return window


def fetch_latest_for_fridge(conn, fridge: str, sensors: list[str]) -> dict:
    """Fetch the most recent reading of each sensor on one fridge.

    Returns {sensor: (unix_time, reading)}, omitting sensors that have never reported.
    Reads `latest_reading`, which every sensor now gets a row in regardless of whether
    its history is also kept.
    """
    if not sensors:
        return {}

    cur = conn.cursor()
    placeholders = ", ".join(["%s"] * len(sensors))
    cur.execute(f"""
    SELECT s.name, lr.time, lr.reading
    FROM latest_reading lr
    JOIN sensor s ON lr.sensor_id = s.id
    JOIN fridge f ON s.fridge_id = f.id
    WHERE f.name = %s AND s.name IN ({placeholders})
    """, [fridge] + list(sensors))
    rows = cur.fetchall()
    cur.close()

    return {name: (time.timestamp(), float(reading)) for name, time, reading in rows if reading is not None}


# -- alert state -------------------------------------------------------------

def load_alert_states(conn) -> dict:
    """Load every persisted alert state, keyed by (alert_type, fridge)."""
    cur = conn.cursor()
    cur.execute("""
    SELECT alert_type, fridge, state, since, last_triggered, pending_action, detail
    FROM alert_state
    """)
    rows = cur.fetchall()
    cur.close()
    return {
        (alert_type, fridge): {
            "state": state,
            "since": since,
            "last_triggered": last_triggered,
            "pending_action": pending_action,
            "detail": detail or {},
        }
        for alert_type, fridge, state, since, last_triggered, pending_action, detail in rows
    }


def save_alert_state(conn, alert_type: str, fridge: str, state: str, since, last_triggered, detail: dict,
                     clear_pending: bool = True):
    """Write an alert's current state back. Clears pending_action once it has been consumed."""
    cur = conn.cursor()
    cur.execute(f"""
    INSERT INTO alert_state (alert_type, fridge, state, since, last_triggered, updated, pending_action, detail)
    VALUES (%s, %s, %s, %s, %s, now(), NULL, %s)
    ON CONFLICT (alert_type, fridge) DO UPDATE SET
        state = EXCLUDED.state,
        since = EXCLUDED.since,
        last_triggered = EXCLUDED.last_triggered,
        updated = now(),
        detail = EXCLUDED.detail
        {", pending_action = NULL" if clear_pending else ""}
    """, (alert_type, fridge, state, since, last_triggered, Json(detail)))
    conn.commit()
    cur.close()


def record_alert_event(conn, alert_type: str, fridge: str, from_state, to_state: str, reason: str, detail: dict):
    """Append a state transition to the audit trail."""
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO alert_event (alert_type, fridge, from_state, to_state, reason, detail)
    VALUES (%s, %s, %s, %s, %s, %s)
    """, (alert_type, fridge, from_state, to_state, reason, Json(detail)))
    conn.commit()
    cur.close()


def request_alert_action(conn, alert_type: str, fridge: str, action: str):
    """Queue a state change requested from the website.

    Replaces changes.json. A single UPDATE, so two people clicking at once cannot lose
    each other's command the way the old read-modify-write file did.
    """
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO alert_state (alert_type, fridge, state, pending_action)
    VALUES (%s, %s, 'DISABLED', %s)
    ON CONFLICT (alert_type, fridge) DO UPDATE SET
        pending_action = EXCLUDED.pending_action,
        updated = now()
    """, (alert_type, fridge, action))
    conn.commit()
    cur.close()


def fetch_alert_states_for_display(conn, alert_type: str = None) -> list:
    """Read alert states for the website, newest data first. `alert_type` of None or 'all' returns everything."""
    cur = conn.cursor()
    if alert_type in (None, "all"):
        cur.execute("""
        SELECT alert_type, fridge, state, since, last_triggered, updated, detail
        FROM alert_state ORDER BY alert_type, fridge
        """)
    else:
        cur.execute("""
        SELECT alert_type, fridge, state, since, last_triggered, updated, detail
        FROM alert_state WHERE alert_type = %s ORDER BY fridge
        """, (alert_type,))
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "type": r[0], "fridge": r[1], "state": r[2],
            "since": r[3], "last_triggered": r[4], "updated": r[5],
            "detail": r[6] or {},
        }
        for r in rows
    ]


# -- heartbeat ---------------------------------------------------------------

def beat(conn, name: str = "watchtower"):
    """Record that the named evaluator is alive."""
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO evaluator_heartbeat (name, time) VALUES (%s, now())
    ON CONFLICT (name) DO UPDATE SET time = now()
    """, (name,))
    conn.commit()
    cur.close()


def last_beat(conn, name: str = "watchtower"):
    """Return when the named evaluator last reported in, or None if it never has."""
    cur = conn.cursor()
    cur.execute("SELECT time FROM evaluator_heartbeat WHERE name = %s", (name,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None
