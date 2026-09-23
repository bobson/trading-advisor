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
COL_SMA_LONG = "sma_long"    # long trend MA (default 200), for the chart overlay
COL_RSI = "rsi"
COL_MACD = "macd"
COL_MACD_SIGNAL = "macd_signal"
COL_MACD_HIST = "macd_hist"
COL_VOLUME = "volume"        # raw input column (present for crypto; may be absent on some frames)
COL_VOLUME_MA = "volume_ma"  # SMA of volume (Phase 15)
# Phase 18 toolkit columns (facts/context).
COL_ATR = "atr"
COL_ADX = "adx"              # trend strength (non-directional)
COL_STOCH_K = "stoch_k"
COL_STOCH_D = "stoch_d"
COL_BB_UPPER = "bb_upper"
COL_BB_MID = "bb_mid"
COL_BB_LOWER = "bb_lower"
COL_BB_PCT = "bb_pct"        # %B: where close sits across the bands (0=lower, 1=upper)
COL_OBV = "obv"

COL_DOJI = "doji"
COL_HAMMER = "hammer"
COL_SHOOTING_STAR = "shooting_star"
COL_BULLISH_ENGULFING = "bullish_engulfing"
COL_BEARISH_ENGULFING = "bearish_engulfing"
# Three-candle patterns (facts-only — surfaced + charted, NOT fed into any confluence vote).
COL_MORNING_STAR = "morning_star"
COL_EVENING_STAR = "evening_star"
COL_THREE_WHITE_SOLDIERS = "three_white_soldiers"
COL_THREE_BLACK_CROWS = "three_black_crows"

INDICATOR_COLUMNS = [
    COL_SMA_FAST,
    COL_SMA_SLOW,
    COL_SMA_LONG,
    COL_RSI,
    COL_MACD,
    COL_MACD_SIGNAL,
    COL_MACD_HIST,
    COL_VOLUME_MA,
    COL_ATR,
    COL_ADX,
    COL_STOCH_K,
    COL_STOCH_D,
    COL_BB_UPPER,
    COL_BB_MID,
    COL_BB_LOWER,
    COL_BB_PCT,
    COL_OBV,
]
PATTERN_COLUMNS = [
    COL_DOJI,
    COL_HAMMER,
    COL_SHOOTING_STAR,
    COL_BULLISH_ENGULFING,
    COL_BEARISH_ENGULFING,
    COL_MORNING_STAR,
    COL_EVENING_STAR,
    COL_THREE_WHITE_SOLDIERS,
    COL_THREE_BLACK_CROWS,
]

# The three-candle patterns marked on the chart (label + direction). Deliberately ONLY the
# three-candle set — single/two-candle patterns (doji/hammer/engulfing) are too frequent to mark
# without carpeting the chart; they already surface via the candlestick vote + facts read.
THREE_CANDLE_PATTERNS = [
    (COL_MORNING_STAR, "morning star", "bullish"),
    (COL_EVENING_STAR, "evening star", "bearish"),
    (COL_THREE_WHITE_SOLDIERS, "three white soldiers", "bullish"),
    (COL_THREE_BLACK_CROWS, "three black crows", "bearish"),
]

# MACD parameters — TradingView defaults, not currently exposed in config.
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9

# How small a body counts as a doji, as a fraction of the candle's full range.
DOJI_BODY_MAX_FRACTION = 0.1

# Three-candle pattern thresholds (module constants, like DOJI_BODY_MAX_FRACTION — not config).
STRONG_BODY_MIN_FRACTION = 0.5   # candles 1 & 3 of a star must be "real-bodied" (body >= half range)
STAR_BODY_MAX_RATIO = 0.5        # the star (middle) body is at most half of candle 1's body
SOLDIER_WICK_MAX_FRACTION = 0.3  # soldiers/crows close near their extreme (small opposing wick)


def add_indicators(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add SMA(fast/slow), RSI, and MACD (line/signal/histogram) columns."""
    out = df.copy()
    ind = cfg.indicators

    out[COL_SMA_FAST] = ta.sma(out["close"], length=ind.fast_ma)
    out[COL_SMA_SLOW] = ta.sma(out["close"], length=ind.slow_ma)
    long_sma = ta.sma(out["close"], length=ind.long_ma)   # None on frames shorter than the length
    out[COL_SMA_LONG] = long_sma if long_sma is not None else float("nan")
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

    # Phase 18 toolkit — ATR (volatility), ADX (trend strength), Stochastic (momentum),
    # Bollinger Bands (volatility envelope), OBV (volume-momentum). All FACTS for now, no
    # vote. pandas-ta returns None on frames too short for a given length, so `_col` guards
    # that (the same NoneType-subscript shape that bit MACD once).
    atr = ta.atr(out["high"], out["low"], out["close"], length=ind.atr_period)
    out[COL_ATR] = atr if atr is not None else float("nan")

    adx = ta.adx(out["high"], out["low"], out["close"], length=ind.adx_period)
    out[COL_ADX] = _col(adx, "ADX_")

    stoch = ta.stoch(out["high"], out["low"], out["close"], k=ind.stoch_k, d=ind.stoch_d)
    out[COL_STOCH_K] = _col(stoch, "STOCHk_")
    out[COL_STOCH_D] = _col(stoch, "STOCHd_")

    bb = ta.bbands(out["close"], length=ind.bb_period, std=ind.bb_stddev)
    out[COL_BB_LOWER] = _col(bb, "BBL_")
    out[COL_BB_MID] = _col(bb, "BBM_")
    out[COL_BB_UPPER] = _col(bb, "BBU_")
    out[COL_BB_PCT] = _col(bb, "BBP_")

    out[COL_OBV] = (
        ta.obv(out["close"], out[COL_VOLUME]) if COL_VOLUME in out.columns else float("nan")
    )
    return out


def _col(frame, prefix: str):
    """Pick the column starting with `prefix` from a pandas-ta result, or NaN if the result is
    None (frame too short) or the column is missing. Matches by prefix so the exact param
    suffix (e.g. ADX_14, BBL_20_2.0) never has to be hardcoded.
    """
    if frame is None:
        return float("nan")
    for c in frame.columns:
        if c.startswith(prefix):
            return frame[c]
    return float("nan")


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
    # shooting star: the bearish mirror of the hammer — small body near the low, long upper
    # shadow (>= 2x body), short lower shadow. A potential bearish-reversal shape.
    out[COL_SHOOTING_STAR] = (
        has_range & (body > 0) & (upper_shadow >= 2 * body) & (lower_shadow <= body)
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

    # Three-candle patterns: candle A = two bars back (shift 2), candle B = one bar back (shift 1),
    # candle C = current. Gaps are NOT required (24/7 crypto rarely gaps) — the reversal is proven by
    # candle C closing beyond the MIDPOINT of candle A's body instead.
    oA, hA, lA, cA = o.shift(2), h.shift(2), l.shift(2), c.shift(2)
    oB, hB, lB, cB = o.shift(1), h.shift(1), l.shift(1), c.shift(1)
    bodyA, bodyB, bodyC = (cA - oA).abs(), (cB - oB).abs(), body
    rngA, rngB = (hA - lA), (hB - lB)
    midA = (oA + cA) / 2.0
    strongA = bodyA >= STRONG_BODY_MIN_FRACTION * rngA
    strongC = bodyC >= STRONG_BODY_MIN_FRACTION * rng
    small_star = bodyB <= STAR_BODY_MAX_RATIO * bodyA          # middle body dwarfed by candle A

    # Morning star: strong DOWN candle -> small-bodied star -> strong UP candle closing above the
    # midpoint of candle A's body (bullish reversal). Evening star is the mirror.
    out[COL_MORNING_STAR] = (
        has_range & (cA < oA) & strongA & small_star & (c > o) & strongC & (c > midA)
    )
    out[COL_EVENING_STAR] = (
        has_range & (cA > oA) & strongA & small_star & (c < o) & strongC & (c < midA)
    )

    # Three white soldiers: three rising green candles, each opening inside the prior real body and
    # closing progressively higher AND near its own high (small upper shadow). Three black crows mirror.
    not_doji = (
        (bodyA > DOJI_BODY_MAX_FRACTION * rngA)
        & (bodyB > DOJI_BODY_MAX_FRACTION * rngB)
        & (bodyC > DOJI_BODY_MAX_FRACTION * rng)
    )
    up_A, up_B, up_C = (cA > oA), (cB > oB), (c > o)
    close_near_high = (
        ((hA - cA) <= SOLDIER_WICK_MAX_FRACTION * rngA)
        & ((hB - cB) <= SOLDIER_WICK_MAX_FRACTION * rngB)
        & ((h - c) <= SOLDIER_WICK_MAX_FRACTION * rng)
    )
    out[COL_THREE_WHITE_SOLDIERS] = (
        has_range & up_A & up_B & up_C & not_doji
        & (cB > cA) & (c > cB)                                 # progressively higher closes
        & (oB > oA) & (oB < cA) & (o > oB) & (o < cB)          # each opens within the prior body
        & close_near_high
    )
    dn_A, dn_B, dn_C = (cA < oA), (cB < oB), (c < o)
    close_near_low = (
        ((cA - lA) <= SOLDIER_WICK_MAX_FRACTION * rngA)
        & ((cB - lB) <= SOLDIER_WICK_MAX_FRACTION * rngB)
        & ((c - l) <= SOLDIER_WICK_MAX_FRACTION * rng)
    )
    out[COL_THREE_BLACK_CROWS] = (
        has_range & dn_A & dn_B & dn_C & not_doji
        & (cB < cA) & (c < cB)                                 # progressively lower closes
        & (oB < oA) & (oB > cA) & (o < oB) & (o > cB)          # each opens within the prior body
        & close_near_low
    )
    return out


# Precedence for naming the ONE most-significant candlestick pattern on a bar: three-candle first
# (rarest/strongest), then two-candle, then single-candle. Facts-only — never feeds a vote.
_CANDLE_READ_ORDER = [
    (COL_MORNING_STAR, "morning star", "bullish"),
    (COL_EVENING_STAR, "evening star", "bearish"),
    (COL_THREE_WHITE_SOLDIERS, "three white soldiers", "bullish"),
    (COL_THREE_BLACK_CROWS, "three black crows", "bearish"),
    (COL_BULLISH_ENGULFING, "bullish engulfing", "bullish"),
    (COL_BEARISH_ENGULFING, "bearish engulfing", "bearish"),
    (COL_HAMMER, "hammer", "bullish"),
    (COL_SHOOTING_STAR, "shooting star", "bearish"),
    (COL_DOJI, "doji", "neutral"),
]


def candlestick_read(featured_df: pd.DataFrame) -> dict | None:
    """Name the strongest candlestick pattern on the LAST closed bar (three-candle patterns take
    precedence), or None. Facts-only: this does NOT feed any confluence vote. A morning/evening star
    whose middle bar is doji-sized is labelled a 'doji star' (the classic named variant)."""
    if len(featured_df) == 0:
        return None
    last = featured_df.iloc[-1]
    for col, label, direction in _CANDLE_READ_ORDER:
        if col in featured_df.columns and bool(last.get(col, False)):
            if col in (COL_MORNING_STAR, COL_EVENING_STAR) and len(featured_df) >= 2 \
                    and bool(featured_df.iloc[-2].get(COL_DOJI, False)):
                label = f"{label} (doji star)"
            return {"pattern": label, "direction": direction}
    return None


def add_features(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Return a copy of `df` with all Phase 2 indicator and pattern columns added."""
    out = add_indicators(df, cfg)
    out = add_candlestick_patterns(out)
    return out
