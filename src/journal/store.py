"""ROADMAP D1 — the prediction journal: YOUR calls, logged before the engine's read is revealed.

One row per call in `journal_entries`. The server — not the page — fixes the bar the call is made at
(the latest CLOSED bar, fresh candles) and its price, and freezes what the engine said at that moment
(bias, tier, patterns, Feature-6 regime, facts hash, engine commit) for the breakdowns. What the user
could SEE when logging (verdict, explanation) is stored as it was on screen, so calibration can
separate blind calls from anchored ones.

Honesty rules, enforced here:
  * up/down calls only; confidence 50–100 = "my probability this call is judged CORRECT under the
    journal rule" (a 30% "up" is really a 70% "down");
  * the invalidation must sit on the losing side of the logging price;
  * one LIVE call per (symbol, timeframe, bar), from whichever page — no hedging both ways on the same
    bar (blind-training calls, D6, are their own record);
  * a call can be deleted only within DELETE_WINDOW_S of logging (typos), never once it's older, and
    never after it resolved — otherwise the calls going badly could quietly disappear.
"""

from __future__ import annotations

import json
import sqlite3
import time

import pandas as pd

from src.config import Config

DELETE_WINDOW_S = 300
UNITS = ("weeks", "days", "bars")
SOURCES = ("analysis", "morning", "blind")

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    source TEXT NOT NULL,                  -- analysis | morning | blind (D6)
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
    bar_time INTEGER NOT NULL,             -- open time of the closed bar the call was made at (epoch s UTC)
    price REAL NOT NULL,                   -- that bar's close
    direction TEXT NOT NULL,               -- up | down
    confidence INTEGER NOT NULL,           -- 50..100: P(judged correct under the rule)
    invalidation REAL NOT NULL,
    horizon_value INTEGER NOT NULL, horizon_unit TEXT NOT NULL,
    end_time INTEGER NOT NULL,             -- the window closes here (epoch s UTC)
    note TEXT,
    verdict_visible INTEGER NOT NULL,      -- was the engine's verdict on screen when logging?
    explanation_visible INTEGER NOT NULL,  -- was Claude's explanation on screen?
    engine TEXT,                           -- JSON: the engine's read at that bar
    rule_version INTEGER NOT NULL,
    outcome TEXT,                          -- correct | incorrect | invalidated (NULL = pending)
    resolved_at INTEGER, end_close REAL,
    UNIQUE (symbol, timeframe, bar_time, source)
);
"""


class JournalError(ValueError):
    """A call the journal refuses (wrong side, duplicate, out of range...). The message is for the user."""


def connect(path: str = "data/wizard.db"):
    from src.store.db import connect as base
    conn = base(path)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def tf_seconds(timeframe: str) -> int:
    n, unit = int(timeframe[:-1]), timeframe[-1]
    return n * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]


def end_time_for(bar_time: int, timeframe: str, value: int, unit: str) -> int:
    """The window runs from the close of the logging bar for `value` weeks / days / bars."""
    start = bar_time + tf_seconds(timeframe)
    span = {"weeks": 7 * 86400, "days": 86400}.get(unit)
    return start + (value * span if span else value * tf_seconds(timeframe))


def engine_snapshot(df: pd.DataFrame, symbol: str, timeframe: str, cfg: Config) -> dict:
    """What the engine read at the logging bar (never shown to the user by this call)."""
    from src.forward.record import engine_info, facts_hash
    from src.indicators.features import add_features
    from src.market.regime import classify_regime
    from src.service.analyze import advise
    f = advise(symbol, timeframe, cfg, df=df, explain_enabled=False).facts
    reg = classify_regime(add_features(df, cfg), cfg).iloc[-1]
    eng = engine_info(cfg)
    return {"bias": f["confluence"]["bias"], "tier": f["situation"]["tier"],
            "aligned": bool(f["confluence"]["triggered"]),
            "patterns": sorted({p["type"] for p in f.get("chart_patterns") or []
                                if p.get("lifecycle") in ("forming", "fresh", "in_play")}),
            "regime": str(reg) if reg is not None and not pd.isna(reg) else "unknown",
            "facts_hash": facts_hash(f), "engine_commit": eng["commit"]}


def log_call(conn, *, df: pd.DataFrame, cfg: Config, symbol: str, timeframe: str, direction: str,
             confidence: int, invalidation: float, horizon_value: int, horizon_unit: str, note: str = "",
             source: str = "analysis", verdict_visible: bool, explanation_visible: bool,
             now: float | None = None, bar_time: int | None = None) -> dict:
    """Validate and store one call at the last closed bar of `df` (already closed-candles-only).
    `bar_time` is for D6's blind mode (an explicit historical bar); the live path never passes it."""
    from src.journal.resolve import RULE_VERSION
    if direction not in ("up", "down"):
        raise JournalError("direction must be up or down")
    if not 50 <= int(confidence) <= 100:
        raise JournalError("confidence must be 50–100 (a call below 50% is a call the other way)")
    if horizon_unit not in UNITS or int(horizon_value) < 1:
        raise JournalError("horizon must be at least 1 week, day or bar")
    if source not in SOURCES:
        raise JournalError("unknown source")
    if df.empty:
        raise JournalError("no closed candles for this market")
    if bar_time is not None:
        df = df[df.index <= pd.Timestamp(bar_time, unit="s", tz="UTC")]
    bt = int(pd.Timestamp(df.index[-1]).timestamp())
    price = float(df["close"].iloc[-1])
    if not invalidation > 0 or abs(invalidation - price) / price > 0.5:
        raise JournalError(f"the invalidation {invalidation:g} is more than 50% away from the price ({price:g}) — a typo?")
    if (direction == "up" and not invalidation < price) or (direction == "down" and not invalidation > price):
        side = "below" if direction == "up" else "above"
        raise JournalError(f"for an {direction} call the invalidation must be {side} the price ({price:g})")
    row = {"created_at": int(now or time.time()), "source": source, "symbol": symbol, "timeframe": timeframe,
           "bar_time": bt, "price": price, "direction": direction, "confidence": int(confidence),
           "invalidation": float(invalidation), "horizon_value": int(horizon_value), "horizon_unit": horizon_unit,
           "end_time": end_time_for(bt, timeframe, int(horizon_value), horizon_unit), "note": (note or "")[:2000],
           "verdict_visible": int(bool(verdict_visible)), "explanation_visible": int(bool(explanation_visible)),
           "engine": json.dumps(engine_snapshot(df, symbol, timeframe, cfg)), "rule_version": RULE_VERSION}
    if source != "blind" and conn.execute(
            "SELECT 1 FROM journal_entries WHERE symbol=? AND timeframe=? AND bar_time=? AND source != 'blind'",
            (symbol, timeframe, bt)).fetchone():
        raise JournalError("you already logged a call for this market, timeframe and candle")   # no hedging across pages
    try:
        cur = conn.execute(f"INSERT INTO journal_entries ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                           tuple(row.values()))
    except sqlite3.IntegrityError:
        raise JournalError("you already logged a call for this market, timeframe and candle") from None
    conn.commit()
    return get(conn, cur.lastrowid)


def get(conn, entry_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM journal_entries WHERE id=?", (entry_id,)).fetchone()
    return _row(r) if r else None


def _row(r) -> dict:
    d = dict(r)
    d["engine"] = json.loads(d["engine"]) if d.get("engine") else None
    d["verdict_visible"], d["explanation_visible"] = bool(d["verdict_visible"]), bool(d["explanation_visible"])
    return d


def list_entries(conn, limit: int = 500) -> list[dict]:
    return [_row(r) for r in conn.execute("SELECT * FROM journal_entries ORDER BY created_at DESC, id DESC LIMIT ?",
                                          (limit,))]


def delete(conn, entry_id: int, *, now: float | None = None) -> None:
    e = get(conn, entry_id)
    if e is None:
        raise JournalError("no such entry")
    if e["outcome"] is not None:
        raise JournalError("a resolved call is permanent")
    if (now or time.time()) - e["created_at"] > DELETE_WINDOW_S:
        raise JournalError(f"calls can only be deleted within {DELETE_WINDOW_S // 60} minutes of logging")
    conn.execute("DELETE FROM journal_entries WHERE id=? AND outcome IS NULL", (entry_id,))
    conn.commit()
