# app/services/db.py
import os
import psycopg2
import psycopg2.extras


def get_conn():
    """Open a new Postgres connection (autocommit)."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    return conn


def dict_cursor(conn):
    """Return a cursor that yields dict rows (column name → value)."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
