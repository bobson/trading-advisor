"""Tests for swing detection — the foundation, so this is the most important test file.

"Matches the highs/lows your eye would pick" isn't machine-checkable, so we pin the
definition two independent ways: hand-built series with known pivots, and a
centered-rolling-max cross-check that must agree with scipy on interior points.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.structure.swings import (
    SWING_HIGH,
    SWING_LOW,
    add_swing_columns,
    find_swings,
)


def _ohlc_from_pivots(mid):
    """Build candles whose high/low straddle a mid price by ±0.5 (clean zigzag)."""
    mid = np.asarray(mid, dtype=float)
    idx = pd.date_range("2024-01-01", periods=len(mid), freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": mid, "high": mid + 0.5, "low": mid - 0.5, "close": mid, "volume": 1.0},
        index=idx,
    )


def _random_walk(n=300, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": close, "high": close + rng.uniform(0.1, 1, n),
         "low": close - rng.uniform(0.1, 1, n), "close": close, "volume": 1.0},
        index=idx,
    )


def test_finds_obvious_swings():
    # mid zigzag: peaks at bars 1,3,5 ; troughs at bars 2,4
    df = _ohlc_from_pivots([1, 3, 2, 5, 1, 4, 2])
    swings = find_swings(df, sensitivity=1)
    highs = sorted(swings.loc[swings["kind"] == SWING_HIGH, "bar"])
    lows = sorted(swings.loc[swings["kind"] == SWING_LOW, "bar"])
    assert highs == [1, 3, 5]
    assert lows == [2, 4]


def test_uses_high_low_not_close():
    # high peaks at bar 1, but close peaks at bar 2 — the detector must follow `high`.
    idx = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"open": [1, 1, 1, 1], "high": [1, 5, 2, 1], "low": [0, 0, 0, 0],
         "close": [1, 2, 4, 1], "volume": 1.0},
        index=idx,
    )
    swings = find_swings(df, sensitivity=1)
    high_bars = list(swings.loc[swings["kind"] == SWING_HIGH, "bar"])
    assert high_bars == [1]  # not [2], which is where close peaks


def test_recent_unconfirmed_pivot_is_excluded():
    # A peak at bar 5 (of 7) has only 1 real bar to its right; at sensitivity=2 it is
    # NOT confirmed. mode='clip' would wrongly flag it — the interior filter must not.
    df = _ohlc_from_pivots([1, 2, 3, 4, 5, 10, 9])
    swings = find_swings(df, sensitivity=2)
    assert 5 not in list(swings["bar"])  # unconfirmed near-edge peak excluded


def test_higher_sensitivity_yields_fewer_swings():
    df = _random_walk()
    fine = len(find_swings(df, sensitivity=2))
    coarse = len(find_swings(df, sensitivity=10))
    assert coarse < fine


def test_matches_centered_rolling_max():
    # Independent definition: an interior swing high is where `high` equals the max of
    # the centered (2k+1) window. Must agree with scipy on interior bars.
    df = _random_walk()
    k = 3
    marked = add_swing_columns(df, sensitivity=k)["swing_high"].to_numpy()
    roll_max = df["high"].rolling(2 * k + 1, center=True).max()
    expected = (df["high"] == roll_max).to_numpy()
    interior = slice(k, len(df) - k)
    assert np.array_equal(marked[interior], expected[interior])


def test_add_swing_columns_shape_and_dtype():
    df = _random_walk(n=80)
    out = add_swing_columns(df, sensitivity=5)
    assert len(out) == len(df)
    assert out["swing_high"].dtype == bool and out["swing_low"].dtype == bool
    # last `sensitivity` bars can't be confirmed yet
    assert not out["swing_high"].iloc[-5:].any()
    assert not out["swing_low"].iloc[-5:].any()


def test_invalid_sensitivity_raises():
    df = _ohlc_from_pivots([1, 2, 3])
    with pytest.raises(ValueError):
        find_swings(df, sensitivity=0)
