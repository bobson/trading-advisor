"""Tests for Phase 4 structure detectors: support/resistance, trendlines, trend."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.indicators.features import COL_SMA_FAST, COL_SMA_SLOW
from src.structure.support_resistance import (
    RESISTANCE,
    SUPPORT,
    annotate_roles,
    find_support_resistance,
)
from src.structure.swings import SWING_HIGH, SWING_LOW
from src.structure.trend import DOWNTREND, SIDEWAYS, UPTREND, classify_trend
from src.structure.trendlines import find_trendlines, fit_trendline


def _swings(records):
    """records: list of (bar, price, kind)."""
    return pd.DataFrame(records, columns=["bar", "price", "kind"])


# --- support / resistance ------------------------------------------------------

def test_merges_within_tolerance():
    # 100 and 100.4 are 0.4% apart -> merge under a 0.5% tolerance
    swings = _swings([(0, 100.0, SWING_LOW), (2, 100.4, SWING_LOW)])
    levels = find_support_resistance(swings, tolerance_pct=0.5, min_touches=2)
    assert len(levels) == 1
    assert levels.loc[0, "touches"] == 2
    assert 100.0 < levels.loc[0, "price"] < 100.4


def test_does_not_merge_beyond_tolerance():
    # 100 and 100.6 are 0.6% apart -> stay separate under 0.5% tolerance.
    # (Also the discriminator for the percent-vs-fraction bug: if 0.5 were used as a
    #  fraction, i.e. a 50% band, these would wrongly merge.)
    swings = _swings([(0, 100.0, SWING_LOW), (2, 100.6, SWING_HIGH)])
    levels = find_support_resistance(swings, tolerance_pct=0.5, min_touches=1)
    assert len(levels) == 2


def test_min_touches_filters_lonely_levels():
    swings = _swings(
        [(0, 100.0, SWING_LOW), (2, 100.1, SWING_LOW), (4, 100.05, SWING_LOW),
         (6, 200.0, SWING_HIGH)]  # 200 is a single, lonely touch
    )
    levels = find_support_resistance(swings, tolerance_pct=0.5, min_touches=2)
    assert len(levels) == 1
    assert levels.loc[0, "touches"] == 3


def test_annotate_roles_relative_to_price():
    levels = pd.DataFrame({"price": [90.0, 110.0], "touches": [2, 2]})
    roled = annotate_roles(levels, last_close=100.0)
    assert roled.loc[0, "role"] == SUPPORT      # 90 below price
    assert roled.loc[1, "role"] == RESISTANCE   # 110 above price


# --- trendlines ----------------------------------------------------------------

def test_fit_recovers_known_line():
    # perfectly collinear: price = 2*bar + 10
    line = fit_trendline(np.array([0, 1, 2]), np.array([10.0, 12.0, 14.0]), SUPPORT)
    assert line.slope == pytest.approx(2.0)
    assert line.intercept == pytest.approx(10.0)
    assert line.r2 == pytest.approx(1.0)
    assert line.value_at(5) == pytest.approx(20.0)  # projects beyond fitted points


def test_find_trendlines_needs_enough_swings():
    # only 2 lows, 3 highs -> support omitted, resistance present
    swings = _swings(
        [(0, 90.0, SWING_LOW), (4, 92.0, SWING_LOW),
         (1, 110.0, SWING_HIGH), (3, 111.0, SWING_HIGH), (5, 112.0, SWING_HIGH)]
    )
    lines = find_trendlines(swings, num_points=3)
    assert SUPPORT not in lines
    assert RESISTANCE in lines
    assert lines[RESISTANCE].slope > 0


# --- trend ---------------------------------------------------------------------

def _featured(sma_slow_values):
    n = len(sma_slow_values)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {COL_SMA_FAST: sma_slow_values, COL_SMA_SLOW: sma_slow_values}, index=idx
    )


def _up_swings():
    return _swings(
        [(1, 100.0, SWING_HIGH), (3, 105.0, SWING_HIGH), (5, 110.0, SWING_HIGH),
         (2, 95.0, SWING_LOW), (4, 98.0, SWING_LOW), (6, 102.0, SWING_LOW)]
    )


def _down_swings():
    return _swings(
        [(1, 110.0, SWING_HIGH), (3, 105.0, SWING_HIGH), (5, 100.0, SWING_HIGH),
         (2, 102.0, SWING_LOW), (4, 98.0, SWING_LOW), (6, 95.0, SWING_LOW)]
    )


def test_uptrend_confirmed_by_rising_ma():
    result = classify_trend(_featured(list(range(20))), _up_swings(), slope_window=3)
    assert result.label == UPTREND
    assert result.reasons


def test_downtrend_confirmed_by_falling_ma():
    result = classify_trend(_featured(list(range(20, 0, -1))), _down_swings(), slope_window=3)
    assert result.label == DOWNTREND


def test_uptrend_structure_but_flat_ma_downgrades_to_sideways():
    result = classify_trend(_featured([50.0] * 20), _up_swings(), slope_window=3)
    assert result.label == SIDEWAYS
    assert any("unconfirmed" in r for r in result.reasons)


def test_mixed_swings_are_sideways():
    mixed = _swings(
        [(1, 100.0, SWING_HIGH), (3, 110.0, SWING_HIGH), (5, 105.0, SWING_HIGH),
         (2, 95.0, SWING_LOW), (4, 98.0, SWING_LOW), (6, 96.0, SWING_LOW)]
    )
    result = classify_trend(_featured(list(range(20))), mixed, slope_window=3)
    assert result.label == SIDEWAYS


def test_insufficient_swings_is_sideways():
    result = classify_trend(_featured(list(range(20))), _swings([(1, 100.0, SWING_HIGH)]), slope_window=3)
    assert result.label == SIDEWAYS
