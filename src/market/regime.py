"""Feature 6 — market regime: label every bar as one of five states so everything downstream
(the pattern encyclopedia especially) can segment by it.

    trending_up / trending_down — ADX says a trend is present, the slow-MA slope says which way
    ranging                     — no trend, middling volatility (chop around a level)
    volatile                    — no trend but volatility is high (whipsaw)
    quiet                       — no trend and volatility is compressed

The three ingredients are all CAUSAL and use ROLLING windows only — never whole-series
statistics, which would leak the future into early bars:
  - **ADX** (trend presence) — already a causal column from `add_features`.
  - **slow-MA slope** over `slope_window` bars (direction), as a % change.
  - **ATR percentile** over a rolling `atr_percentile_window` (volatility), i.e. where the current
    ATR ranks within its own trailing window — so "high vol" is relative to the recent past, not
    to a future we can't see.

Trend takes priority: a trending market that also happens to be volatile is still `trending_*`
(that's the tradable state), so volatility only decides the label when ADX is below threshold.

**Hysteresis** stops the label flickering bar to bar: a new regime must persist `persist_bars`
consecutive bars before it takes over (a one-bar blip is ignored). The pass is a causal forward
scan — the emitted label at bar i depends only on raw labels at bars <= i — so it stays
look-ahead-safe (a test proves mutating future bars never changes an earlier label).

Defaults are tuned for multi-week trend following on DAILY/WEEKLY bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import Config
from src.indicators.features import COL_ADX, COL_ATR, COL_SMA_SLOW, add_features

TRENDING_UP = "trending_up"
TRENDING_DOWN = "trending_down"
RANGING = "ranging"
VOLATILE = "volatile"
QUIET = "quiet"

REGIMES = (TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE, QUIET)


def _rolling_atr_percentile(atr: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Where the current ATR sits within its trailing `window` (0..1). Causal: the window ends
    at the current bar, so no future ATR is consulted."""
    def _rank(a: np.ndarray) -> float:
        return float((a <= a[-1]).mean())   # fraction of the window at or below the current bar

    return atr.rolling(window, min_periods=min_periods).apply(_rank, raw=True)


def _raw_regime(featured: pd.DataFrame, cfg: Config) -> pd.Series:
    """Per-bar regime BEFORE hysteresis. None on warm-up bars where any input is NaN."""
    rc = cfg.regime
    adx = featured[COL_ADX]
    sma = featured[COL_SMA_SLOW]
    slope_pct = (sma / sma.shift(rc.slope_window) - 1.0) * 100.0
    atr_rank = _rolling_atr_percentile(featured[COL_ATR], rc.atr_percentile_window,
                                       rc.atr_percentile_min_periods)

    thr = cfg.indicators.adx_trend_threshold
    trending = adx >= thr
    up = trending & (slope_pct > rc.slope_flat_pct)
    down = trending & (slope_pct < -rc.slope_flat_pct)
    volatile = (~trending) & (atr_rank >= rc.vol_high_pct)
    quiet = (~trending) & (atr_rank <= rc.vol_low_pct)

    # Trend wins over volatility; everything valid-but-unclassified is `ranging` (incl. a
    # trending bar with a flat slope, and a non-trending bar at middling volatility).
    raw = np.select([up, down, volatile, quiet],
                    [TRENDING_UP, TRENDING_DOWN, VOLATILE, QUIET], default=RANGING)

    valid = adx.notna() & slope_pct.notna() & atr_rank.notna()
    out = pd.Series(raw, index=featured.index, dtype=object)
    out[~valid] = None
    return out


def _apply_hysteresis(raw: pd.Series, persist: int) -> pd.Series:
    """Causal anti-flicker: a new label must appear on `persist` consecutive bars before it
    replaces the current one. The first real label is adopted immediately."""
    emitted = None          # the label currently in force
    cand = None             # the label building up a streak against `emitted`
    count = 0
    out: list = []
    for v in raw:
        if v is None or pd.isna(v):         # warm-up (None or NaN): nothing to emit yet
            out.append(emitted)
            continue
        if emitted is None:                 # adopt the first real label at once
            emitted = cand = v
            count = 0
        elif v == emitted:                  # agreement resets any pending switch
            cand = v
            count = 0
        else:                               # a differing label — build/extend its streak
            if v == cand:
                count += 1
            else:
                cand, count = v, 1
            if count >= persist:            # streak long enough -> switch
                emitted, count = cand, 0
        out.append(emitted)
    return pd.Series(out, index=raw.index, dtype=object, name="regime")


def classify_regime(featured: pd.DataFrame, cfg: Config) -> pd.Series:
    """The regime label per bar (object Series named `regime`; None during warm-up)."""
    return _apply_hysteresis(_raw_regime(featured, cfg), cfg.regime.persist_bars)


def compute_regime(df: pd.DataFrame, cfg: Config) -> pd.Series:
    """Convenience: add features to raw OHLC candles, then classify."""
    return classify_regime(add_features(df, cfg), cfg)


def add_regime(featured: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Return `featured` with a `regime` column appended (like any other indicator)."""
    out = featured.copy()
    out["regime"] = classify_regime(featured, cfg)
    return out


# --- SQLite cache (per symbol/timeframe/bar) -------------------------------------------------

def cache_regime(conn, symbol: str, timeframe: str, regime: pd.Series) -> None:
    """Upsert each bar's regime into `regime_cache`. Warm-up Nones are stored as NULL."""
    rows = [
        (symbol, timeframe, int(pd.Timestamp(ts).timestamp()), (None if v is None else str(v)))
        for ts, v in regime.items()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO regime_cache(symbol, timeframe, ts, regime) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def load_regime(conn, symbol: str, timeframe: str) -> pd.Series:
    """Read the cached regime series (UTC-indexed) for a symbol/timeframe; empty if none."""
    cur = conn.execute(
        "SELECT ts, regime FROM regime_cache WHERE symbol=? AND timeframe=? ORDER BY ts",
        (symbol, timeframe),
    )
    rows = cur.fetchall()
    idx = pd.to_datetime([r["ts"] for r in rows], unit="s", utc=True)
    return pd.Series([r["regime"] for r in rows], index=idx, dtype=object, name="regime")


def get_regime(symbol: str, timeframe: str, df: pd.DataFrame, cfg: Config, *, conn=None) -> pd.Series:
    """Compute the regime for `df`, write it to the cache, and return it. `conn` is injectable
    (tests pass an in-memory DB); when omitted a default `data/wizard.db` connection is opened."""
    regime = compute_regime(df, cfg)
    own = conn is None
    if own:
        from src.store.db import connect
        conn = connect()
    try:
        cache_regime(conn, symbol, timeframe, regime)
    finally:
        if own:
            conn.close()
    return regime
