"""ROADMAP D1 — resolving journal calls. The rule is FIXED and versioned, like the forward record's.

Journal rule v1: the window is every CLOSED bar of the call's timeframe after the logging bar whose
close time is at or before `end_time`.
  invalidated  the invalidation price was touched at any point in the window (bar highs / lows);
  otherwise    the last bar's close is on the called side of the logging price -> correct,
               anything else (including an exactly equal close) -> incorrect.
A call resolves only once the data covers its window: a closed bar exists whose close time is at or
after `end_time` (a Saturday end on forex resolves on Monday). Resolution is an UPDATE … WHERE
outcome IS NULL, so running it twice changes nothing.
"""

from __future__ import annotations

import time

import pandas as pd

from src.journal.store import tf_seconds

RULE_VERSION = 1
RULE_TEXT = {1: (
    "Journal rule v1. Window: every closed bar after the logging bar, up to the end of the horizon. "
    "Invalidated if the invalidation price is touched at any point (highs/lows). Otherwise correct if "
    "the last close in the window is on the called side of the logging price; incorrect if not "
    "(an exactly equal close is incorrect). Confidence = your probability the call is judged correct.")}


def _epoch_s(idx: pd.DatetimeIndex):
    return ((idx.tz_convert("UTC").tz_localize(None) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).to_numpy()


def judge(entry: dict, df: pd.DataFrame) -> tuple[str, float] | None:
    """(outcome, last close in the window), or None while the data doesn't cover the window yet.
    `df` must be closed-candles-only for the entry's timeframe."""
    tf = tf_seconds(entry["timeframe"])
    if not len(df):
        return None
    opens = _epoch_s(df.index)                           # unit-safe (pandas may store ns, us or ms)
    closes_at = opens + tf
    if closes_at.max() < entry["end_time"]:
        return None
    win = df[(opens > entry["bar_time"]) & (closes_at <= entry["end_time"])]
    if win.empty:
        return None
    up = entry["direction"] == "up"
    touched = (win["low"] <= entry["invalidation"]).any() if up else (win["high"] >= entry["invalidation"]).any()
    last = float(win["close"].iloc[-1])
    if touched:
        return "invalidated", last
    right = last > entry["price"] if up else last < entry["price"]
    return ("correct" if right else "incorrect"), last


def resolve_due(conn, candles_for, *, now: float | None = None) -> int:
    """Resolve every pending call whose window has ended. `candles_for(symbol, timeframe)` returns
    FRESH closed candles; it is only called for markets that actually have a due call."""
    now = now or time.time()
    due = conn.execute("SELECT * FROM journal_entries WHERE outcome IS NULL AND end_time <= ?", (int(now),)).fetchall()
    frames: dict[tuple, pd.DataFrame | None] = {}
    n = 0
    for r in due:
        key = (r["symbol"], r["timeframe"])
        if key not in frames:
            try:
                frames[key] = candles_for(*key)
            except Exception:                                 # data unavailable now: try next time
                frames[key] = None
        df = frames[key]
        if df is None:
            continue
        res = judge(dict(r), df)
        if res is None:
            continue
        cur = conn.execute("UPDATE journal_entries SET outcome=?, end_close=?, resolved_at=? WHERE id=? AND outcome IS NULL",
                           (res[0], res[1], int(now), r["id"]))
        n += cur.rowcount
    conn.commit()
    return n


def live_candles(cfg):
    """Fresh, closed candles for resolution (refreshed when older than one bar)."""
    from datetime import datetime, timezone

    from src.data.registry import get_candles
    from src.forward.record import closed_only

    def load(symbol: str, timeframe: str) -> pd.DataFrame:
        df = get_candles(symbol, timeframe, cfg, stale_after_minutes=max(1, tf_seconds(timeframe) // 60))
        return closed_only(df, timeframe, datetime.now(timezone.utc))
    return load
