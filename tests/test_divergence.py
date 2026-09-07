"""Tests for Phase 18 — RSI divergence detection on swings."""

from __future__ import annotations

import pandas as pd

from src.indicators.features import COL_RSI
from src.structure.divergence import find_rsi_divergence
from src.structure.swings import SWING_HIGH, SWING_LOW


def _featured(rsi_values):
    n = len(rsi_values)
    return pd.DataFrame({"close": range(n), COL_RSI: rsi_values})


def _swings(records):
    return pd.DataFrame(records, columns=["bar", "price", "kind"])


def test_bearish_divergence_detected():
    rsi = [50.0] * 20
    rsi[5], rsi[15] = 70.0, 60.0  # RSI lower high while price makes a higher high
    d = find_rsi_divergence(_featured(rsi), _swings([(5, 100.0, SWING_HIGH), (15, 110.0, SWING_HIGH)]))
    assert d is not None and d.kind == "bearish"


def test_bullish_divergence_detected():
    rsi = [50.0] * 20
    rsi[5], rsi[15] = 30.0, 40.0  # RSI higher low while price makes a lower low
    d = find_rsi_divergence(_featured(rsi), _swings([(5, 100.0, SWING_LOW), (15, 90.0, SWING_LOW)]))
    assert d is not None and d.kind == "bullish"


def test_no_divergence_when_momentum_confirms():
    rsi = [50.0] * 20
    rsi[5], rsi[15] = 60.0, 70.0  # RSI higher high confirms the higher high -> no divergence
    assert find_rsi_divergence(_featured(rsi), _swings([(5, 100.0, SWING_HIGH), (15, 110.0, SWING_HIGH)])) is None


def test_none_with_too_few_swings():
    assert find_rsi_divergence(_featured([50.0] * 10), _swings([(5, 100.0, SWING_HIGH)])) is None
