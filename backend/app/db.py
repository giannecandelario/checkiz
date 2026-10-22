import json
import os
import sqlite3
from pathlib import Path

def _db_path():
    """One SQLite file by default, but a demo, a device test or a second instance
    on this machine must not be able to write into the developer's data."""
    env = os.getenv("CHECKIZ_DB_PATH")
    return Path(env).expanduser().resolve() if env else (
        Path(__file__).resolve().parent.parent / "checkiz.db")

DB_PATH = _db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    ref TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    received_at TEXT,
    sender TEXT,
    raw TEXT,
    source TEXT DEFAULT 'sms',
    consumed_order TEXT
);
CREATE TABLE IF NOT EXISTS claims (
    ref TEXT PRIMARY KEY,
    order_id TEXT,
    claimed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pending (
    ref TEXT PRIMARY KEY,
    order_id TEXT,
    amount REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS qr_orders (
    order_id TEXT PRIMARY KEY,
    amount REAL,
    coded INTEGER DEFAULT 0,
    status TEXT DEFAULT 'OPEN',
    paid_ref TEXT,
    paid_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,
    status TEXT,
    message TEXT,
    amount REAL,
    ref TEXT,
    elapsed_ms INTEGER,
    needs_app_check INTEGER DEFAULT 0,
    label TEXT,
    sha256 TEXT,
    signals TEXT,
    printed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS review_ack (
    order_id TEXT PRIMARY KEY,
    acked_id INTEGER DEFAULT 0,
    acked_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def json_field(value, default):
    """Read a column stored as JSON text. Empty or hand-edited rows fall back to
    the default instead of breaking a report someone needs mid-stream."""
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Older local databases: add columns introduced later.
        for table, col, ddl in [
            ("verifications", "elapsed_ms", "INTEGER"),
            ("verifications", "needs_app_check", "INTEGER DEFAULT 0"),
            ("verifications", "label", "TEXT"),
            ("verifications", "sha256", "TEXT"),
            ("verifications", "signals", "TEXT"),
            ("verifications", "printed_at", "TEXT"),
            ("ledger", "source", "TEXT DEFAULT 'sms'"),
            ("ledger", "consumed_order", "TEXT"),
            ("qr_orders", "status", "TEXT DEFAULT 'OPEN'"),
            ("qr_orders", "paid_ref", "TEXT"),
            ("qr_orders", "paid_at", "TEXT"),
        ]:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        # after the columns exist, so an old database does not fail here
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verifications_sha ON verifications (sha256)")
