"""ROADMAP A7 — the random-entry baseline for paper trading: what luck alone produces.

Your paper record (k closed trades) is compared with many "monkey" records on the SAME instrument:
each monkey trade enters at a random historical bar, takes a random side (long/short 50/50), and
holds for the SAME duration and SAME dollar size as the matching real trade. Repeating that
`n_runs` times gives the distribution of total P&L (and win count) that luck produces with your
exact exposure. If your result sits inside that band, the record can't tell skill from luck.

Like-for-like with the paper P&L: no fees/slippage on either side (paper P&L doesn't model them).
Pure and seedable (`random_entry_baseline`) so it is testable offline; `baseline_for_symbol`
wires it to the stored trades and cached candles.
"""

from __future__ import annotations

import numpy as np


def random_entry_baseline(
    closes: np.ndarray, holds_bars: list[int], amounts: list[float], *,
    n_runs: int = 1000, seed: int = 0, your_total: float | None = None,
) -> dict:
    """Distribution of total P&L for `n_runs` random records with the given holds and sizes.

    Returns the 5th/50th/95th percentiles of total P&L and of wins, and — when `your_total` is
    given — the share of random records that did WORSE than yours (its percentile)."""
    closes = np.asarray(closes, dtype=float)
    k = len(holds_bars)
    if k == 0 or len(closes) < 2:
        return {"n_trades": k, "n_runs": 0}
    holds = np.clip(np.asarray(holds_bars, dtype=int), 1, len(closes) - 1)
    amounts_arr = np.asarray(amounts, dtype=float)
    rng = np.random.default_rng(seed)

    # entries[i, j] = random bar for trade j in run i, leaving room for its hold
    max_start = len(closes) - 1 - holds                         # per trade
    entries = (rng.random((n_runs, k)) * (max_start + 1)).astype(int)
    exits = entries + holds
    sides = rng.choice([-1.0, 1.0], size=(n_runs, k))
    rets = (closes[exits] / closes[entries] - 1.0) * sides      # per-trade return, side-aligned
    pnl = rets * amounts_arr                                    # $ per trade
    totals = pnl.sum(axis=1)
    wins = (pnl > 0).sum(axis=1)

    out = {
        "n_trades": k,
        "n_runs": n_runs,
        "total_p05": round(float(np.percentile(totals, 5)), 2),
        "total_p50": round(float(np.percentile(totals, 50)), 2),
        "total_p95": round(float(np.percentile(totals, 95)), 2),
        "wins_p05": int(np.percentile(wins, 5)),
        "wins_p50": int(np.percentile(wins, 50)),
        "wins_p95": int(np.percentile(wins, 95)),
    }
    if your_total is not None:
        out["your_total"] = round(float(your_total), 2)
        out["your_percentile"] = round(float((totals < your_total).mean() * 100), 1)
        out["inside_luck_band"] = bool(out["total_p05"] <= your_total <= out["total_p95"])
    return out


def _tf_seconds(tf: str) -> int:
    return int(tf[:-1]) * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[tf[-1]]


def baseline_for_symbol(conn, symbol: str, cfg, *, n_runs: int = 1000, seed: int = 0,
                        candles=None) -> dict:
    """Random-entry baseline for the CLOSED paper trades on `symbol`. Holding time of each trade is
    converted to bars on the trade's timeframe (the most common one among the trades; default
    1h), at least 1 bar. `candles` is injectable for tests; otherwise cache-first `get_candles`."""
    rows = conn.execute(
        "SELECT timeframe, opened_at, closed_at, amount_usd, realized_pnl FROM trades "
        "WHERE symbol=? AND status='closed' AND closed_at IS NOT NULL", (symbol,)).fetchall()
    if not rows:
        return {"n_trades": 0, "n_runs": 0}
    tfs = [r["timeframe"] for r in rows if r["timeframe"]]
    tf = max(set(tfs), key=tfs.count) if tfs else "1h"
    if candles is None:
        from src.data.registry import get_candles
        candles = get_candles(symbol, tf, cfg)
    step = _tf_seconds(tf)
    holds = [max(1, round((r["closed_at"] - r["opened_at"]) / step)) for r in rows]
    amounts = [float(r["amount_usd"]) for r in rows]
    yours = float(sum(r["realized_pnl"] or 0.0 for r in rows))
    out = random_entry_baseline(candles["close"].to_numpy(), holds, amounts,
                                n_runs=n_runs, seed=seed, your_total=yours)
    out.update({"timeframe": tf, "history_bars": int(len(candles)),
                "note": "Random time, random side, your holding times and sizes; no costs on either side."})
    return out
