"""ROADMAP D6 — blind training: the pool of past moments where a chart pattern CONFIRMED.

Built from THE encyclopedia walk (`encyclopedia.collect_instances`, look-ahead-safe): every pattern
first seen while forming that later broke out, whose outcome is known (the full horizon after the
breakout exists). One row per setup in `training_setups`; the API picks one at random, shows the chart
ENDING at the breakout candle with the engine's drawings hidden, takes the user's call through the
journal (source "blind"), and reveals what happened.

Setups are identified by their bar TIME, never by index: the candle cache shifts as new bars arrive.
"""

from __future__ import annotations

import json
import random

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS training_setups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
    bar_time INTEGER NOT NULL,             -- open time of the breakout (confirmation) candle, epoch s UTC
    type TEXT NOT NULL, direction TEXT NOT NULL, regime TEXT NOT NULL,
    outcome TEXT NOT NULL,                 -- target | failed | open (the encyclopedia's outcome)
    move_atr REAL, breakout REAL, invalidation REAL, target REAL,
    UNIQUE (symbol, timeframe, bar_time, type)
);
"""


def collect_setups(df: pd.DataFrame, cfg, symbol: str, timeframe: str, *, horizon: int = 24) -> list[dict]:
    """Confirmed, judged setups for one market (`cfg` request-scoped)."""
    from src.indicators.features import add_features
    from src.market.regime import classify_regime
    from src.research.encyclopedia import collect_instances
    regimes = classify_regime(add_features(df, cfg), cfg)
    out = []
    for x in collect_instances(df, cfg, symbol, timeframe, horizon=horizon):
        if x.first_state != "forming" or x.confirmed_bar is None or x.outcome in (None, "pending"):
            continue
        c = x.confirmed_bar
        reg = regimes.iloc[c]
        out.append({"symbol": symbol, "timeframe": timeframe, "bar_time": int(pd.Timestamp(df.index[c]).timestamp()),
                    "type": x.pattern_type, "direction": x.direction,
                    "regime": str(reg) if reg is not None and not pd.isna(reg) else "unknown",
                    "outcome": x.outcome, "move_atr": None if x.move_atr is None else round(x.move_atr, 3),
                    "breakout": x.breakout, "invalidation": x.invalidation, "target": x.target})
    return out


def connect(path: str = "data/wizard.db"):
    from src.store.db import connect as base
    conn = base(path)
    conn.executescript(SCHEMA)
    return conn


def save(conn, setups: list[dict]) -> int:
    n = 0
    for s in setups:
        cols = ", ".join(s)
        n += conn.execute(f"INSERT OR IGNORE INTO training_setups ({cols}) VALUES ({', '.join('?' * len(s))})",
                          tuple(s.values())).rowcount
    conn.commit()
    return n


def options(conn) -> dict:
    """What the filters can offer, with counts."""
    q = lambda col: {r[0]: r[1] for r in conn.execute(  # noqa: E731
        f"SELECT {col}, COUNT(*) FROM training_setups GROUP BY {col} ORDER BY {col}")}
    return {"types": q("type"), "regimes": q("regime"), "timeframes": q("timeframe"),
            "total": conn.execute("SELECT COUNT(*) FROM training_setups").fetchone()[0]}


def pick(conn, *, type_: str | None = None, regime: str | None = None, timeframe: str | None = None,
         rng: random.Random | None = None) -> dict | None:
    """A random setup matching the filters that this user hasn't already answered (blind journal)."""
    where, args = ["1=1"], []
    for col, val in (("type", type_), ("regime", regime), ("timeframe", timeframe)):
        if val:
            where.append(f"s.{col} = ?")
            args.append(val)
    rows = conn.execute(
        f"""SELECT s.* FROM training_setups s WHERE {' AND '.join(where)} AND NOT EXISTS (
              SELECT 1 FROM journal_entries j WHERE j.source = 'blind' AND j.symbol = s.symbol
              AND j.timeframe = s.timeframe AND j.bar_time = s.bar_time)""", args).fetchall()
    if not rows:
        return None
    return dict((rng or random).choice(rows))


def get(conn, setup_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM training_setups WHERE id=?", (setup_id,)).fetchone()
    return dict(r) if r else None


def export(setups: list[dict], path: str) -> None:
    with open(path, "w") as f:
        json.dump(setups, f)
