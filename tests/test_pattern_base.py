"""Feature 2 — the pattern machinery: state machine + confirmation profile, in isolation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators.features import (
    COL_ATR,
    COL_BEARISH_ENGULFING,
    COL_BULLISH_ENGULFING,
    COL_DOJI,
    COL_HAMMER,
    COL_MACD,
    COL_MACD_SIGNAL,
    COL_SHOOTING_STAR,
    COL_VOLUME,
    COL_VOLUME_MA,
)
from src.patterns.base import (
    BEARISH,
    BULLISH,
    CONFIRMED,
    CONTRADICTS,
    FAILED,
    FORMING,
    NEUTRAL,
    NEUTRAL_DIR,
    SUPPORTS,
    UNAVAILABLE,
    ConfirmationProfile,
    build_confirmation,
    classify_state,
)


# --- state machine (look-ahead-safe: only last_close) ---------------------------------------

def test_classify_state_bullish():
    assert classify_state(BULLISH, 110, 90, last_close=115) == CONFIRMED
    assert classify_state(BULLISH, 110, 90, last_close=100) == FORMING
    assert classify_state(BULLISH, 110, 90, last_close=85) == FAILED


def test_classify_state_bearish():
    assert classify_state(BEARISH, 90, 110, last_close=85) == CONFIRMED
    assert classify_state(BEARISH, 90, 110, last_close=100) == FORMING
    assert classify_state(BEARISH, 90, 110, last_close=115) == FAILED


def test_classify_state_neutral_and_missing_levels():
    assert classify_state(NEUTRAL_DIR, 110, 90, last_close=200) == FORMING
    assert classify_state(BULLISH, None, None, last_close=115) == FORMING


# --- confirmation profile bookkeeping -------------------------------------------------------

def test_profile_counts_and_score():
    p = ConfirmationProfile(price=SUPPORTS, volume=SUPPORTS, momentum=CONTRADICTS)
    c = p.counts()
    assert c == {"supports": 2, "contradicts": 1, "neutral": 0, "available": 3}
    assert p.score() == round((2 - 1) / 3, 3)
    assert ConfirmationProfile().score() == 0.0          # nothing available -> 0


# --- build_confirmation reads bar N -----------------------------------------------------------

def _frame(*, direction_bull=True, n=8):
    """A featured frame whose LAST bar looks like a clean bullish break: expansion volume, MACD
    up, ATR rising, a bullish candle."""
    close = np.linspace(100, 112, n)
    df = pd.DataFrame({"close": close})
    df[COL_VOLUME] = 1000.0; df.loc[df.index[-1], COL_VOLUME] = 2000.0
    df[COL_VOLUME_MA] = 1000.0
    df[COL_MACD] = 1.0; df[COL_MACD_SIGNAL] = 0.5           # macd > signal (bullish)
    df[COL_ATR] = np.linspace(1.0, 3.0, n)                  # rising
    for c in (COL_BULLISH_ENGULFING, COL_HAMMER, COL_BEARISH_ENGULFING, COL_SHOOTING_STAR, COL_DOJI):
        df[c] = False
    df.loc[df.index[-1], COL_HAMMER] = True                  # a bullish reversal candle
    return df


def test_all_supports_for_a_clean_bullish_break():
    p = build_confirmation(BULLISH, breakout_level=105, invalidation_level=95, featured_df=_frame(),
                           state=CONFIRMED, higher_tf_trend="uptrend", structure_hit=True)
    assert p.price == SUPPORTS and p.volume == SUPPORTS and p.momentum == SUPPORTS
    assert p.volatility == SUPPORTS and p.candlestick == SUPPORTS
    assert p.higher_tf == SUPPORTS and p.structure == SUPPORTS
    assert p.score() == 1.0


def test_same_signals_contradict_a_bearish_pattern():
    p = build_confirmation(BEARISH, breakout_level=95, invalidation_level=105, featured_df=_frame(),
                           state=FORMING, higher_tf_trend="uptrend", structure_hit=False)
    assert p.momentum == CONTRADICTS          # MACD is bullish, pattern is bearish
    assert p.candlestick == CONTRADICTS       # bullish candle against a bearish pattern
    assert p.higher_tf == CONTRADICTS         # uptrend opposes a bearish pattern
    assert p.structure == NEUTRAL             # structure_hit False -> neutral, not a vote


def test_categories_are_unavailable_when_inputs_missing():
    df = pd.DataFrame({"close": [100, 101, 102]})   # no volume/macd/atr/candles
    p = build_confirmation(BULLISH, 101, 99, df, state=FORMING)
    assert p.volume == UNAVAILABLE and p.momentum == UNAVAILABLE
    assert p.volatility == UNAVAILABLE and p.candlestick == UNAVAILABLE
    assert p.higher_tf == UNAVAILABLE and p.structure == UNAVAILABLE
    assert p.price == "neutral"               # price is always readable from state
