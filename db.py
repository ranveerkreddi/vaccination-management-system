"""Database layer: schema and connection helper (plain SQL, no ORM)."""
import sqlite3

SLOTS = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
SLOT_CAPACITY = 3  # max active appointments per date + time slot

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL CHECK (length(trim(name)) > 0),
    phone      TEXT,
    dob        TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vaccines (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS appointments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER NOT NULL REFERENCES patients(id) ON DELETE RESTRICT,
    vaccine_id  INTEGER NOT NULL REFERENCES vaccines(id) ON DELETE RESTRICT,
    appt_date   TEXT NOT NULL,
    slot        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'booked'
                CHECK (status IN ('booked', 'administered', 'cancelled')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_appt_slot ON appointments (appt_date, slot, status);
CREATE INDEX IF NOT EXISTS idx_appt_patient ON appointments (patient_id);
"""


def connect(path):
    """Open a connection in autocommit mode; transactions are managed explicitly."""
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.close()
