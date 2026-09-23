"""The application's SQLite store (LOCKED decision: stdlib `sqlite3`, one file at
`data/wizard.db`, no ORM). This is the first table; the encyclopedia and journal features add
`encyclopedia_stats` and `journal_entries` here later.

`data/` is gitignored, so the DB is a local working artifact — never committed. `connect()`
creates the parent dir and the schema on demand, so callers never worry about setup; tests pass
`":memory:"` (or a tmp path) for an isolated DB.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = "data/wizard.db"

# Per symbol/timeframe/bar regime label (Feature 6). Keyed by (symbol, timeframe, ts) so a
# recompute upserts in place rather than duplicating.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS regime_cache (
    symbol    TEXT    NOT NULL,
    timeframe TEXT    NOT NULL,
    ts        INTEGER NOT NULL,          -- bar timestamp, epoch seconds (UTC)
    regime    TEXT,                      -- label, or NULL during warm-up
    PRIMARY KEY (symbol, timeframe, ts)
);

-- Paper-trading simulator: one row per Buy/Sell. One position at a time per symbol; the opposite
-- side closes the open one (fills a live spot price at open and close). Append-only in spirit.
CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT    NOT NULL,
    timeframe    TEXT,
    side         TEXT    NOT NULL,        -- "buy" | "sell"
    amount_usd   REAL    NOT NULL,        -- dollar notional entered
    price        REAL    NOT NULL,        -- live fill price at open
    entry_source TEXT,                    -- "live" | "last_close"
    units        REAL    NOT NULL,        -- amount_usd / price
    opened_at    INTEGER NOT NULL,        -- epoch seconds UTC
    status       TEXT    NOT NULL,        -- "open" | "closed"
    closed_at    INTEGER,                 -- epoch secs at close (NULL while open)
    exit_price   REAL,                    -- live fill price at close (NULL while open)
    exit_source  TEXT,
    realized_pnl REAL,                    -- signed $ (NULL while open)
    snapshot     TEXT,                    -- JSON: {bias, confidence, agreeing_categories, explanation?}
    note         TEXT
);

-- ROADMAP B1: the detector GOLD SET — what the user's eye sees at a chosen bar, labelled with the
-- detector overlays hidden. One row per (symbol, timeframe, bar); re-saving the same bar updates it.
CREATE TABLE IF NOT EXISTS gold_labels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT    NOT NULL,
    timeframe  TEXT    NOT NULL,
    bar        INTEGER NOT NULL,          -- bar index in the full history (the as-of / scrub bar)
    bar_time   INTEGER,                   -- that bar's timestamp, epoch seconds UTC
    labels     TEXT    NOT NULL,          -- JSON: {patterns:[{type, points:[{time,price}]}], zones:[{lower,upper,role}], nothing: bool, note}
    created_at INTEGER NOT NULL,          -- epoch seconds UTC
    updated_at INTEGER NOT NULL,
    UNIQUE (symbol, timeframe, bar)
);
"""


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    """Open (creating if needed) the wizard DB, ensure the schema, and return the connection."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
