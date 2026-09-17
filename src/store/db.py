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
