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
)
from src.structure.fibonacci import FibRetracement
from src.structure.trend import DOWNTREND, SIDEWAYS, UPTREND, TrendResult


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _sig(direction, name="x"):
    return Signal(name, direction, f"{name}:{direction}")


# --- evaluate_confluence (the pure tally rule) ---------------------------------

def test_fires_when_enough_agree():
    result = evaluate_confluence([_sig(BULLISH, "a"), _sig(BULLISH, "b")], min_agreeing=2)
    assert result.bias == BULLISH
    assert result.triggered
    assert result.agreeing == 2


def test_does_not_fire_below_threshold():
    result = evaluate_confluence([_sig(BULLISH), _sig(NEUTRAL)], min_agreeing=2)
    assert result.bias == BULLISH  # bullish still leads
    assert not result.triggered
    assert result.agreeing == 1


def test_neutral_votes_do_not_count():
    signals = [_sig(BULLISH, "a"), _sig(NEUTRAL, "b"), _sig(NEUTRAL, "c")]
    result = evaluate_confluence(signals, min_agreeing=2)
    assert not result.triggered
    assert result.agreeing == 1


def test_tie_never_fires():
    # 2 bullish / 2 bearish: genuine disagreement is not a setup.
    signals = [_sig(BULLISH, "a"), _sig(BULLISH, "b"), _sig(BEARISH, "c"), _sig(BEARISH, "d")]
    result = evaluate_confluence(signals, min_agreeing=2)
    assert result.bias == NEUTRAL
    assert not result.triggered


def test_strictly_greater_side_wins_despite_conflict():
    # 3 bullish / 2 bearish, min 2: bullish wins even though bearish also reaches the count.
    signals = [_sig(BULLISH, "a"), _sig(BULLISH, "b"), _sig(BULLISH, "c"),
               _sig(BEARISH, "d"), _sig(BEARISH, "e")]
    result = evaluate_confluence(signals, min_agreeing=2)
    assert result.bias == BULLISH
    assert result.triggered
    assert result.agreeing == 3


def test_contributing_reasons_are_the_winning_side():
    signals = [_sig(BULLISH, "a"), _sig(BULLISH, "b"), _sig(BEARISH, "c")]
    result = evaluate_confluence(signals, min_agreeing=2)
    assert result.reasons == ["a:bullish", "b:bullish"]
    assert all(s.direction == BULLISH for s in result.contributing)


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
