"""Recommendation #3 — does crowded funding actually precede contrarian moves?

Phase 22 shipped funding as a FACT and deferred the vote until measured. This is the measure:
align the historical funding rate onto the price bars (look-ahead-safe — each bar sees only
funding settled at or before it), then compare forward returns after "crowded longs" / "crowded
shorts" readings against the baseline of all bars. Funding earns a VOTE only if extremes clearly
skew forward returns the contrarian way. (Given Rec #1 found no engine edge, expect this to be
inconclusive — that's a valid, documented outcome, not a failure.)
"""

from __future__ import annotations

import pandas as pd


def fetch_funding_history(exchange, perp: str, since_ms: int, limit: int = 1000, max_pages: int = 12) -> pd.Series:
    """Paginated historical funding rate (UTC-indexed Series), via a ccxt-like exchange."""
    rows: list[dict] = []
    since = since_ms
    for _ in range(max_pages):
        batch = exchange.fetch_funding_rate_history(perp, since=since, limit=limit)
        if not batch:
            break
        rows.extend(batch)
        last = batch[-1]["timestamp"]
        if last <= since or len(batch) < limit:
            break
        since = last + 1
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r["timestamp"] for r in rows], unit="ms", utc=True)
    s = pd.Series([float(r["fundingRate"]) for r in rows], index=idx).sort_index()
    return s[~s.index.duplicated(keep="last")]


def align_funding(candles_index: pd.DatetimeIndex, funding: pd.Series) -> pd.Series:
    """For each candle, the last funding settled AT OR BEFORE it (forward-fill = look-ahead-safe).
    Bars before the first known settlement are NaN."""
    if funding.empty:
        return pd.Series(index=candles_index, dtype=float)
    f = funding.sort_index()
    return f.reindex(f.index.union(candles_index)).ffill().reindex(candles_index)


def _stat(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0, "mean_fwd_pct": None, "pct_up": None}
    return {
        "n": len(xs),
        "mean_fwd_pct": round(sum(xs) / len(xs) * 100, 3),
        "pct_up": round(sum(1 for x in xs if x > 0) / len(xs) * 100, 1),
    }


def study_funding(candles_df: pd.DataFrame, funding_bar: pd.Series, cfg, horizon: int = 24, decile: float = 0.1) -> dict:
    """Bucket forward returns by RELATIVE funding crowding and compare to baseline.

    A fixed threshold is useless when the whole regime is low-funding (every bar reads
    "neutral"), so we use the period's top/bottom `decile` of funding as "high"/"low" crowding.
    (The percentile threshold is computed over the whole period — a mild in-sample choice for
    the *threshold* only; the price forward-returns remain strictly look-ahead-safe.)
    """
    close = candles_df["close"].to_numpy()
    fb = funding_bar.to_numpy()
    n = len(close)

    usable = [(i, float(fb[i])) for i in range(n - horizon) if not pd.isna(fb[i])]
    if not usable:
        empty = {"n": 0, "mean_fwd_pct": None, "pct_up": None}
        return {"horizon": horizon, "hi_threshold": None, "lo_threshold": None,
                "all": empty, "high_funding": empty, "low_funding": empty}

    vals = sorted(v for _, v in usable)
    hi = vals[min(int((1 - decile) * len(vals)), len(vals) - 1)]
    lo = vals[int(decile * len(vals))]

    buckets: dict[str, list[float]] = {"all": [], "high_funding": [], "low_funding": []}
    for i, f in usable:
        fwd = close[i + horizon] / close[i] - 1.0
        buckets["all"].append(fwd)
        if f >= hi:
            buckets["high_funding"].append(fwd)   # most crowded-long -> contrarian expects DOWN
        if f <= lo:
            buckets["low_funding"].append(fwd)     # most crowded-short -> contrarian expects UP

    return {"horizon": horizon, "hi_threshold": round(hi, 6), "lo_threshold": round(lo, 6),
            **{k: _stat(v) for k, v in buckets.items()}}
