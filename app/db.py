"""SQLite persistence layer (stdlib only, zero setup)."""
import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("LEADLENS_DB", "leadlens.db")

DEFAULT_ICP = {
    "industries": ["software", "saas", "fintech", "healthcare it", "cybersecurity"],
    "min_employees": 10,
    "max_employees": 500,
    "target_titles": ["founder", "ceo", "owner", "cto", "vp", "head", "director", "manager"],
    "locations": ["united states", "usa", "us", "canada", "united kingdom"],
    # Weights must sum to 100
    "weights": {"industry": 25, "size": 20, "title": 25, "location": 10, "contact": 20},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT UNIQUE NOT NULL,
    name TEXT, title TEXT, company TEXT, domain TEXT, industry TEXT,
    employees INTEGER, location TEXT, email TEXT, linkedin TEXT, phone TEXT,
    email_status TEXT DEFAULT 'missing',
    score INTEGER DEFAULT 0,
    reasons TEXT DEFAULT '[]',
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


@contextmanager
def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with get_db() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM settings WHERE key='icp'").fetchone():
            c.execute("INSERT INTO settings VALUES ('icp', ?)", (json.dumps(DEFAULT_ICP),))


def load_icp(c):
    row = c.execute("SELECT value FROM settings WHERE key='icp'").fetchone()
    return json.loads(row["value"]) if row else dict(DEFAULT_ICP)


def save_icp(c, icp):
    c.execute("INSERT OR REPLACE INTO settings VALUES ('icp', ?)", (json.dumps(icp),))
