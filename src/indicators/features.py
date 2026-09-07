"""Phase 2 — reliable tier: indicators + candlestick patterns as DataFrame columns.

`add_features(df, cfg)` takes a clean OHLCV frame (from src.data) and returns a COPY
with extra columns added. Two deliberate choices:

- **Never drops rows.** An indicator's warmup period leaves leading NaNs (the first 49
  bars have no SMA-50, etc.). We keep them: index alignment with the candles matters
  downstream, and "not enough history yet" is real information — not something to hide.

- **Moving averages are SIMPLE (SMA).** To compare values against TradingView, set its
  MA overlay to *SMA* with the same lengths. RSI uses Wilder's smoothing and MACD uses
  EMAs internally (both are TradingView's defaults), so those match TV out of the box.
  Note the data layer drops the still-forming candle, so compare against the last
  *closed* bar on TradingView, not the live one.

Candlestick patterns are hand-rolled here rather than via TA-Lib (a C dependency that
is painful to install). They are deterministic boolean columns, verified by unit tests
with hand-built candles. They are the secondary, "best-effort" tier — their thresholds
will not match TradingView's pattern tool exactly, and that's expected.

**Column names are a contract.** Import the COL_* constants below downstream (Phase 4's
trend detector reads the SMA columns) instead of hardcoding strings.
"""

from __future__ import annotations

import pandas as pd
import pandas_ta_classic as ta

from src.config import Config

# --- column-name contract: import these, never hardcode the strings ------------
COL_SMA_FAST = "sma_fast"
COL_SMA_SLOW = "sma_slow"
COL_RSI = "rsi"
COL_MACD = "macd"
COL_MACD_SIGNAL = "macd_signal"
COL_MACD_HIST = "macd_hist"
COL_VOLUME = "volume"        # raw input column (present for crypto; may be absent on some frames)
COL_VOLUME_MA = "volume_ma"  # SMA of volume (Phase 15)

COL_DOJI = "doji"
COL_HAMMER = "hammer"
COL_BULLISH_ENGULFING = "bullish_engulfing"
COL_BEARISH_ENGULFING = "bearish_engulfing"

INDICATOR_COLUMNS = [
    COL_SMA_FAST,
    COL_SMA_SLOW,
    COL_RSI,
    COL_MACD,
    COL_MACD_SIGNAL,
    COL_MACD_HIST,
    COL_VOLUME_MA,
]
PATTERN_COLUMNS = [
    COL_DOJI,
    COL_HAMMER,
    COL_BULLISH_ENGULFING,
    COL_BEARISH_ENGULFING,
]

# MACD parameters — TradingView defaults, not currently exposed in config.
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9

# How small a body counts as a doji, as a fraction of the candle's full range.
DOJI_BODY_MAX_FRACTION = 0.1


def add_indicators(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add SMA(fast/slow), RSI, and MACD (line/signal/histogram) columns."""
    out = df.copy()
    ind = cfg.indicators

    out[COL_SMA_FAST] = ta.sma(out["close"], length=ind.fast_ma)
    out[COL_SMA_SLOW] = ta.sma(out["close"], length=ind.slow_ma)
    out[COL_RSI] = ta.rsi(out["close"], length=ind.rsi_period)

    macd = ta.macd(out["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    suffix = f"{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    out[COL_MACD] = macd[f"MACD_{suffix}"]
    out[COL_MACD_SIGNAL] = macd[f"MACDs_{suffix}"]
    out[COL_MACD_HIST] = macd[f"MACDh_{suffix}"]

    # Volume MA (Phase 15). The column is ALWAYS added to honour the INDICATOR_COLUMNS
    # contract; when a frame carries no volume (some synthetic/forex frames) it is all-NaN,
    # and the volume detector treats that as "no confirmation" rather than crashing.
    out[COL_VOLUME_MA] = (
        ta.sma(out[COL_VOLUME], length=ind.volume_ma)
        if COL_VOLUME in out.columns
        else float("nan")
    )
    return out


def add_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Add boolean columns for a few hand-rolled candlestick patterns.

    Definitions (single- or two-candle, deterministic):
      - doji: real body is tiny relative to the full range (indecision).
      - hammer: small body, long lower shadow (>= 2x body), short upper shadow —
        a potential bullish-reversal shape. (Context/trend is judged later, elsewhere.)
      - bullish_engulfing: a down candle followed by an up candle whose body fully
        covers the prior body.
      - bearish_engulfing: the mirror image.
    """
    out = df.copy()
    o, h, l, c = out["open"], out["high"], out["low"], out["close"]

    body = (c - o).abs()
    rng = h - l
    body_top = out[["open", "close"]].max(axis=1)
    body_bottom = out[["open", "close"]].min(axis=1)
    upper_shadow = h - body_top
    lower_shadow = body_bottom - l

    has_range = rng > 0
    out[COL_DOJI] = has_range & (body <= DOJI_BODY_MAX_FRACTION * rng)
    out[COL_HAMMER] = (
        has_range & (body > 0) & (lower_shadow >= 2 * body) & (upper_shadow <= body)
    )

    # Two-candle patterns: compare each candle with the previous one.
    prev_o, prev_c = o.shift(1), c.shift(1)
    prev_bearish = prev_c < prev_o
    prev_bullish = prev_c > prev_o
    curr_bullish = c > o
    curr_bearish = c < o

    out[COL_BULLISH_ENGULFING] = (
        prev_bearish & curr_bullish & (o <= prev_c) & (c >= prev_o)
    )
    out[COL_BEARISH_ENGULFING] = (
        prev_bullish & curr_bearish & (o >= prev_c) & (c <= prev_o)
    )
    return out


def add_features(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Return a copy of `df` with all Phase 2 indicator and pattern columns added."""
    out = add_indicators(df, cfg)
    out = add_candlestick_patterns(out)
    return out
