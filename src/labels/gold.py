"""ROADMAP B1 — the detector gold set: what the user's eye sees at a chosen bar.

Labels are made in the scrub view with the detector overlays hidden (so the eye doesn't anchor on
them) and saved per (symbol, timeframe, bar). They are the reference B2 measures detector precision
and recall against, so they are validated on the way in: a pattern needs a known type and at least
two points; a zone needs lower < upper and a role. `nothing: true` records "I see no pattern here"
— just as important as a positive label, because it is what exposes false positives.

Storage is the `gold_labels` table (see `src/store/db.py`), one row per bar; saving the same bar
again replaces its labels (`updated_at` moves, `created_at` stays).
"""

from __future__ import annotations

import json
import time
from collections import Counter

from src.patterns.chart_patterns import (
    ASCENDING_CHANNEL,
    ASCENDING_TRIANGLE,
    DESCENDING_CHANNEL,
    DESCENDING_TRIANGLE,
    DOUBLE_BOTTOM,
    DOUBLE_TOP,
    FALLING_WEDGE,
    HEAD_AND_SHOULDERS,
    INVERSE_HEAD_AND_SHOULDERS,
    RECTANGLE,
    RISING_WEDGE,
    SYMMETRIC_TRIANGLE,
)

# The detector's own vocabulary (so B2 compares like with like) + shapes the detector doesn't find
# yet, so the gold set can measure RECALL on them too.
DETECTOR_TYPES = [DOUBLE_TOP, DOUBLE_BOTTOM, HEAD_AND_SHOULDERS, INVERSE_HEAD_AND_SHOULDERS,
                  ASCENDING_TRIANGLE, DESCENDING_TRIANGLE, SYMMETRIC_TRIANGLE, RECTANGLE,
                  ASCENDING_CHANNEL, DESCENDING_CHANNEL, RISING_WEDGE, FALLING_WEDGE]
EXTRA_TYPES = ["bull flag", "bear flag", "other"]
PATTERN_TYPES = DETECTOR_TYPES + EXTRA_TYPES
ZONE_ROLES = ("support", "resistance")


def validate(labels: dict) -> dict:
    """Normalise and check a labels payload; raises ValueError with a readable message."""
    if not isinstance(labels, dict):
        raise ValueError("labels must be an object")
    patterns, zones = labels.get("patterns") or [], labels.get("zones") or []
    out_p = []
    for i, p in enumerate(patterns):
        if p.get("type") not in PATTERN_TYPES:
            raise ValueError(f"pattern {i + 1}: unknown type {p.get('type')!r}")
        pts = p.get("points") or []
        if len(pts) < 2:
            raise ValueError(f"pattern {i + 1} ({p['type']}): needs at least 2 key points")
        out_p.append({"type": p["type"],
                      "points": [{"time": int(q["time"]), "price": float(q["price"])} for q in pts]})
    out_z = []
    for i, z in enumerate(zones):
        lo, hi = float(z["lower"]), float(z["upper"])
        if not lo < hi:
            raise ValueError(f"zone {i + 1}: lower must be below upper")
        if z.get("role") not in ZONE_ROLES:
            raise ValueError(f"zone {i + 1}: role must be support or resistance")
        out_z.append({"lower": lo, "upper": hi, "role": z["role"]})
    nothing = bool(labels.get("nothing"))
    if nothing and out_p:
        raise ValueError("'nothing here' can't be combined with pattern labels")
    if not out_p and not out_z and not nothing:
        raise ValueError("empty label — mark a pattern or zone, or tick 'nothing here'")
    return {"patterns": out_p, "zones": out_z, "nothing": nothing, "note": (labels.get("note") or "").strip()}


def save(conn, symbol: str, timeframe: str, bar: int, labels: dict, *, bar_time: int | None = None,
         now: int | None = None) -> dict:
    """Insert or replace the labels for (symbol, timeframe, bar). Returns the stored row."""
    clean = validate(labels)
    now = int(now if now is not None else time.time())
    conn.execute(
        "INSERT INTO gold_labels(symbol,timeframe,bar,bar_time,labels,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(symbol,timeframe,bar) DO UPDATE SET "
        "labels=excluded.labels, bar_time=excluded.bar_time, updated_at=excluded.updated_at",
        (symbol, timeframe, int(bar), bar_time, json.dumps(clean), now, now))
    conn.commit()
    return load(conn, symbol, timeframe, bar)


def _row(r) -> dict:
    d = dict(r)
    d["labels"] = json.loads(d["labels"])
    return d


def load(conn, symbol: str, timeframe: str, bar: int) -> dict | None:
    r = conn.execute("SELECT * FROM gold_labels WHERE symbol=? AND timeframe=? AND bar=?",
                     (symbol, timeframe, int(bar))).fetchone()
    return _row(r) if r else None


def list_all(conn) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM gold_labels ORDER BY updated_at DESC, id DESC").fetchall()]


def delete(conn, label_id: int) -> None:
    conn.execute("DELETE FROM gold_labels WHERE id=?", (label_id,))
    conn.commit()


def summary(conn) -> dict:
    """Totals for the gold-set list: charts labelled, by pattern type, zones, 'nothing here'."""
    rows = list_all(conn)
    by_type = Counter(p["type"] for r in rows for p in r["labels"]["patterns"])
    return {
        "charts": len(rows),
        "patterns": sum(by_type.values()),
        "by_type": dict(sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))),
        "zones": sum(len(r["labels"]["zones"]) for r in rows),
        "nothing": sum(1 for r in rows if r["labels"]["nothing"]),
        "by_symbol_tf": dict(Counter(f"{r['symbol']} {r['timeframe']}" for r in rows)),
    }
