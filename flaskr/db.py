# Methods for controlling the SQLite DB

import sqlite3
from datetime import datetime
import click

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
        db.executescript(f.read())


@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Initialized the database.')

sqlite3.register_converter(
    'timestamp', lambda v: datetime.fromisoformat(v.decode())
)


def init_app(app):
    """Initialise the app with database knowledge"""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)