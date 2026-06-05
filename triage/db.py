"""SQLite wrapper for the Argus triage database.

Connect to (or create) the database. Schema is auto-applied on first connect.
"""

import sqlite3
from pathlib import Path

SCHEMA_FILE = Path(__file__).parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).parent / "triage.db"


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    new_db = not Path(db_path).exists()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if new_db:
        conn.executescript(SCHEMA_FILE.read_text())
        conn.commit()
    return conn
