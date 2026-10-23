import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "checkiz.db"

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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS receipt_fingerprints (
    ref TEXT PRIMARY KEY,
    phash TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Older local databases: add columns introduced later.
        for table, col, ddl in [
            ("verifications", "elapsed_ms", "INTEGER"),
            ("ledger", "source", "TEXT DEFAULT 'sms'"),
            ("ledger", "consumed_order", "TEXT"),
            ("qr_orders", "status", "TEXT DEFAULT 'OPEN'"),
            ("qr_orders", "paid_ref", "TEXT"),
            ("qr_orders", "paid_at", "TEXT"),
        ]:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
