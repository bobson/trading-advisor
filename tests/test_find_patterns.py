"""Feature 2 — the refactored detectors emit Patterns with state, and the look-ahead guard covers
the state machine. Synthetic fixtures exercise detection of each shape and each state.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.indicators.features import COL_ATR
from src.patterns.base import BULLISH, CONFIRMED, FAILED, FORMING
from src.patterns.chart_patterns import (
    ASCENDING_CHANNEL,
    ASCENDING_TRIANGLE,
    DOUBLE_BOTTOM,
    DOUBLE_TOP,
    RECTANGLE,
    find_patterns,
)
from src.structure.swings import SWING_HIGH, SWING_LOW


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _frame(swing_rows, last_close, *, atr=2.0, n=None):
    """A minimal featured frame + swings. `swing_rows` = [(bar, price, kind)]; `last_close` sets
    bar N's close (which drives the state); `atr` sets the ATR-scaled tolerance."""
    max_bar = max(b for b, _, _ in swing_rows)
    n = n or max_bar + 3
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC", name="timestamp")
    close = np.full(n, 100.0)
    close[-1] = last_close
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close}, index=idx)
    df[COL_ATR] = atr
    swings = pd.DataFrame(swing_rows, columns=["bar", "price", "kind"])
    return df, swings


def _types(patterns):
    return {p.type for p in patterns}


# --- detection of each shape ----------------------------------------------------------------

def _double_top_swings():
    return [(2, 110.0, SWING_HIGH), (4, 100.0, SWING_LOW), (6, 110.0, SWING_HIGH)]


def test_detects_double_top(cfg):
    df, sw = _frame(_double_top_swings(), last_close=105)
    pats = find_patterns(df, sw, cfg)
    assert DOUBLE_TOP in _types(pats)
    p = next(p for p in pats if p.type == DOUBLE_TOP)
    assert p.direction == "bearish" and p.breakout_level == 100.0 and p.invalidation_level == 110.0


def test_detects_ascending_triangle(cfg):
    sw = [(1, 110.0, SWING_HIGH), (3, 110.0, SWING_HIGH), (5, 110.0, SWING_HIGH),
          (2, 100.0, SWING_LOW), (4, 103.0, SWING_LOW), (6, 106.0, SWING_LOW)]
    df, sw = _frame(sw, last_close=108)
    pats = find_patterns(df, sw, cfg)
    assert ASCENDING_TRIANGLE in _types(pats)


def test_detects_rectangle(cfg):
    sw = [(1, 110.0, SWING_HIGH), (3, 110.0, SWING_HIGH), (5, 110.0, SWING_HIGH),
          (2, 100.0, SWING_LOW), (4, 100.0, SWING_LOW), (6, 100.0, SWING_LOW)]
    df, sw = _frame(sw, last_close=105)
    assert RECTANGLE in _types(find_patterns(df, sw, cfg))   # RECTANGLE == "sideways channel"


def test_sideways_channel_after_a_runup_is_not_an_ascending_channel(cfg):
    """Regression (BTC daily): the flat top/bottom span only the last TWO swings each, while an
    older run-up swing is lower. That used to fit a rising line and mislabel a horizontal RANGE as
    an 'ascending channel'. It must now read as a sideways channel, not ascending."""
    sw = [(1, 60.0, SWING_LOW), (2, 65.0, SWING_HIGH),      # the move INTO the range (older, lower)
          (3, 75.0, SWING_LOW), (4, 82.0, SWING_HIGH),      # range: flat bottom ~75, flat top ~82
          (5, 75.5, SWING_LOW), (6, 82.5, SWING_HIGH)]
    df, sw = _frame(sw, last_close=78)
    types = _types(find_patterns(df, sw, cfg))
    assert RECTANGLE in types                                # the sideways channel is detected
    assert ASCENDING_CHANNEL not in types                    # ...and NOT mislabelled as ascending
    p = next(p for p in find_patterns(df, sw, cfg) if p.type == RECTANGLE)
    assert abs(p.breakout_level - 82.25) < 1 and abs(p.invalidation_level - 75.25) < 1   # flat edges


def test_detects_ascending_channel(cfg):
    sw = [(1, 105.0, SWING_HIGH), (3, 108.0, SWING_HIGH), (5, 111.0, SWING_HIGH),
          (2, 100.0, SWING_LOW), (4, 103.0, SWING_LOW), (6, 106.0, SWING_LOW)]
    df, sw = _frame(sw, last_close=110)
    assert ASCENDING_CHANNEL in _types(find_patterns(df, sw, cfg))


# --- the three states, via a double top -----------------------------------------------------

@pytest.mark.parametrize("last_close,expected", [
    (105, FORMING),      # between neckline 100 and the peaks 110
    (95, CONFIRMED),     # closed below the neckline -> bearish break confirmed
    (115, FAILED),       # closed back above the peaks -> failed
])
def test_double_top_state_machine(cfg, last_close, expected):
    df, sw = _frame(_double_top_swings(), last_close=last_close)
    p = next(p for p in find_patterns(df, sw, cfg) if p.type == DOUBLE_TOP)
    assert p.state == expected


def _with_closes(df, closes_from_bar7):
    """Overwrite the closes after the double top's right peak (bar 6) — bars 7..N."""
    df = df.copy()
    df.iloc[7:7 + len(closes_from_bar7), df.columns.get_loc("close")] = closes_from_bar7
    return df


@pytest.mark.parametrize("closes,expected", [
    ([95, 97, 96], CONFIRMED),     # broke below the neckline (100) and stayed below
    ([95, 97, 105], FAILED),       # broke below, then closed back above the neckline -> reclaimed
    ([105, 95, 103], FAILED),      # the reclaim counts even after a later re-break attempt
    ([104, 107, 105], FORMING),    # never broke, never hit the peaks
    ([115, 105, 105], FAILED),     # closed above the peaks once -> stays failed
])
def test_double_top_state_remembers_history(cfg, closes, expected):
    df, sw = _frame(_double_top_swings(), last_close=closes[-1], n=10)
    df = _with_closes(df, closes)
    p = next(p for p in find_patterns(df, sw, cfg) if p.type == DOUBLE_TOP)
    assert p.state == expected
    assert ("failed break" in p.reason) == (expected == FAILED and closes[0] != 115)


@pytest.mark.parametrize("reclaim_close,expected", [
    (100.3, CONFIRMED),   # back above the neckline (100) but inside 0.25 x ATR(2) = 0.5 -> not a reclaim
    (100.6, FAILED),      # beyond the margin -> reclaimed
])
def test_reclaim_needs_atr_margin(cfg, reclaim_close, expected):
    assert cfg.patterns.reclaim_atr_mult == 0.25
    df, sw = _frame(_double_top_swings(), last_close=reclaim_close, n=10)
    df = _with_closes(df, [95, 97, reclaim_close])
    p = next(p for p in find_patterns(df, sw, cfg) if p.type == DOUBLE_TOP)
    assert p.state == expected


def test_double_bottom_reclaimed_breakout_fails(cfg):
    """Mirror: a double bottom that closes above its neckline, then back below it, reads failed."""
    sw = [(2, 90.0, SWING_LOW), (4, 100.0, SWING_HIGH), (6, 90.0, SWING_LOW)]
    df, sw = _frame(sw, last_close=97, n=10)
    df = _with_closes(df, [105, 103, 97])
    p = next(p for p in find_patterns(df, sw, cfg) if p.type == DOUBLE_BOTTOM)
    assert p.state == FAILED


def test_neutral_rectangle_resolves_direction_on_break(cfg):
    sw = [(1, 110.0, SWING_HIGH), (3, 110.0, SWING_HIGH), (5, 110.0, SWING_HIGH),
          (2, 100.0, SWING_LOW), (4, 100.0, SWING_LOW), (6, 100.0, SWING_LOW)]
    df, sw = _frame(sw, last_close=113)     # closed above the top of the range
    p = next(p for p in find_patterns(df, sw, cfg) if p.type == RECTANGLE)
    assert p.direction == BULLISH and p.state == CONFIRMED


# --- look-ahead guard extended to the state machine -----------------------------------------

def test_state_is_look_ahead_safe(cfg):
    """The pattern + its state at bar N must not change when future bars are mutated. Detect on
    df[:N+1] (find_swings' confirmed-interior filter is the leak vector)."""
    from src.indicators.features import add_features
    from src.structure.swings import find_swings

    # a real-ish daily series with a clean double-top near the end
    n = 80
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC", name="timestamp")
    t = np.arange(n)
    close = 100 + 6 * np.sin(t / 4.0) + t * 0.03
    close[60] = close[52] = 118.0            # two equal peaks -> a double top
    df = pd.DataFrame({"open": close, "high": close + 1.5, "low": close - 1.5, "close": close}, index=idx)

    k = 66
    sub = df.iloc[: k + 1]
    feat = add_features(sub, cfg)
    sw = find_swings(sub, cfg.structure.swing_sensitivity)
    before = find_patterns(feat, sw, cfg)
    assert before, "no pattern near the cut — the guard would be vacuous"        # non-degeneracy
    states_before = sorted((p.type, p.state) for p in before)

    mutated = df.copy()
    mutated.iloc[k + 1:] *= 10.0             # finite garbage after the cut
    msub = mutated.iloc[: k + 1]
    after = find_patterns(add_features(msub, cfg), find_swings(msub, cfg.structure.swing_sensitivity), cfg)
    assert sorted((p.type, p.state) for p in after) == states_before


# --- impulse trim, wedges, trader-style lines, breakout memory on sloped lines ----------------

def _frame_closes(swing_rows, closes, atr=2.0):
    """Like _frame, but with explicit closes for every bar (so sloped-line breakouts are realistic)."""
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC", name="timestamp")
    c = np.asarray(closes, dtype=float)
    df = pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c}, index=idx)
    df[COL_ATR] = atr
    return df, pd.DataFrame(swing_rows, columns=["bar", "price", "kind"])


def test_xrp_like_falling_wedge_after_a_rally(cfg):
    """Regression (XRP/USDT 1d, Aug–Sep 2026): a big rally to a new high, then lower highs and lower
    lows converging. The pre-rally low must NOT be used (it made the old detector say 'symmetric
    triangle'); it's a falling wedge, and the breakout is the first close above the line a trader
    draws through the highest wicks."""
    from src.patterns.chart_patterns import FALLING_WEDGE
    sw = [(2, 99.0, SWING_HIGH), (5, 98.0, SWING_LOW),            # before the rally
          (13, 170.0, SWING_HIGH),                                 # rally top: a +72 leg = impulse
          (24, 131.0, SWING_LOW), (25, 148.0, SWING_HIGH), (36, 150.0, SWING_HIGH), (38, 125.0, SWING_LOW)]
    closes = [100.0] * 13 + [150.0] * 11 + [135.0] * 15
    upper_at = lambda b: 170.0 + (150.0 - 170.0) / 23 * (b - 13)   # noqa: E731  line through 13 and 36
    closes += [upper_at(39) - 3, upper_at(40) - 2, upper_at(41) + 4, upper_at(42) + 6]
    df, sw_df = _frame_closes(sw, closes)
    p = next(p for p in find_patterns(df, sw_df, cfg) if p.type == FALLING_WEDGE)
    assert p.direction == BULLISH and p.state == CONFIRMED
    assert p.state_bar == 41                                         # first close above the drawn line
    assert min(p.bars) >= 13                                         # nothing from before the rally


def test_upper_boundary_is_the_line_through_the_highest_wicks(cfg):
    from src.patterns.chart_patterns import _envelope
    from src.structure.trendlines import fit_trendline
    pts = pd.DataFrame([(13, 170.0), (25, 148.0), (36, 150.0)], columns=["bar", "price"])
    fit = fit_trendline(pts["bar"].to_numpy(), pts["price"].to_numpy(), "resistance")
    env = _envelope(pts, True, fit)
    assert all(env.value_at(b) >= p - 1e-9 for b, p in zip(pts["bar"], pts["price"]))   # nothing above it
    assert env.value_at(13) == pytest.approx(170.0) and env.value_at(36) == pytest.approx(150.0)


def test_a_steady_trend_is_not_mistaken_for_an_impulse(cfg):
    from src.patterns.chart_patterns import _after_last_impulse
    n = 40
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    c = np.linspace(100, 120, n)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, COL_ATR: 1.0}, index=idx)
    sw = pd.DataFrame([(5, 106.0, SWING_HIGH), (15, 111.0, SWING_HIGH), (25, 116.0, SWING_HIGH),
                       (10, 102.0, SWING_LOW), (20, 107.0, SWING_LOW), (30, 112.0, SWING_LOW)],
                      columns=["bar", "price", "kind"])
    _, trimmed = _after_last_impulse(sw, df, cfg, 1.0)
    assert not trimmed


def test_neutral_range_that_breaks_down_gets_a_downside_target(cfg):
    sw = [(1, 110.0, SWING_HIGH), (3, 110.0, SWING_HIGH), (5, 110.0, SWING_HIGH),
          (2, 100.0, SWING_LOW), (4, 100.0, SWING_LOW), (6, 100.0, SWING_LOW)]
    df, sw = _frame(sw, last_close=96)
    p = next(p for p in find_patterns(df, sw, cfg) if p.type == RECTANGLE)
    assert p.direction == "bearish" and p.state == CONFIRMED
    assert p.target == pytest.approx(90.0)                         # 100 − (110 − 100), not 120
