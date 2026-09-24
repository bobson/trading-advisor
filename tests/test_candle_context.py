"""1- and 2-candle patterns at a level that favours them (facts-only chart markers).

Scenario: a support zone near 95 (swing lows at bars 10 and 30), a resistance zone near 105 (swing
highs at bars 20 and 40), ATR 2. Candles are placed at bar 60 with hand-set pattern flags."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.indicators.features import (
    COL_ATR,
    COL_BEARISH_ENGULFING,
    COL_BULLISH_ENGULFING,
    COL_DOJI,
    COL_HAMMER,
    COL_SHOOTING_STAR,
)
from src.patterns import candle_context as cc
from src.structure.swings import SWING_HIGH, SWING_LOW

N, I = 80, 60


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _frame(o, h, l, c, *, flag, prev_close=100.0, n=N):
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    base = np.full(n, 100.0)
    df = pd.DataFrame({"open": base, "high": base + 0.5, "low": base - 0.5, "close": base}, index=idx)
    df.iloc[I - 1, df.columns.get_loc("close")] = prev_close
    for col, v in zip(("open", "high", "low", "close"), (o, h, l, c)):
        df.iloc[I, df.columns.get_loc(col)] = v
    df[COL_ATR] = 2.0
    for col in (COL_HAMMER, COL_SHOOTING_STAR, COL_BULLISH_ENGULFING, COL_BEARISH_ENGULFING, COL_DOJI):
        df[col] = False
    df.iloc[I, df.columns.get_loc(flag)] = True
    return df


def _swings(extra=()):
    rows = [(10, 95.0, SWING_LOW), (30, 95.2, SWING_LOW), (20, 105.0, SWING_HIGH), (40, 105.2, SWING_HIGH), *extra]
    return pd.DataFrame(rows, columns=["bar", "price", "kind"]).sort_values("bar")


def _event(df, sw, cfg):
    ev = [e for e in cc.candle_events(df, sw, cfg) if e["bar"] == I]
    assert len(ev) == 1
    return ev[0]


def test_hammer_whose_wick_tags_support_is_marked(cfg):
    e = _event(_frame(97.0, 97.8, 95.1, 97.5, flag=COL_HAMMER, prev_close=97.0), _swings(), cfg)
    assert e["code"] == "H" and e["direction"] == "bullish"
    assert e["level"] is not None and "support" in e["level"]


def test_hammer_in_no_mans_land_is_not_marked(cfg):
    e = _event(_frame(99.0, 99.6, 98.2, 99.5, flag=COL_HAMMER, prev_close=99.0), _swings(), cfg)
    assert e["level"] is None


def test_bullish_pattern_at_resistance_is_not_favoured(cfg):
    """A hammer whose wick dips into a RESISTANCE zone — the level doesn't favour it."""
    e = _event(_frame(106.5, 107.0, 104.9, 106.8, flag=COL_HAMMER, prev_close=104.0), _swings(), cfg)
    assert e["level"] is None


def test_shooting_star_tagging_resistance_is_marked(cfg):
    e = _event(_frame(103.0, 105.3, 102.8, 102.9, flag=COL_SHOOTING_STAR, prev_close=103.0), _swings(), cfg)
    assert e["direction"] == "bearish" and e["level"] is not None and "resistance" in e["level"]


def test_doji_is_never_at_a_level(cfg):
    """A doji has no direction for a level to favour — even sitting right on support."""
    e = _event(_frame(95.2, 95.8, 94.9, 95.2, flag=COL_DOJI, prev_close=96.0), _swings(), cfg)
    assert e["code"] == "D" and e["level"] is None


def test_levels_formed_after_the_candle_do_not_count(cfg):
    """Look-ahead guard: the second support touch lands AFTER bar 60, and one just before it is
    not yet confirmed (bar 57 > 60 − sensitivity 5). The same hammer is then NOT at a zone."""
    sw = pd.DataFrame([(10, 95.0, SWING_LOW), (57, 95.1, SWING_LOW), (70, 95.2, SWING_LOW),
                       (20, 110.0, SWING_HIGH)], columns=["bar", "price", "kind"]).sort_values("bar")
    e = _event(_frame(97.0, 97.8, 95.1, 97.5, flag=COL_HAMMER, prev_close=97.0), sw, cfg)
    assert e["level"] is None


def test_future_bars_do_not_change_past_events(cfg):
    df = _frame(97.0, 97.8, 95.1, 97.5, flag=COL_HAMMER, prev_close=97.0)
    before = _event(df, _swings(), cfg)
    later = df.copy()
    later.iloc[I + 1:, later.columns.get_loc("close")] = 50.0      # a crash after the candle
    later.iloc[I + 1:, later.columns.get_loc("low")] = 49.0
    assert _event(later, _swings(), cfg) == before


def test_precedence_matches_the_vote(cfg):
    """Engulfing beats hammer on the same bar, as in `signal_from_patterns`."""
    df = _frame(97.0, 97.8, 95.1, 97.5, flag=COL_HAMMER, prev_close=97.0)
    df.iloc[I, df.columns.get_loc(COL_BULLISH_ENGULFING)] = True
    assert _event(df, _swings(), cfg)["code"] == "BuE"


def test_cache_gives_the_same_answer(cfg):
    df = _frame(97.0, 97.8, 95.1, 97.5, flag=COL_HAMMER, prev_close=97.0)
    cc._LEVEL_CACHE.clear()
    first = cc.candle_events(df, _swings(), cfg, market=("TEST", "1d"))
    second = cc.candle_events(df, _swings(), cfg, market=("TEST", "1d"))
    assert first == second == cc.candle_events(df, _swings(), cfg)
    assert len(cc._LEVEL_CACHE) == 1                              # bar 60 cached (not the last bar)


def test_serialized_chart_carries_the_three_views():
    from src.service.analyze import advise
    from src.service.serialize import serialize_chart
    cfg = load_config()
    n = 260
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC", name="timestamp")
    c = 100 + 3 * np.sin(np.arange(n) / 4.0)
    df = pd.DataFrame({"open": c + 0.3 * np.cos(np.arange(n)), "high": c + 1.2, "low": c - 1.2,
                       "close": c, "volume": 1.0}, index=idx)
    out = serialize_chart(advise("BTC/USDT", "1h", cfg, df=df, explain_enabled=False))["overlays"]["candles_12"]
    assert set(out) == {"all", "at_level", "last", "level_window"}
    assert all(r["level"] for r in out["at_level"]) and len(out["at_level"]) <= len(out["all"])
    assert all(r["code"] != "D" for r in out["at_level"])
    if out["last"] is not None:
        assert out["last"]["time"] == int(idx[-1].timestamp())
