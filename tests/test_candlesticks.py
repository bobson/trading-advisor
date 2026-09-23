"""Three-candle candlestick patterns (facts-only — morning/evening star, three soldiers/crows).

Textbook fixtures prove each pattern FIRES; a no-false-positive check on the exact real BTC/USDT
1h bars the user was looking at proves it stays quiet when there's no pattern. These columns are
causal (only shift(1)/shift(2), i.e. past bars), so a look-ahead guard is included too.
"""

from __future__ import annotations

import pandas as pd

from src.indicators.features import (
    COL_DOJI,
    COL_EVENING_STAR,
    COL_MORNING_STAR,
    COL_THREE_BLACK_CROWS,
    COL_THREE_WHITE_SOLDIERS,
    add_candlestick_patterns,
    candlestick_read,
)


def _df(rows: list[dict]) -> pd.DataFrame:
    return add_candlestick_patterns(pd.DataFrame(rows))


# --- each pattern fires on its textbook shape ---------------------------------------------------

def test_morning_star_fires():
    # strong bearish -> small star -> strong bullish closing above the midpoint (95) of candle A.
    f = _df([
        dict(open=100, high=101, low=89, close=90),
        dict(open=89, high=90, low=87, close=88.5),
        dict(open=89, high=99, low=88, close=98),
    ])
    assert bool(f[COL_MORNING_STAR].iloc[-1])
    assert candlestick_read(f) == {"pattern": "morning star", "direction": "bullish"}


def test_evening_star_fires():
    f = _df([
        dict(open=90, high=101, low=89, close=100),
        dict(open=101, high=103, low=100.5, close=101.5),
        dict(open=101, high=102, low=91, close=92),
    ])
    assert bool(f[COL_EVENING_STAR].iloc[-1])
    assert candlestick_read(f) == {"pattern": "evening star", "direction": "bearish"}


def test_evening_star_with_doji_middle_is_named_doji_star():
    # middle bar is a doji (body <= 10% of its range) -> the classic "doji star" variant.
    f = _df([
        dict(open=90, high=101, low=89, close=100),
        dict(open=101, high=104, low=100, close=101.1),   # tiny body, wide range = doji
        dict(open=101, high=102, low=91, close=92),
    ])
    assert bool(f[COL_EVENING_STAR].iloc[-1])
    assert bool(f[COL_DOJI].iloc[-2])
    assert candlestick_read(f) == {"pattern": "evening star (doji star)", "direction": "bearish"}


def test_three_white_soldiers_fires():
    f = _df([
        dict(open=10, high=15.2, low=9.8, close=15),
        dict(open=13, high=18.1, low=12.9, close=18),
        dict(open=16, high=21.1, low=15.9, close=21),
    ])
    assert bool(f[COL_THREE_WHITE_SOLDIERS].iloc[-1])
    assert candlestick_read(f) == {"pattern": "three white soldiers", "direction": "bullish"}


def test_three_black_crows_fires():
    f = _df([
        dict(open=21, high=21.2, low=15.9, close=16),
        dict(open=18, high=18.1, low=12.9, close=13),
        dict(open=15, high=15.2, low=9.8, close=10),
    ])
    assert bool(f[COL_THREE_BLACK_CROWS].iloc[-1])
    assert candlestick_read(f) == {"pattern": "three black crows", "direction": "bearish"}


# --- precedence: a three-candle pattern outranks a single/two-candle one on the same bar --------

def test_three_candle_pattern_outranks_single_candle():
    # The morning star's third bar is also a hammer-ish up candle; the read must pick the star.
    f = _df([
        dict(open=100, high=101, low=89, close=90),
        dict(open=89, high=90, low=87, close=88.5),
        dict(open=89, high=99, low=88, close=98),
    ])
    read = candlestick_read(f)
    assert read is not None and read["pattern"] == "morning star"


# --- no false positive on the real bars the user was looking at ---------------------------------

def test_no_pattern_on_the_real_last_three_btc_bars():
    # The exact BTC/USDT 1h bars from the user's question: three UP candles, a doji last bar, no
    # direction flip -> NOT a star and NOT soldiers (the middle/last aren't near their highs).
    f = _df([
        dict(open=83996.0, high=84363.2, low=83500.0, close=84038.0),
        dict(open=84038.0, high=84392.6, low=83699.3, close=84326.6),
        dict(open=84326.6, high=84411.0, low=84136.0, close=84330.0),
    ])
    assert not bool(f[COL_MORNING_STAR].iloc[-1])
    assert not bool(f[COL_EVENING_STAR].iloc[-1])
    assert not bool(f[COL_THREE_WHITE_SOLDIERS].iloc[-1])
    assert not bool(f[COL_THREE_BLACK_CROWS].iloc[-1])
    # The last bar IS a doji, though — the read should say so (matching what the user saw).
    assert candlestick_read(f) == {"pattern": "doji", "direction": "neutral"}


# --- causality: a future bar can't change a past bar's pattern columns ---------------------------

def test_columns_are_look_ahead_safe():
    rows = [
        dict(open=100, high=101, low=89, close=90),
        dict(open=89, high=90, low=87, close=88.5),
        dict(open=89, high=99, low=88, close=98),
        dict(open=98, high=99, low=97, close=97.5),
    ]
    base = _df(rows)
    mutated_rows = [dict(r) for r in rows]
    mutated_rows[3] = dict(open=98, high=200, low=10, close=180)   # garble the future bar
    mutated = _df(mutated_rows)
    # bar 2 (the morning star's confirmation) must be unchanged by anything after it.
    for col in (COL_MORNING_STAR, COL_EVENING_STAR, COL_THREE_WHITE_SOLDIERS, COL_THREE_BLACK_CROWS):
        assert bool(base[col].iloc[2]) == bool(mutated[col].iloc[2])
