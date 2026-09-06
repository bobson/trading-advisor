"""Tests for Phase 9 — named chart patterns.

The "done when" is: clear textbook examples get the correct label. Patterns can legitimately
co-occur (an ascending triangle's near-equal highs also read as a double top), so we assert
the expected label is *present*, not that it's the only one. Separate tests pin the
anti-over-call guards (shallow trough / mismatched peaks must NOT fire).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.config import load_config
from src.patterns.chart_patterns import (
    ASCENDING_TRIANGLE,
    BEARISH,
    BULLISH,
    DESCENDING_TRIANGLE,
    DOUBLE_BOTTOM,
    DOUBLE_TOP,
    HEAD_AND_SHOULDERS,
    INVERSE_HEAD_AND_SHOULDERS,
    SYMMETRIC_TRIANGLE,
    find_chart_patterns,
)
from src.structure.swings import SWING_HIGH, SWING_LOW


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _swings(records):
    """records: list of (bar, price, kind)."""
    return pd.DataFrame(records, columns=["bar", "price", "kind"])


def _names(patterns):
    return {p.name for p in patterns}


# --- textbook positives --------------------------------------------------------

def test_double_top(cfg):
    s = _swings([
        (0, 90.0, SWING_LOW),
        (5, 110.0, SWING_HIGH),
        (10, 100.0, SWING_LOW),   # ~9% trough -> real reversal
        (15, 110.0, SWING_HIGH),  # equal peak
    ])
    patterns = find_chart_patterns(s, cfg)
    assert DOUBLE_TOP in _names(patterns)
    dt = next(p for p in patterns if p.name == DOUBLE_TOP)
    assert dt.direction == BEARISH
    assert dt.neckline == 100.0


def test_double_bottom(cfg):
    s = _swings([
        (0, 110.0, SWING_HIGH),
        (5, 90.0, SWING_LOW),
        (10, 100.0, SWING_HIGH),
        (15, 90.0, SWING_LOW),
    ])
    patterns = find_chart_patterns(s, cfg)
    assert DOUBLE_BOTTOM in _names(patterns)
    assert next(p for p in patterns if p.name == DOUBLE_BOTTOM).direction == BULLISH


def test_head_and_shoulders(cfg):
    s = _swings([
        (5, 110.0, SWING_HIGH),   # left shoulder
        (10, 100.0, SWING_LOW),
        (15, 125.0, SWING_HIGH),  # head (highest)
        (20, 101.0, SWING_LOW),
        (25, 110.0, SWING_HIGH),  # right shoulder (equal to left)
    ])
    patterns = find_chart_patterns(s, cfg)
    assert HEAD_AND_SHOULDERS in _names(patterns)
    hs = next(p for p in patterns if p.name == HEAD_AND_SHOULDERS)
    assert hs.direction == BEARISH
    assert hs.bars == [5, 15, 25]


def test_inverse_head_and_shoulders(cfg):
    s = _swings([
        (5, 110.0, SWING_LOW),    # left shoulder
        (10, 100.0, SWING_HIGH),
        (15, 85.0, SWING_LOW),    # head (lowest)
        (20, 99.0, SWING_HIGH),
        (25, 110.0, SWING_LOW),   # right shoulder
    ])
    patterns = find_chart_patterns(s, cfg)
    assert INVERSE_HEAD_AND_SHOULDERS in _names(patterns)
    assert next(p for p in patterns if p.name == INVERSE_HEAD_AND_SHOULDERS).direction == BULLISH


def test_symmetric_triangle(cfg):
    s = _swings([
        (0, 130.0, SWING_HIGH),
        (5, 100.0, SWING_LOW),
        (10, 122.0, SWING_HIGH),  # falling highs
        (15, 108.0, SWING_LOW),   # rising lows
        (20, 116.0, SWING_HIGH),
        (25, 112.0, SWING_LOW),
    ])
    patterns = find_chart_patterns(s, cfg)
    assert SYMMETRIC_TRIANGLE in _names(patterns)
    assert next(p for p in patterns if p.name == SYMMETRIC_TRIANGLE).direction == "neutral"


def test_ascending_triangle(cfg):
    s = _swings([
        (0, 120.0, SWING_HIGH),
        (5, 100.0, SWING_LOW),
        (10, 120.5, SWING_HIGH),  # flat highs
        (15, 105.0, SWING_LOW),   # rising lows
        (20, 119.8, SWING_HIGH),
        (25, 110.0, SWING_LOW),
    ])
    patterns = find_chart_patterns(s, cfg)
    assert ASCENDING_TRIANGLE in _names(patterns)
    assert next(p for p in patterns if p.name == ASCENDING_TRIANGLE).direction == BULLISH


def test_descending_triangle(cfg):
    s = _swings([
        (0, 130.0, SWING_HIGH),
        (5, 100.0, SWING_LOW),
        (10, 120.0, SWING_HIGH),  # falling highs
        (15, 100.5, SWING_LOW),   # flat lows
        (20, 112.0, SWING_HIGH),
        (25, 99.8, SWING_LOW),
    ])
    patterns = find_chart_patterns(s, cfg)
    assert DESCENDING_TRIANGLE in _names(patterns)
    assert next(p for p in patterns if p.name == DESCENDING_TRIANGLE).direction == BEARISH


# --- anti-over-call guards -----------------------------------------------------

def test_shallow_trough_is_not_a_double_top(cfg):
    # Two equal highs but only a ~1% dip between them -> not a real reversal.
    s = _swings([
        (0, 90.0, SWING_LOW),
        (5, 110.0, SWING_HIGH),
        (10, 108.9, SWING_LOW),   # ~1% below the peaks < 3% min_trough
        (15, 110.0, SWING_HIGH),
    ])
    assert DOUBLE_TOP not in _names(find_chart_patterns(s, cfg))


def test_mismatched_peaks_are_not_a_double_top(cfg):
    # Peaks differ by ~9% -> not "equal" -> no double top.
    s = _swings([
        (0, 90.0, SWING_LOW),
        (5, 110.0, SWING_HIGH),
        (10, 95.0, SWING_LOW),
        (15, 120.0, SWING_HIGH),
    ])
    assert DOUBLE_TOP not in _names(find_chart_patterns(s, cfg))


def test_head_not_clearing_shoulders_is_not_hs(cfg):
    # "Head" barely above shoulders (< tolerance) -> just three similar highs.
    s = _swings([
        (5, 110.0, SWING_HIGH),
        (10, 100.0, SWING_LOW),
        (15, 111.0, SWING_HIGH),  # < 2% above shoulders
        (20, 101.0, SWING_LOW),
        (25, 110.0, SWING_HIGH),
    ])
    assert HEAD_AND_SHOULDERS not in _names(find_chart_patterns(s, cfg))


def test_empty_and_tiny_inputs(cfg):
    assert find_chart_patterns(_swings([]), cfg) == []
    assert find_chart_patterns(_swings([(0, 100.0, SWING_HIGH)]), cfg) == []
