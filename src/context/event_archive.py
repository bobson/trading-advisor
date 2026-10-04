"""ROADMAP D4 prep — archive the economic calendar so an event study has history to study.

The keyless calendar only shows THIS week, so the past is lost unless it's kept. The 08:00 morning
job saves the week's events into `events` every day; each event is keyed by (time, currency, title),
so a daily save just refreshes it. `first_seen_at` / `last_seen_at` record when it was in the feed;
the consensus / previous figures keep their latest published value (the feed may revise a consensus
during the week). A week the droplet is down for entirely is a gap — it can't be backfilled from
this feed.
"""

from __future__ import annotations

import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,                  -- event time, epoch s UTC
    currency TEXT NOT NULL, title TEXT NOT NULL,
    impact TEXT NOT NULL, kind TEXT NOT NULL,
    forecast TEXT, previous TEXT, actual TEXT,
    source TEXT NOT NULL,
    first_seen_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL,
    UNIQUE (ts, currency, title)
);
"""


def connect(path: str = "data/wizard.db"):
    from src.store.db import connect as base
    conn = base(path)
    conn.executescript(SCHEMA)
    return conn


def archive(conn, events: list[dict], *, source: str, now: float | None = None) -> dict:
    """Insert new events, refresh known ones. Returns {"new": n, "seen": m}."""
    now = int(now or time.time())
    new = 0
    for e in events:
        cur = conn.execute(
            "INSERT OR IGNORE INTO events (ts, currency, title, impact, kind, forecast, previous, actual, source, "
            "first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (e["ts"], e["currency"], e["title"], e["impact"], e["kind"], e.get("forecast"), e.get("previous"),
             e.get("actual"), source, now, now))
        if cur.rowcount:
            new += 1
        else:
            conn.execute("UPDATE events SET last_seen_at=?, impact=?, forecast=?, previous=?, "
                         "actual=COALESCE(?, actual) WHERE ts=? AND currency=? AND title=?",
                         (now, e["impact"], e.get("forecast"), e.get("previous"), e.get("actual"),
                          e["ts"], e["currency"], e["title"]))
    conn.commit()
    return {"new": new, "seen": len(events)}


def stats(conn) -> dict:
    """How much history exists — what D4 would have to work with."""
    try:
        r = conn.execute("SELECT COUNT(*), MIN(ts), MAX(ts), SUM(impact = 'High') FROM events").fetchone()
    except Exception:
        return {"events": 0, "high": 0, "from": None, "to": None}
    return {"events": r[0] or 0, "high": r[3] or 0, "from": r[1], "to": r[2]}
