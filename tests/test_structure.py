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


# --- ROADMAP A4: support/resistance zones ----------------------------------------------------

from src.structure.support_resistance import find_sr_zones, zone_distance  # noqa: E402


def _sw(rows):
    return pd.DataFrame(rows, columns=["bar", "price", "kind"])


def test_zone_width_scales_with_atr():
    """Same swings, double the ATR -> double the minimum band width (ATR-scaled, not %)."""
    sw = _sw([(10, 100.0, "high"), (20, 100.1, "high")])
    narrow = find_sr_zones(sw, atr=2.0, n_bars=50, zone_atr_mult=0.5)
    wide = find_sr_zones(sw, atr=4.0, n_bars=50, zone_atr_mult=0.5)
    w1 = float(narrow["upper"][0] - narrow["lower"][0])
    w2 = float(wide["upper"][0] - wide["lower"][0])
    assert w1 == pytest.approx(1.0) and w2 == pytest.approx(2.0)


def test_zone_is_scale_free_across_markets():
    """A BTC-sized and an FX-sized market with proportional swings + ATR get proportional bands."""
    btc = find_sr_zones(_sw([(10, 80000.0, "high"), (20, 80040.0, "high")]), atr=800.0, n_bars=50)
    fx = find_sr_zones(_sw([(10, 1.1000, "high"), (20, 1.10055, "high")]), atr=0.011, n_bars=50)
    rel = lambda z: float((z["upper"][0] - z["lower"][0]) / z["price"][0])  # noqa: E731
    assert rel(btc) == pytest.approx(rel(fx), rel=1e-3)


def test_zone_covers_every_touch_and_merges_by_atr():
    sw = _sw([(5, 100.0, "low"), (15, 101.2, "low"), (25, 110.0, "high")])
    z = find_sr_zones(sw, atr=4.0, n_bars=40, zone_atr_mult=0.5, min_touches=1)
    first = z.iloc[0]
    assert first["touches"] == 2                           # 100 and 101.2 are within 0.5×ATR=2
    assert first["lower"] <= 100.0 and first["upper"] >= 101.2
    assert len(z) == 2                                     # 110 is its own zone


def test_touch_history_and_staleness():
    sw = _sw([(5, 100.0, "low"), (30, 100.2, "high")])
    z = find_sr_zones(sw, atr=2.0, n_bars=200, stale_bars=120).iloc[0]
    assert (z["first_touch"], z["last_touch"], z["bars_since_touch"]) == (5, 30, 169)
    assert bool(z["stale"])                                # 169 >= 120 bars without a reversal
    fresh = find_sr_zones(sw, atr=2.0, n_bars=100, stale_bars=120).iloc[0]
    assert fresh["bars_since_touch"] == 69 and not bool(fresh["stale"])


def test_strength_is_recency_weighted():
    old = find_sr_zones(_sw([(0, 100.0, "low"), (10, 100.1, "low")]), atr=2.0, n_bars=200,
                        halflife_bars=60).iloc[0]
    recent = find_sr_zones(_sw([(180, 100.0, "low"), (190, 100.1, "low")]), atr=2.0, n_bars=200,
                           halflife_bars=60).iloc[0]
    assert recent["touches"] == old["touches"] and recent["strength"] > 5 * old["strength"]


def test_zone_distance_is_zero_inside_the_band():
    z = pd.DataFrame({"lower": [99.0, 105.0], "upper": [101.0, 106.0]})
    assert list(zone_distance(z, 100.0)) == [0.0, 5.0]


def test_zones_are_look_ahead_safe():
    """Zones built from bars <= N don't change when later bars change: they only read confirmed
    swings at or before N and the ATR/length of the slice."""
    sw = _sw([(5, 100.0, "low"), (15, 100.3, "low")])
    a = find_sr_zones(sw[sw["bar"] <= 20], atr=2.0, n_bars=21)
    b = find_sr_zones(pd.concat([sw, _sw([(30, 100.1, "low")])]).query("bar <= 20"), atr=2.0, n_bars=21)
    pd.testing.assert_frame_equal(a, b)
