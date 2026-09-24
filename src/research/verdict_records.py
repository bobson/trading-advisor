"""ROADMAP B4 — the measured record of each VERDICT type, shown beside the verdict.

Walking THE look-ahead-safe backtest walk (`backtest.evaluate.walk` + `signal_at`, no second walker),
every scanned bar's verdict is recorded with how price actually moved over the next `horizon` bars:

  verdict type = (bias, how many categories agreed, whether categories were ALIGNED i.e. triggered)
  resolved that way = the close `horizon` bars later is beyond this bar's close in the bias direction

Rows per (symbol, timeframe, bias, agreeing, aligned) plus an 'all' markets roll-up, each with its
count. Neutral verdicts are not directional and aren't recorded. Overlapping windows (consecutive bars)
make the cases NOT independent — the count is shown with every rate, and below MIN_N (20) the row is
"insufficient data" (no percentage). This is what happened before, never odds for the current bar.
"""

from __future__ import annotations

import importlib
from collections import defaultdict

import pandas as pd

from src.config import Config

MIN_N = 20
ALL = "all"
_ev = importlib.import_module("src.backtest.evaluate")      # the module (the package re-exports a function)

SCHEMA = """
CREATE TABLE IF NOT EXISTS verdict_records (
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL, bias TEXT NOT NULL,
    agreeing INTEGER NOT NULL, aligned INTEGER NOT NULL,
    n INTEGER NOT NULL, resolved INTEGER NOT NULL, horizon INTEGER NOT NULL, built_at INTEGER NOT NULL,
    PRIMARY KEY (symbol, timeframe, bias, agreeing, aligned)
);
"""


def collect(df: pd.DataFrame, cfg: Config, *, horizon: int = 24, step: int = 2) -> list[tuple]:
    """(bias, agreeing, aligned, resolved) for every scanned bar with a directional verdict."""
    close = df["close"].to_numpy()
    out = []
    for i, _sub, feat, swings in _ev.walk(df, cfg, horizon=horizon, step=step):
        res = _ev.signal_at(df, i, cfg, featured=feat, swings=swings)
        if res.bias not in ("bullish", "bearish"):
            continue
        moved = close[i + horizon] - close[i]
        resolved = moved > 0 if res.bias == "bullish" else moved < 0
        out.append((res.bias, int(res.agreeing_categories), bool(res.triggered), bool(resolved)))
    return out


def aggregate(per_market: dict[tuple[str, str], list[tuple]]) -> list[dict]:
    """Counts per (symbol, timeframe, bias, agreeing, aligned), plus symbol='all' roll-ups."""
    acc: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for (sym, tf), cases in per_market.items():
        for bias, agreeing, aligned, resolved in cases:
            for s in (sym, ALL):
                cell = acc[(s, tf, bias, agreeing, int(aligned))]
                cell[0] += 1
                cell[1] += int(resolved)
    return [{"symbol": s, "timeframe": tf, "bias": b, "agreeing": a, "aligned": al, "n": n, "resolved": r}
            for (s, tf, b, a, al), (n, r) in sorted(acc.items())]


def save(conn, rows: list[dict], *, horizon: int, built_at: int, markets: list[tuple[str, str]]) -> None:
    conn.executescript(SCHEMA)
    for sym, tf in markets:
        conn.execute("DELETE FROM verdict_records WHERE timeframe=? AND symbol IN (?, ?)", (tf, sym, ALL))
    for r in rows:
        conn.execute("INSERT OR REPLACE INTO verdict_records VALUES (?,?,?,?,?,?,?,?,?)",
                     (r["symbol"], r["timeframe"], r["bias"], r["agreeing"], r["aligned"], r["n"], r["resolved"],
                      horizon, built_at))
    conn.commit()


def load(conn) -> list[dict]:
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM verdict_records").fetchall()]
    except Exception:                                      # table not built yet
        return []


def record_for(rows: list[dict], symbol: str, timeframe: str, bias: str, agreeing: int, aligned: bool) -> dict | None:
    """The record for this verdict type: this market's own row when it has MIN_N+ cases, else the
    all-markets row for the same timeframe. None for a neutral read or when nothing was built.
    Returns {scope, n, resolved, rate (None below MIN_N), insufficient, horizon, label}."""
    if bias not in ("bullish", "bearish"):
        return None
    key = lambda s: next((r for r in rows if r["symbol"] == s and r["timeframe"] == timeframe  # noqa: E731
                          and r["bias"] == bias and r["agreeing"] == agreeing and r["aligned"] == int(aligned)), None)
    own, pooled = key(symbol), key(ALL)
    pick, scope = (own, symbol) if own and own["n"] >= MIN_N else ((pooled, "all markets") if pooled else (own, symbol))
    if pick is None:
        return None
    n, res = pick["n"], pick["resolved"]
    label = f"{'categories aligned' if aligned else 'not aligned'} {bias}, {agreeing} categor{'y' if agreeing == 1 else 'ies'} agreeing"
    return {"scope": scope, "timeframe": timeframe, "n": n, "resolved": res, "horizon": pick["horizon"],
            "rate": round(res / n, 3) if n >= MIN_N else None, "insufficient": n < MIN_N, "label": label}


def record_text(rec: dict | None) -> str:
    """'categories aligned bullish, 2 categories agreeing — 212 of 430 resolved that way (49%) over 24
    bars (BTC/USDT 1d)' or '… insufficient data (7 cases)'."""
    if rec is None:
        return "no record (neutral read, or verdict records not built)"
    where = f"({rec['scope']} {rec['timeframe']})"
    if rec["insufficient"]:
        return f"{rec['label']} — insufficient data ({rec['n']} cases) {where}"
    return (f"{rec['label']} — {rec['resolved']} of {rec['n']} resolved that way ({rec['rate'] * 100:.0f}%) "
            f"over {rec['horizon']} bars {where}")
