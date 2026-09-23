"""Two-point trendlines: a line through two swing lows (support) / two swing highs (resistance),
kept only while no close has broken it by more than break_atr_mult × ATR."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators.features import COL_ATR
from src.structure.swings import SWING_HIGH, SWING_LOW
from src.structure.trendlines import RESISTANCE, SUPPORT, find_two_point_trendlines


def _frame(closes, atr=1.0):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, COL_ATR: atr}, index=idx)


def _swings(rows):
    return pd.DataFrame(rows, columns=["bar", "price", "kind"])


def _find(df, sw):
    return find_two_point_trendlines(df, sw, atr_col=COL_ATR, break_atr_mult=0.25)


def test_rising_support_through_two_lows():
    closes = [100 + i for i in range(30)]                  # steady uptrend, never breaks the line
    sw = _swings([(5, 104.0, SWING_LOW), (15, 114.0, SWING_LOW)])
    tl = _find(_frame(closes), sw)[SUPPORT]
    assert tl.direction == "rising" and tl.anchors == [(5, 104.0), (15, 114.0)]
    assert abs(tl.value_at(25) - 124.0) < 1e-9             # 1 per bar, projected forward


def test_broken_line_is_dropped():
    closes = [100 + i for i in range(30)]
    closes[20] = 110.0                                    # line is at 119 on bar 20 -> close well below
    sw = _swings([(5, 104.0, SWING_LOW), (15, 114.0, SWING_LOW)])
    assert SUPPORT not in _find(_frame(closes), sw)


def test_small_poke_within_atr_margin_keeps_the_line():
    closes = [100 + i for i in range(30)]
    closes[20] = 118.8                                    # 0.2 below the line (119), margin is 0.25
    sw = _swings([(5, 104.0, SWING_LOW), (15, 114.0, SWING_LOW)])
    assert SUPPORT in _find(_frame(closes), sw)


def test_longest_valid_line_wins():
    closes = [100 + i for i in range(30)]
    sw = _swings([(2, 101.0, SWING_LOW), (8, 107.0, SWING_LOW), (15, 114.0, SWING_LOW)])
    tl = _find(_frame(closes), sw)[SUPPORT]
    assert tl.anchors[0] == (2, 101.0)                    # earliest anchor that stays unbroken


def test_invalid_older_anchor_falls_back_to_a_later_one():
    closes = [100 + i for i in range(30)]
    # A line from (2, 90) to (15, 114) runs above the closes early on -> broken; (8, 107) is valid.
    sw = _swings([(2, 90.0, SWING_LOW), (8, 107.0, SWING_LOW), (15, 114.0, SWING_LOW)])
    tl = _find(_frame(closes), sw)[SUPPORT]
    assert tl.anchors[0] == (8, 107.0)


def test_falling_resistance_through_two_highs():
    closes = [130 - i for i in range(30)]
    sw = _swings([(5, 126.0, SWING_HIGH), (15, 116.0, SWING_HIGH)])
    tl = _find(_frame(closes), sw)[RESISTANCE]
    assert tl.direction == "falling"


def test_needs_two_swings_of_a_kind():
    sw = _swings([(5, 104.0, SWING_LOW), (8, 120.0, SWING_HIGH)])
    assert _find(_frame([100 + i for i in range(30)]), sw) == {}


def test_look_ahead_safe():
    """The lines at bar N must not change when bars after N are mutated."""
    closes = [100 + i for i in range(40)]
    sw = _swings([(5, 104.0, SWING_LOW), (15, 114.0, SWING_LOW)])
    df = _frame(closes)
    before = _find(df.iloc[:26], sw)
    mutated = df.copy()
    mutated.iloc[26:, mutated.columns.get_loc("close")] = 10.0     # future crash through the line
    after = _find(mutated.iloc[:26], sw)
    assert before[SUPPORT].anchors == after[SUPPORT].anchors
