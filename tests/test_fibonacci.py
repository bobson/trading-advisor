"""Tests for Phase 5 Fibonacci retracements.

The direction logic is pinned by the endpoints: levels[0.0] must equal the most-recent
swing's price and levels[1.0] the older anchor's. (The 0.5 midpoint can't guard this —
both up and down formulas give (H+L)/2 there, so a swapped direction would still pass.)
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.structure.fibonacci import DOWN, UP, fib_retracement
from src.structure.swings import SWING_HIGH, SWING_LOW


def _swings(records):
    """records: list of (bar, price, kind)."""
    return pd.DataFrame(records, columns=["bar", "price", "kind"])


def test_up_leg_endpoints_and_ratios():
    # low at bar 2 (100), then high at bar 6 (200) -> up leg
    fib = fib_retracement(_swings([(2, 100.0, SWING_LOW), (6, 200.0, SWING_HIGH)]))
    assert fib is not None and fib.direction == UP
    assert fib.levels[0.0] == pytest.approx(200.0)   # 0% at the impulse end (the high)
    assert fib.levels[1.0] == pytest.approx(100.0)   # 100% at the older anchor (the low)
    assert fib.levels[0.5] == pytest.approx(150.0)
    assert fib.levels[0.618] == pytest.approx(200.0 - 0.618 * 100.0)


def test_down_leg_endpoints():
    # high at bar 2 (200), then low at bar 6 (100) -> down leg
    fib = fib_retracement(_swings([(2, 200.0, SWING_HIGH), (6, 100.0, SWING_LOW)]))
    assert fib is not None and fib.direction == DOWN
    assert fib.levels[0.0] == pytest.approx(100.0)   # 0% at the impulse end (the low)
    assert fib.levels[1.0] == pytest.approx(200.0)   # 100% at the older anchor (the high)
    assert fib.levels[0.5] == pytest.approx(150.0)


def test_picks_latest_leg():
    # An old leg, then a fresh down leg ending at bar 9. Must use bars 7 (high) & 9 (low).
    swings = _swings(
        [(1, 50.0, SWING_LOW), (3, 90.0, SWING_HIGH),
         (7, 180.0, SWING_HIGH), (9, 120.0, SWING_LOW)]
    )
    fib = fib_retracement(swings)
    assert fib.direction == DOWN
    assert fib.high_bar == 7 and fib.low_bar == 9
    assert fib.levels[0.0] == pytest.approx(120.0)
    assert fib.levels[1.0] == pytest.approx(180.0)


def test_levels_ordered_between_anchors():
    fib = fib_retracement(_swings([(2, 100.0, SWING_LOW), (6, 200.0, SWING_HIGH)]))
    prices = [fib.levels[r] for r in sorted(fib.levels)]
    # up leg: prices decrease from H (r=0) to L (r=1)
    assert prices == sorted(prices, reverse=True)
    assert all(fib.low_price <= p <= fib.high_price for p in prices)


def test_degenerate_leg_returns_none():
    # Non-alternating: two highs in a row, the last high (80) BELOW the far-back low (100).
    # "Most recent opposite before last" reaches back to bar 0 -> H(80) <= L(100).
    swings = _swings(
        [(0, 100.0, SWING_LOW), (4, 150.0, SWING_HIGH), (8, 80.0, SWING_HIGH)]
    )
    assert fib_retracement(swings) is None


def test_insufficient_swings_returns_none():
    assert fib_retracement(_swings([(2, 100.0, SWING_LOW)])) is None
    assert fib_retracement(_swings([])) is None
