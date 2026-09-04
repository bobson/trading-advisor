"""Tests for Phase 2 indicators and candlestick patterns.

Indicators: the "done when" ("matches TradingView") is a user-side visual compare, but
we can still catch wiring mistakes here with internal-consistency checks (SMA equals a
rolling mean, MACD histogram equals line minus signal, RSI stays in range).

Patterns: verified the way the plan emphasizes for detectors — hand-built candles where
the expected answer is obvious.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.indicators.features import (
    COL_BEARISH_ENGULFING,
    COL_BULLISH_ENGULFING,
    COL_DOJI,
    COL_HAMMER,
    COL_MACD,
    COL_MACD_HIST,
    COL_MACD_SIGNAL,
    COL_RSI,
    COL_SMA_FAST,
    COL_SMA_SLOW,
    INDICATOR_COLUMNS,
    PATTERN_COLUMNS,
    add_candlestick_patterns,
    add_features,
)


@pytest.fixture
def cfg():
    return load_config()


def _synthetic_ohlcv(n=200, seed=0):
    """Deterministic random-walk candles — enough rows to warm up SMA-50/MACD."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0, 1, n)
    low = np.minimum(open_, close) - rng.uniform(0, 1, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.uniform(1, 100, n)},
        index=idx,
    )


def _candle(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1.0}


# --- indicators ----------------------------------------------------------------

def test_add_features_adds_all_columns_and_keeps_length(cfg):
    df = _synthetic_ohlcv()
    feat = add_features(df, cfg)
    for col in INDICATOR_COLUMNS + PATTERN_COLUMNS:
        assert col in feat.columns
    assert len(feat) == len(df)  # no rows dropped


def test_sma_equals_rolling_mean(cfg):
    df = _synthetic_ohlcv()
    feat = add_features(df, cfg)
    expected_fast = df["close"].rolling(cfg.indicators.fast_ma).mean()
    pd.testing.assert_series_equal(
        feat[COL_SMA_FAST], expected_fast, check_names=False
    )


def test_macd_histogram_is_line_minus_signal(cfg):
    df = _synthetic_ohlcv()
    feat = add_features(df, cfg).dropna(subset=[COL_MACD, COL_MACD_SIGNAL])
    diff = feat[COL_MACD] - feat[COL_MACD_SIGNAL]
    assert np.allclose(feat[COL_MACD_HIST], diff, atol=1e-9)


def test_rsi_within_range_and_warmup_nans(cfg):
    df = _synthetic_ohlcv()
    feat = add_features(df, cfg)
    rsi = feat[COL_RSI].dropna()
    assert rsi.between(0, 100).all()
    # SMA-50 must have leading NaNs during warmup (kept, not dropped).
    assert feat[COL_SMA_SLOW].iloc[: cfg.indicators.slow_ma - 1].isna().all()


# --- candlestick patterns (hand-built candles) ---------------------------------

def test_doji_fires_on_tiny_body():
    # open≈close, with wicks both sides -> tiny body vs range
    df = pd.DataFrame([_candle(100, 105, 95, 100.2)])
    out = add_candlestick_patterns(df)
    assert bool(out[COL_DOJI].iloc[0])


def test_doji_does_not_fire_on_big_body():
    df = pd.DataFrame([_candle(100, 110, 99, 109)])
    out = add_candlestick_patterns(df)
    assert not bool(out[COL_DOJI].iloc[0])


def test_hammer_fires_on_long_lower_shadow():
    # small body at the top, long lower wick, ~no upper wick
    df = pd.DataFrame([_candle(100, 100.3, 90, 100.2)])
    out = add_candlestick_patterns(df)
    assert bool(out[COL_HAMMER].iloc[0])


def test_bullish_engulfing():
    # candle 0: down (100 -> 96). candle 1: up (95 -> 101) engulfing the prior body.
    df = pd.DataFrame([_candle(100, 100.5, 95.5, 96), _candle(95, 101.5, 94.5, 101)])
    out = add_candlestick_patterns(df)
    assert not bool(out[COL_BULLISH_ENGULFING].iloc[0])  # needs a prior candle
    assert bool(out[COL_BULLISH_ENGULFING].iloc[1])
    assert not bool(out[COL_BEARISH_ENGULFING].iloc[1])


def test_bearish_engulfing():
    # candle 0: up (96 -> 100). candle 1: down (101 -> 95) engulfing the prior body.
    df = pd.DataFrame([_candle(96, 100.5, 95.5, 100), _candle(101, 101.5, 94.5, 95)])
    out = add_candlestick_patterns(df)
    assert bool(out[COL_BEARISH_ENGULFING].iloc[1])
    assert not bool(out[COL_BULLISH_ENGULFING].iloc[1])


def test_pattern_columns_are_boolean():
    df = _synthetic_ohlcv(n=60)
    out = add_candlestick_patterns(df)
    for col in PATTERN_COLUMNS:
        assert out[col].dtype == bool
