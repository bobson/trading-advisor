"""Tests for Phase 6 confluence engine.

Two layers of test, matching the module's split:
  - `evaluate_confluence` on hand-built Signal lists (the pure tally rule).
  - the per-detector vote functions on hand-built facts (each maps to the right direction).
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
    COL_MACD_SIGNAL,
    COL_RSI,
    COL_VOLUME,
    COL_VOLUME_MA,
)
from src.signals.confluence import (
    BEARISH,
    BULLISH,
    NEUTRAL,
    Signal,
    evaluate_confluence,
    signal_from_fibonacci,
    signal_from_macd,
    signal_from_patterns,
    signal_from_rsi,
    signal_from_support_resistance,
    signal_from_trend,
    signal_from_volume,
)
from src.structure.fibonacci import FibRetracement
from src.structure.trend import DOWNTREND, SIDEWAYS, UPTREND, TrendResult


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _sig(name, direction):
    """A signal with a REAL detector name so it maps to a category (Phase 17)."""
    return Signal(name, direction, f"{name}:{direction}")


# --- evaluate_confluence (category-aware, 0–1 confidence) ----------------------

def test_flags_when_enough_categories_agree(cfg):
    # trend + momentum = two independent categories -> reaches require_categories (2)
    r = evaluate_confluence([_sig("trend", BULLISH), _sig("rsi", BULLISH)], cfg)
    assert r.bias == BULLISH and r.triggered
    assert r.agreeing_categories == 2
    assert 0.0 < r.confidence <= 1.0


def test_does_not_fire_below_required_categories(cfg):
    r = evaluate_confluence([_sig("trend", BULLISH)], cfg)  # one category only
    assert r.bias == BULLISH and not r.triggered
    assert r.agreeing_categories == 1


def test_correlated_signals_collapse_into_one_category(cfg):
    # S/R and fib are both "structure" — the double-count the plan calls out is gone.
    r = evaluate_confluence([_sig("support_resistance", BULLISH), _sig("fibonacci", BULLISH)], cfg)
    assert r.categories["structure"] == BULLISH
    assert r.agreeing_categories == 1     # collapsed to ONE category
    assert not r.triggered                # 1 < require_categories (2)


def test_category_internal_conflict_nets_neutral(cfg):
    r = evaluate_confluence([_sig("rsi", BULLISH), _sig("macd", BEARISH)], cfg)
    assert r.categories["momentum"] == NEUTRAL
    assert r.bias == NEUTRAL and not r.triggered


def test_weight_tie_never_fires(cfg):
    # trend bull (1.0) vs momentum bear (1.0): equal weight -> neutral, no setup.
    sigs = [_sig("trend", BULLISH), _sig("rsi", BEARISH), _sig("macd", BEARISH)]
    r = evaluate_confluence(sigs, cfg)
    assert r.bias == NEUTRAL and not r.triggered


def test_heavier_category_wins(cfg):
    # structure (1.2) outweighs trend (1.0), so bearish wins despite trend being bullish.
    sigs = [_sig("trend", BULLISH), _sig("support_resistance", BEARISH), _sig("fibonacci", BEARISH)]
    r = evaluate_confluence(sigs, cfg)
    assert r.bias == BEARISH


def test_contributing_is_category_consistent(cfg):
    # trend+momentum (2.0) beat structure (1.2) -> bullish; structure signals must NOT show as
    # contributing even though this is a mixed set.
    sigs = [_sig("trend", BULLISH), _sig("rsi", BULLISH),
            _sig("support_resistance", BEARISH), _sig("fibonacci", BEARISH)]
    r = evaluate_confluence(sigs, cfg)
    assert r.bias == BULLISH and r.triggered
    assert {s.name for s in r.contributing} == {"trend", "rsi"}


# --- per-detector votes --------------------------------------------------------

def test_trend_votes():
    assert signal_from_trend(TrendResult(UPTREND, ["up"])).direction == BULLISH
    assert signal_from_trend(TrendResult(DOWNTREND, ["down"])).direction == BEARISH
    assert signal_from_trend(TrendResult(SIDEWAYS, ["flat"])).direction == NEUTRAL


def _one_row(**cols):
    return pd.DataFrame([cols])


def test_rsi_votes(cfg):
    assert signal_from_rsi(_one_row(**{COL_RSI: 25.0}), cfg).direction == BULLISH
    assert signal_from_rsi(_one_row(**{COL_RSI: 75.0}), cfg).direction == BEARISH
    assert signal_from_rsi(_one_row(**{COL_RSI: 50.0}), cfg).direction == NEUTRAL
    assert signal_from_rsi(_one_row(**{COL_RSI: np.nan}), cfg).direction == NEUTRAL


def test_macd_votes():
    assert signal_from_macd(_one_row(**{COL_MACD: 1.0, COL_MACD_SIGNAL: 0.5})).direction == BULLISH
    assert signal_from_macd(_one_row(**{COL_MACD: 0.5, COL_MACD_SIGNAL: 1.0})).direction == BEARISH
    assert signal_from_macd(_one_row(**{COL_MACD: np.nan, COL_MACD_SIGNAL: 1.0})).direction == NEUTRAL


def _pattern_row(bull_eng=False, hammer=False, bear_eng=False, doji=False):
    return _one_row(**{
        COL_BULLISH_ENGULFING: bull_eng,
        COL_HAMMER: hammer,
        COL_BEARISH_ENGULFING: bear_eng,
        COL_DOJI: doji,
    })


def test_pattern_votes():
    assert signal_from_patterns(_pattern_row(bull_eng=True)).direction == BULLISH
    assert signal_from_patterns(_pattern_row(hammer=True)).direction == BULLISH
    assert signal_from_patterns(_pattern_row(bear_eng=True)).direction == BEARISH
    assert signal_from_patterns(_pattern_row(doji=True)).direction == NEUTRAL
    assert signal_from_patterns(_pattern_row()).direction == NEUTRAL


def _levels(records):
    return pd.DataFrame(records, columns=["price", "touches"])


def test_sr_votes_bullish_on_support():
    # a level at 99.8 sits below last_close (support), 0.2% away -> within 0.5% -> bullish
    levels = _levels([(99.8, 3), (90.0, 2)])
    sig = signal_from_support_resistance(levels, last_close=100.0, proximity_pct=0.5)
    assert sig.direction == BULLISH


def test_sr_votes_bearish_on_resistance():
    # a level above last_close is resistance -> bearish
    levels = _levels([(100.3, 3)])
    sig = signal_from_support_resistance(levels, last_close=100.0, proximity_pct=0.5)
    assert sig.direction == BEARISH


def test_sr_neutral_when_far():
    levels = _levels([(120.0, 3)])
    sig = signal_from_support_resistance(levels, last_close=100.0, proximity_pct=0.5)
    assert sig.direction == NEUTRAL


def _fib(direction, levels):
    return FibRetracement(
        direction=direction, high_bar=10, high_price=110.0,
        low_bar=0, low_price=100.0, levels=levels,
    )


def test_fib_bullish_on_up_leg():
    # up-leg, price sitting on the 61.8% level -> support -> bullish
    fib = _fib("up", {0.618: 103.82, 0.5: 105.0})
    sig = signal_from_fibonacci(fib, last_close=103.85, proximity_pct=0.5)
    assert sig.direction == BULLISH


def test_fib_bearish_on_down_leg():
    fib = _fib("down", {0.618: 106.18, 0.5: 105.0})
    sig = signal_from_fibonacci(fib, last_close=106.15, proximity_pct=0.5)
    assert sig.direction == BEARISH


def test_fib_neutral_when_none():
    assert signal_from_fibonacci(None, last_close=100.0, proximity_pct=0.5).direction == NEUTRAL


def test_volume_confirms_candle_direction(cfg):
    # above-average volume (3x, >= 1.2 factor) confirms whichever way the candle closed
    up = _one_row(**{COL_VOLUME: 300.0, COL_VOLUME_MA: 100.0, "open": 100.0, "close": 101.0})
    assert signal_from_volume(up, cfg).direction == BULLISH
    down = _one_row(**{COL_VOLUME: 300.0, COL_VOLUME_MA: 100.0, "open": 101.0, "close": 100.0})
    assert signal_from_volume(down, cfg).direction == BEARISH


def test_volume_neutral_when_thin_missing_or_nan(cfg):
    thin = _one_row(**{COL_VOLUME: 90.0, COL_VOLUME_MA: 100.0, "open": 100.0, "close": 101.0})
    assert signal_from_volume(thin, cfg).direction == NEUTRAL      # 0.9x < 1.2x bar
    missing = _one_row(**{COL_RSI: 50.0})                          # no volume columns at all
    assert signal_from_volume(missing, cfg).direction == NEUTRAL
    nan = _one_row(**{COL_VOLUME: np.nan, COL_VOLUME_MA: 100.0, "open": 100.0, "close": 101.0})
    assert signal_from_volume(nan, cfg).direction == NEUTRAL
